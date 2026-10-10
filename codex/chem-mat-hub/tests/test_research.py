import dataclasses
import json
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import codex_hub as runtime
import research
import sync_upstream
hub = runtime.hub


def response(payload, status=200):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(payload).encode()
    r.headers['Content-Type'] = 'application/json'
    r.encoding = 'utf-8'
    return r


@pytest.fixture(autouse=True)
def isolate_network(monkeypatch, tmp_path):
    runtime.DIAGNOSTICS.clear()
    monkeypatch.setattr(runtime.TRANSPORT, 'cache_path', tmp_path / 'cache.sqlite3')
    monkeypatch.setattr(runtime.TRANSPORT, 'no_cache', True)
    monkeypatch.setattr(runtime.TRANSPORT, 'retries', 0)
    def no_network(*args, **kwargs):
        raise AssertionError('Unexpected network call in local test')
    monkeypatch.setattr(runtime.TRANSPORT, 'request', no_network)
    monkeypatch.setattr(research.time, 'sleep', lambda _: None)


@pytest.mark.parametrize('source', research.LITERATURE)
def test_real_adapter_pagination(source, monkeypatch):
    calls = []
    def fake(session, method, url, **kwargs):
        params = dict(parse_qs(urlsplit(url).query))
        params.update(kwargs.get('params') or {})
        path = urlsplit(url).path
        # Follow-up PubMed summaries and Scopus abstracts are not search pages.
        if 'esummary' in path:
            ids = str(params['id']).split(',')
            return response({'result': {i: {'title': 'Ionogel ' + i, 'pubdate': '2025', 'articleids': [{'idtype': 'doi', 'value': '10.1234/' + i}]} for i in ids}})
        if '/abstract/doi/' in path:
            return response({'abstracts-retrieval-response': {'coredata': {'dc:description': 'Conductivity study'}}})
        count, offset = {
            'openalex': ('per_page','page'), 'semantic-scholar': ('limit','offset'),
            'europe-pmc': ('pageSize','cursorMark'), 'arxiv': ('max_results','start'),
            'crossref': ('rows','offset'), 'scopus': ('count','start'), 'osti': ('rows','page'),
            'doaj': ('pageSize','page'), 'datacite': ('page[size]','page[number]'),
            'pubmed': ('retmax','retstart'), 'core': ('limit','offset'), 'zenodo': ('size','page')
        }[source]
        assert int(params[count]) == 2
        p = len(calls)
        assert str(params[offset]) == str('*' if p == 0 else 'next') if source == 'europe-pmc' else int(params[offset]) == (p * 2 if offset in ('offset','start','retstart') else p+1)
        calls.append(params)
        ids = [str(p*2+i) for i in range(2)]
        records = [{'title': 'Ionogel '+i, 'doi': '10.1234/'+i, 'year': 2025} for i in ids]
        if source == 'openalex':
            return response({'results': [{'title': r['title'], 'doi': r['doi'], 'publication_year': 2025, 'primary_location': {}, 'open_access': {}} for r in records]})
        if source == 'semantic-scholar':
            return response({'data': [{'title':r['title'],'externalIds':{'DOI':r['doi']},'year':2025} for r in records]})
        if source == 'europe-pmc':
            return response({'nextCursorMark': 'next' if p == 0 else 'last', 'resultList': {'result': [{'title':r['title'],'doi':r['doi'],'pubYear':'2025'} for r in records]}})
        if source == 'arxiv':
            r = response({})
            r._content = ('<feed xmlns="http://www.w3.org/2005/Atom">'+''.join('<entry><title>'+x['title']+'</title><id>https://arxiv.org/abs/'+i+'</id><published>2025-01-01</published><summary>Ionogel</summary></entry>' for x,i in zip(records,ids))+'</feed>').encode()
            return r
        if source == 'crossref':
            return response({'message': {'items': [{'title':[r['title']], 'DOI':r['doi'], 'created':{'date-parts':[[2025]]}} for r in records]}})
        if source == 'scopus':
            return response({'search-results': {'entry': [{'dc:title':r['title'],'prism:doi':r['doi'],'prism:coverDate':'2025-01-01'} for r in records]}})
        if source == 'osti':
            return response([dict(r, publication_date='2025-01-01') for r in records])
        if source == 'doaj':
            return response({'results': [{'bibjson':dict(r, identifier=[{'type':'doi','id':r['doi']}])} for r in records]})
        if source == 'datacite':
            return response({'data':[{'attributes': dict(r, titles=[{'title':r['title']}], publicationYear=2025)} for r in records]})
        if source == 'pubmed':
            return response({'esearchresult': {'idlist':ids}})
        if source == 'core':
            return response({'results':[dict(r,yearPublished=2025) for r in records]})
        if source == 'zenodo':
            return response({'hits': {'hits': [{'metadata':dict(r,publication_date='2025-01-01'), 'doi':r['doi']} for r in records]}})
    monkeypatch.setattr(runtime.TRANSPORT, 'request', fake)
    config = research.Search(per_source=3,page_size=2,max_pages=3,enrich=0)
    result = research.search(hub, runtime, 'ionogel', config=dataclasses.replace(config,sources=(source,)))
    assert len(calls) == 2
    assert result['articles_returned'] == 3
    assert result['pagination'][0]['stop_reason'] == 'per_source_limit_reached'


