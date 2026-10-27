import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import codex_hub as runtime
import fulltext


def reply(url, body, kind='text/html', status=200):
    result = requests.Response()
    result.url = url
    result.status_code = status
    result._content = body.encode() if isinstance(body, str) else body
    result._content_consumed = True
    result.headers['Content-Type'] = kind
    result.encoding = 'utf-8'
    return result


@pytest.fixture
def pdf():
    with runtime.hub.fitz.open() as doc:
        doc.new_page().insert_text((72, 72), 'Ionogel full paper. Conductivity 2 mS/cm at 25 C.')
        return doc.tobytes()


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.TRANSPORT, 'cache_path', tmp_path / 'cache.sqlite3')
    monkeypatch.setattr(runtime.TRANSPORT, 'no_cache', False)
    monkeypatch.setattr(runtime.TRANSPORT, 'retries', 0)
    monkeypatch.setattr(runtime.hub, 'resolve_unpaywall_pdf', lambda _: None)
    def denied(*args, **kwargs):
        raise AssertionError('Unexpected network request')
    monkeypatch.setattr(runtime.TRANSPORT, 'request', denied)


def test_publisher_doi_redirect_and_metadata_pdf(monkeypatch, pdf):
    calls = []
    def request(session, method, url, **kwargs):
        calls.append((url, id(session), getattr(session, '_chem_fulltext', False)))
        if url.startswith('https://doi.org/'):
            session.cookies.set('publisher', 'ephemeral')
            return reply('https://publisher.example/article/1', '<meta name="citation_pdf_url" content="/paper.pdf?token=private">')
        assert session.cookies.get('publisher') == 'ephemeral'
        return reply(url, pdf, 'application/pdf')
    monkeypatch.setattr(runtime.TRANSPORT, 'request', request)
    result = runtime.hub.deep_read_pdf('10.1234/example')
    assert result['status'] == 'success'
    assert result['pages_read'] == 1
    assert 'Ionogel full paper' in result['pages'][0]['text']
    assert result['retrieval']['retrieval_route'] == 'publisher_pdf_link'
    assert 'private' not in json.dumps(result)
    assert len({row[1] for row in calls}) == 1 and all(row[2] for row in calls)
    assert not runtime.TRANSPORT.cache_path.exists()


def test_oa_failure_falls_back_to_publisher(monkeypatch, pdf):
    monkeypatch.setattr(runtime.hub, 'resolve_unpaywall_pdf', lambda _: 'https://repository.example/broken.pdf')
    def request(session, method, url, **kwargs):
        if 'repository' in url:
            return reply(url, 'missing', status=404)
        return reply('https://publisher.example/paper.pdf', pdf, 'application/pdf')
    monkeypatch.setattr(runtime.TRANSPORT, 'request', request)
    body, info = fulltext.retrieve(runtime.hub, '10.1234/a', '10.1234/a')
    assert body == pdf
    assert info['retrieval_route'] == 'doi_publisher'
    assert info['attempts'][0]['http_status'] == 404


def test_crossref_fulltext_fallback(monkeypatch, pdf):
    def request(session, method, url, **kwargs):
        if 'crossref' in url:
            return reply(url, json.dumps({'message': {'link': [{'URL': 'https://publisher.example/main.pdf', 'content-type': 'application/pdf'}]}}), 'application/json')
        if 'main.pdf' in url:
            return reply(url, pdf, 'application/octet-stream')
        return reply('https://publisher.example/article/a', '<html>Abstract only</html>')
    monkeypatch.setattr(runtime.TRANSPORT, 'request', request)
    body, info = fulltext.retrieve(runtime.hub, '10.1234/a', '10.1234/a')
    assert body == pdf and info['retrieval_route'] == 'crossref_fulltext'


@pytest.mark.parametrize('status,html', [(403, 'Access denied'), (200, '<html>Institutional login. Sign in to access</html>')])
def test_login_never_counts_as_fulltext(monkeypatch, status, html):
    monkeypatch.setattr(runtime.TRANSPORT, 'request', lambda session, method, url, **kw: reply(url, html, status=status))
    result = runtime.hub.deep_read_pdf('https://publisher.example/paper.pdf')
    assert result['status'] == 'browser_required'
    assert 'pages' not in result
    assert result['browser_handoff']['publisher_url'] == 'https://publisher.example/paper.pdf'