def test_filters_synonyms_ranking_and_dedup():
    config = research.Search(year_from=2020,year_to=2026,phrases=('ionic conductivity',),exclude=('hydrogel',),synonyms=('PBO|Zylon|polybenzoxazole',))
    assert research.variants('PBO ionogel',config.synonyms) == ['PBO ionogel','Zylon ionogel','polybenzoxazole ionogel']
    valid = {'title':'Zylon ionogel ionic conductivity','year':2025,'doi':'10.1234/test','source_database':'A'}
    assert research.accepted(valid,config)
    assert not research.accepted(dict(valid,year=None),config)
    assert not research.accepted(dict(valid,year=2019),config)
    assert not research.accepted(dict(valid,title=valid['title']+' hydrogel'),config)
    assert not research.accepted(dict(valid,title='Zylon ionogel'),config)
    assert research.relevance('PBO ionogel',valid,config.synonyms)['score_percent'] == 100
    assert research.relevance('PBO ionogel',valid,config.synonyms)['all_query_groups_matched']
    assert not research.relevance('PBO ionogel',{'title':'cellulose ionogel'},config.synonyms)['all_query_groups_matched']
    assert research.relevance('PBO ionogel',{'title':'unrelated'},config.synonyms)['score_percent'] == 0
    merged = research.merge_articles([valid, dict(valid,doi='https://doi.org/10.1234/TEST',source_database='B',abstract='New abstract')])
    assert len(merged) == 1 and merged[0]['source_databases'] == ['A','B'] and merged[0]['abstract'] == 'New abstract'


def test_contextual_evidence():
    text = 'Sample A was tested at 25 °C. Tensile strength was 12 MPa; storage modulus was 3 MPa. Degradation temperature was 350 °C. Ionic conductivity was 2.3 mS/cm.'
    records = research.evidence(text,page=4,source='pdf')
    pairs = {(r['property'],r['value_text']) for r in records}
    assert ('unclassified_temperature','25') in pairs
    assert ('tensile_strength','12') in pairs
    assert ('storage_modulus','3') in pairs
    assert ('degradation_temperature','350') in pairs
    assert ('ionic_conductivity','2.3') in pairs
    assert all(r['page'] == 4 and r['evidence_quote'] and r['sample_context'] for r in records)
    props = hub.extract_material_properties('Tensile strength was 12 MPa. Sample tested at 25 °C.')
    assert not props.get('mechanical_modulus') and not props.get('thermal_properties')


def test_retry_cache_and_auth_isolation(monkeypatch,tmp_path):
    attempts = []
    def fake(*args,**kwargs):
        attempts.append(1)
        return response({'ok':True},503 if len(attempts) == 1 else 200)
    local = threading.local()
    local.trace = []
    t = research.Transport(fake,local)
    t.cache_path = tmp_path/'cache.sqlite3'
    session = requests.Session()
    assert t(session,'GET','https://example.org/data',headers={'x-api-key':'secret-one'}).status_code == 200
    assert len(attempts) == 2
    assert t(session,'GET','https://example.org/data',headers={'x-api-key':'secret-one'}).status_code == 200
    assert len(attempts) == 2 and local.trace[-1]['cache'] == 'hit'
    t(session,'GET','https://example.org/data',headers={'x-api-key':'secret-two'})
    assert len(attempts) == 3
    assert b'secret-one' not in t.cache_path.read_bytes()
    assert 'secret' not in json.dumps(local.trace)
    t.cache_ttl = 0
    t(session,'GET','https://example.org/data',headers={'x-api-key':'secret-one'})
    assert len(attempts) == 4


def test_auth_failure_not_retried(monkeypatch):
    calls=[]
    def fake(*a,**k):
        calls.append(1)
        return response({},401)
    t=research.Transport(fake,threading.local())
    t.no_cache=True
    assert t(requests.Session(),'GET','https://example.org').status_code == 401
    assert len(calls)==1


@pytest.mark.parametrize('payload,status', [({'message':{'items':[]}},'no_matches'), ({'unexpected':'changed_schema'},'adapter_parse_failed')])
def test_empty_search_distinguished_from_parse_failure(payload,status,monkeypatch):
    monkeypatch.setattr(runtime.TRANSPORT,'request',lambda *a,**k:response(payload))
    result=research.search(hub,runtime,'ionogel',config=research.Search(sources=('crossref',),enrich=0))
    assert result['articles_returned']==0
    assert result['source_diagnostics'][0]['status']==status


def test_failed_material_query_not_reported_as_not_found(monkeypatch):
    monkeypatch.setattr(runtime.TRANSPORT,'request',lambda *a,**k:response({},502))
    result=runtime.query_source('oqmd','SiO2')
    assert result['status']=='error' and result['source_status']=='request_failed'


def test_full_pdf_tables_and_page_evidence(tmp_path):
    doc=hub.fitz.open()
    for i in range(31):
        p=doc.new_page()
        p.insert_text((72,72),'Page '+str(i+1)+'. Storage modulus was 3 MPa.',fontsize=12)
    # Ruled table for deterministic detection.
    p=doc[30]
    for x in (72,220,370):
        p.draw_line((x,120),(x,180))
    for y in (120,150,180):
        p.draw_line((72,y),(370,y))
    p.insert_text((80,140),'Sample')
    p.insert_text((230,140),'Modulus')
    p.insert_text((80,170),'A')
    p.insert_text((230,170),'3 MPa')
    path=tmp_path/'paper.pdf'
    doc.save(path)
    doc.close()
    result=hub.deep_read_pdf(str(path))
    assert result['pages_read']==31 and not result['truncated']
    assert any(r['page']==31 for r in result['evidence_candidates'])
    assert result['tables'] and result['tables'][0]['page']==31
    limited=hub.deep_read_pdf(str(path),max_pages=2)
    assert limited['pages_read']==2 and limited['truncated'] and limited['status']=='partial'


def test_scanned_pdf_ocr(tmp_path):
    source=hub.fitz.open()
    p=source.new_page()
    p.insert_text((72,100),'Ionic conductivity was 2.3 mS/cm.',fontsize=20)
    image=p.get_pixmap(dpi=200).tobytes('png')
    scan=hub.fitz.open()
    p=scan.new_page()
    p.insert_image(p.rect,stream=image)
    path=tmp_path/'scan.pdf'
    scan.save(path)
    scan.close()
    source.close()
    result=hub.deep_read_pdf(str(path),ocr=True)
    assert result['pages'][0]['method']=='ocr',result['warnings']
    assert 'conductivity' in result['pages'][0]['text'].lower()


def test_exports_no_fabricated_year_or_doi(tmp_path,monkeypatch):
    monkeypatch.setattr(hub,'fetch_doi_citation_metadata',lambda *a:None)
    bib,ris=tmp_path/'papers.bib',tmp_path/'papers.ris'
    summary=hub.export_zotero_references([{'title':'Unknown year & {sample}','authors':['A Author'],'doi':'https://arxiv.org/abs/1234.5678'}],str(bib),str(ris))
    assert summary['bibtex_count']==summary['ris_count']==1
    assert 'year=' not in bib.read_text() and 'PY  -' not in ris.read_text()
    assert 'DO  -' not in ris.read_text() and 'UR  - https://arxiv.org' in ris.read_text()
    assert r'\&' in bib.read_text() and r'\{sample\}' in bib.read_text()


def test_walden_invariant():
    assert hub.calculate_walden_ionicity(9.1,32,1.52,391.31)['walden_metrics']['molar_conductivity_Lambda_S_cm2_mol']==2.3427
    assert hub.calculate_walden_ionicity(-1,32,1.52,391.31)['status']=='error'