def test_malformed_pdf_and_supplement_not_main(monkeypatch):
    links = fulltext.pdf_links('<a href="supplement.pdf">PDF</a><meta name="citation_pdf_url" content="/main.pdf">', 'https://publisher.example/article')
    assert links == ['https://publisher.example/main.pdf']
    monkeypatch.setattr(runtime.TRANSPORT, 'request', lambda session, method, url, **kw: reply(url, b'%PDF-corrupt', 'application/pdf'))
    body, result = fulltext.retrieve(runtime.hub, 'https://publisher.example/main.pdf')
    assert body is None and result['status'] == 'fulltext_unavailable'
    assert result['attempts'][0]['outcome'] == 'invalid_pdf'


def test_download_size_limit(monkeypatch):
    monkeypatch.setattr(fulltext, 'MAX_BYTES', 10)
    monkeypatch.setattr(runtime.TRANSPORT, 'request', lambda session, method, url, **kw: reply(url, b'x' * 20))
    body, info = fulltext.retrieve(runtime.hub, 'https://publisher.example/paper.pdf')
    assert body is None and info['attempts'][0]['outcome'] == 'too_large'


def test_html_refresh_to_main_paper(monkeypatch, pdf):
    def request(session, method, url, **kwargs):
        if url.endswith('/resolver'):
            return reply(url, '<meta http-equiv="REFRESH" content="2; url=\'/article\'">')
        if url.endswith('/article'):
            return reply(url, '<meta name="citation_pdf_url" content="/main.pdf">')
        return reply(url, pdf, 'application/pdf')
    monkeypatch.setattr(runtime.TRANSPORT, 'request', request)
    body, info = fulltext.retrieve(runtime.hub, 'https://publisher.example/resolver')
    assert body == pdf
    assert [a['origin'] for a in info['attempts']] == ['provided_url', 'publisher_html_redirect', 'publisher_pdf_link']


def test_save_pdf_preserves_existing_and_checksum(tmp_path, pdf):
    destination = tmp_path/'paper.pdf'
    saved = fulltext.persist_pdf(pdf, destination)
    assert destination.read_bytes() == pdf and len(saved['pdf_sha256']) == 64
    assert fulltext.persist_pdf(pdf, destination) == saved
    with pytest.raises(FileExistsError):
        fulltext.persist_pdf(pdf+b'different', destination)
    assert destination.read_bytes() == pdf


def test_collection_resumes_local_pdfs(monkeypatch, tmp_path, pdf):
    def request(session, method, url, **kwargs):
        return reply(url, pdf, 'application/pdf')
    monkeypatch.setattr(runtime.TRANSPORT, 'request', request)
    papers=[{'title':'Ionogel', 'doi':'10.1234/a', 'open_access_pdf':'https://publisher.example/a.pdf'}]
    first=fulltext.collect(runtime.hub, papers, tmp_path/'library', limit=1)
    assert first['readable']==1 and not first['records'][0]['reused_local_pdf']
    def fail(*args,**kwargs):
        pytest.fail('Resumed collection attempted network')
    monkeypatch.setattr(runtime.TRANSPORT,'request',fail)
    second=fulltext.collect(runtime.hub, papers, tmp_path/'library', limit=1)
    assert second['readable']==1 and second['records'][0]['reused_local_pdf']
    assert (tmp_path/'library'/'manifest.json').is_file()


def test_network_failure_is_not_subscription_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError('network blocked')
    monkeypatch.setattr(runtime.TRANSPORT,'request',fail)
    body, result=fulltext.retrieve(runtime.hub,'https://publisher.example/paper.pdf')
    assert body is None and result['status']=='network_error'


def test_unpaywall_requires_explicit_contact(monkeypatch):
    monkeypatch.delenv('CHEM_MAT_HUB_UNPAYWALL_EMAIL',raising=False)
    assert fulltext.resolve_unpaywall_pdf('10.1234/a') is None


@pytest.mark.parametrize('status,reason',[(401,'authentication_required'),(403,'access_forbidden'),(404,'not_found'),(429,'rate_limited'),(503,'server_error')])
def test_http_failures_have_actionable_distinct_reasons(monkeypatch,status,reason):
    monkeypatch.setattr(runtime.TRANSPORT,'request',lambda s,m,u,**k:reply(u,'Denied',status=status))
    _,r=fulltext.retrieve(runtime.hub,'https://publisher.example/main.pdf?token=secret')
    assert r['access_summary']['outcome']==reason
    assert r['access_summary']['institutional_entitlement']=='not_verified'
    assert not r['access_summary']['validated_pdf']
    assert 'secret' not in json.dumps(r)