def test_guarded_sync(tmp_path,monkeypatch):
    # Reconstruct a local upstream fixture; no developer-machine manifest needed.
    original=sync_upstream.ENGINE.read_text(encoding='utf-8')
    loader_start=original.index('# Process environment wins;')
    loader_end=original.index('load_dotenv(os.path.expanduser("~/.env"), override=False)')+len('load_dotenv(os.path.expanduser("~/.env"), override=False)')
    original=original[:loader_start]+'load_dotenv()\nload_dotenv(os.path.expanduser("~/.env"))'+original[loader_end:]
    validation_start=original.index('        values = [conductivity_mS_cm, viscosity_mPa_s, temperature_K]')
    validation_end=original.index('        kappa_S_cm = float(conductivity_mS_cm) * 1e-3',validation_start)
    original=original[:validation_start]+original[validation_end:]
    upstream=tmp_path/'source.py'
    upstream.write_text(original,encoding='utf-8')
    engine=tmp_path/'engine.py'
    engine.write_text(sync_upstream.adapt(upstream.read_text(encoding='utf-8')),encoding='utf-8')
    manifest=tmp_path/'upstream.json'
    manifest.write_text(json.dumps({'upstream_path':str(upstream),'upstream_sha256':sync_upstream.digest(upstream),'managed_engine_sha256':sync_upstream.digest(engine)}))
    monkeypatch.setattr(sync_upstream,'MANIFEST',manifest)
    monkeypatch.setattr(sync_upstream,'ENGINE',engine)
    assert sync_upstream.refresh()['status']=='unchanged'
    upstream.write_text(upstream.read_text(encoding='utf-8')+'\n# upstream update\n',encoding='utf-8')
    assert sync_upstream.check()['upstream_changed']
    assert sync_upstream.refresh()['status']=='updated'
    assert '# upstream update' in engine.read_text(encoding='utf-8')
    engine.write_text(engine.read_text(encoding='utf-8')+'\n# local edit\n',encoding='utf-8')
    assert sync_upstream.refresh()['status']=='blocked'


def test_bridge_signatures_and_validation(monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    import chatgpt_api_server as bridge
    client=TestClient(bridge.app)
    monkeypatch.setattr(bridge.research,'search',lambda hub,runtime,query,config:{'query':query,'max_results':config.max_results})
    assert client.get('/literature',params={'query':'ionogel','max_results':21}).json()=={'query':'ionogel','max_results':21}
    assert client.get('/literature',params={'query':'x','year_from':2026,'year_to':2020}).status_code==422
    monkeypatch.setattr(hub,'explore_citation_graph',lambda seed,mode:{'seed':seed,'mode':mode})
    assert client.get('/citation-graph',params={'seed_doi':'10.1234/test','mode':'forward'}).json()['seed']=='10.1234/test'
    assert client.get('/citation-graph',params={'seed_doi':'10.1234/test','mode':'bad'}).status_code==422
    assert client.get('/polymer',params={'name':'zylon'}).json()['status']=='success'
    assert client.get('/coolprop',params={'fluid':'Water'}).json()['status']=='success'
    assert client.get('/walden',params={'conductivity_ms_cm':9.1,'viscosity_mpa_s':32,'density_g_cm3':1.52,'molar_mass':391.31}).json()['walden_metrics']['molar_conductivity_Lambda_S_cm2_mol']==2.3427
    assert '/literature' in client.get('/openapi.json').json()['paths']
    assert client.get('/walden',params={'conductivity_ms_cm':-1,'viscosity_mpa_s':32}).status_code==422
    assert client.get('/deep-read',params={'doi_or_url':str(tmp_path/'local.pdf')}).status_code==422


def test_legacy_unpaywall_requires_opt_in(monkeypatch):
    import unified_chem_mat_hub as legacy
    monkeypatch.delenv('CHEM_MAT_HUB_UNPAYWALL_EMAIL', raising=False)
    calls=[]
    def unexpected(*args, **kwargs):
        calls.append((args,kwargs))
        raise AssertionError('Contact must not be sent without configuration')
    monkeypatch.setattr(legacy.requests, 'get', unexpected)
    assert legacy.resolve_unpaywall_pdf('10.1234/example') is None
    assert not calls
    assert 'mailto:' not in legacy.HEADERS['User-Agent']


def test_sync_removes_upstream_contact():
    source='import os\nimport math\nfrom dotenv import load_dotenv\nload_dotenv()\nload_dotenv(os.path.expanduser("~/.env"))\n'
    source+='HEADERS = {"User-Agent": "Antigravity-ResearchHub/1.0 (mailto:legacy@example.invalid)"}\n'
    source+='def sample():\n        kappa_S_cm = float(conductivity_mS_cm) * 1e-3\n'
    source+='        r = requests.get(f"https://api.unpaywall.org/v2/{clean_doi}?email=legacy@example.invalid", timeout=4)\n'
    adapted=sync_upstream.adapt(source)
    assert 'legacy@example.invalid' not in adapted
    assert 'CHEM_MAT_HUB_UNPAYWALL_EMAIL' in adapted