@pytest.mark.parametrize('markup,reason',[
    ('<html>Institutional login. Sign in to access</html>','authentication_required'),
    ('<html>Verify you are human</html>','human_verification_required'),
    ('<html>Purchase access</html>','purchase_access_page'),
    ('<html><nav>Sign in</nav><p>Article abstract</p></html>','missing_pdf_link'),
    ('<script>captchaWidget()</script><p>Article abstract</p>','missing_pdf_link')])
def test_html_access_classification(monkeypatch,markup,reason):
    monkeypatch.setattr(runtime.TRANSPORT,'request',lambda s,m,u,**k:reply(u,markup))
    _,r=fulltext.retrieve(runtime.hub,'https://publisher.example/article')
    assert r['access_summary']['outcome']==reason


@pytest.mark.parametrize('exc,reason',[(requests.ConnectionError('secret'),'connection_failed'),(requests.Timeout('secret'),'timeout'),(requests.exceptions.SSLError('secret'),'tls_error')])
def test_network_errors_distinct_from_entitlement(monkeypatch,exc,reason):
    def fail(*a,**k):raise exc
    monkeypatch.setattr(runtime.TRANSPORT,'request',fail)
    _,r=fulltext.retrieve(runtime.hub,'https://publisher.example/main.pdf')
    assert r['status']=='network_error' and r['access_summary']['outcome']==reason
    assert 'secret' not in json.dumps(r)


def test_success_retains_failed_routes(monkeypatch,pdf):
    monkeypatch.setattr(runtime.hub,'resolve_unpaywall_pdf',lambda _: 'https://repo.example/missing.pdf')
    def fake(s,m,u,**k):
        return reply(u,'not found',status=404) if 'repo.example' in u else reply(u,pdf,'application/pdf')
    monkeypatch.setattr(runtime.TRANSPORT,'request',fake)
    _,r=fulltext.retrieve(runtime.hub,'10.1234/a','10.1234/a')
    assert r['access_summary']['outcome']=='validated_pdf'
    assert 'not_found' in r['access_summary']['reasons']


def test_crossref_metadata_failure_retains_http_status(monkeypatch):
    def fake(s,m,u,**k):
        return reply(u,'forbidden',status=403) if 'api.crossref.org' in u else reply(u,'<p>Abstract only</p>')
    monkeypatch.setattr(runtime.TRANSPORT,'request',fake)
    _,r=fulltext.retrieve(runtime.hub,'10.1234/a','10.1234/a')
    metadata=next(a for a in r['attempts'] if a['origin']=='crossref_metadata')
    assert metadata['http_status']==403 and metadata['reason']=='access_forbidden'
    assert r['status']=='fulltext_unavailable' and r['access_summary']['outcome']=='missing_pdf_link'


def test_collection_keeps_failed_oa_and_doi_routes(monkeypatch,tmp_path):
    def read(target,**kwargs):
        return {'status':'browser_required','access_summary':{'outcome':'access_forbidden'},
                'attempts':[{'host':'example.invalid','origin':'provided_url','http_status':403,'reason':'access_forbidden'}]}
    monkeypatch.setattr(runtime.hub,'deep_read_pdf',read)
    r=fulltext.collect(runtime.hub,[{'doi':'10.1234/a','open_access_pdf':'https://repo.example/a.pdf'}],tmp_path/'collection',1)
    assert len(r['records'][0]['collection_routes'])==2 and r['readable']==0
    saved=json.loads(Path(r['records'][0]['evidence_file']).read_text(encoding='utf-8'))
    assert len(saved['collection_routes'])==2


def test_request_budget_explicit(monkeypatch):
    monkeypatch.setattr(fulltext,'MAX_REQUESTS',1)
    monkeypatch.setattr(runtime.TRANSPORT,'request',lambda s,m,u,**k:reply(u,'<meta name="citation_pdf_url" content="/main.pdf">'))
    _,r=fulltext.retrieve(runtime.hub,'https://publisher.example/article')
    assert r['access_summary']['request_budget_exhausted']


@pytest.mark.parametrize('markup,reason',[('<html>Verify you are human</html>','human_verification_required'),('<html>Institutional login</html>','authentication_required'),('<html>Access denied</html>','access_forbidden')])
def test_403_body_inspection_distinguishes_actual_page(monkeypatch,markup,reason):
    monkeypatch.setattr(runtime.TRANSPORT,'request',lambda s,m,u,**k:reply(u,markup,status=403))
    _,r=fulltext.retrieve(runtime.hub,'https://publisher.example/paper')
    assert r['attempts'][0]['http_status']==403 and r['access_summary']['outcome']==reason
