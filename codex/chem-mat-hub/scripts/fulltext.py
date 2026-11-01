"""Resolve public and campus-IP-authorized PDFs; hand off browser-only access."""
import re
import os
import hashlib
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, quote

import requests
from bs4 import BeautifulSoup

MAX_BYTES = 60_000_000
MAX_REQUESTS = 12

NETWORK_REASONS = {'connection_failed', 'timeout', 'tls_error'}
BROWSER_REASONS = {'authentication_required', 'access_forbidden', 'human_verification_required', 'purchase_access_page'}


def http_reason(status):
    return {400:'invalid_request',401:'authentication_required',403:'access_forbidden',
            404:'not_found',408:'timeout',429:'rate_limited'}.get(status,
            'server_error' if status >= 500 else 'http_error' if status >= 400 else None)


def exception_reason(exc):
    if isinstance(exc, requests.exceptions.SSLError):return 'tls_error'
    if isinstance(exc, requests.Timeout):return 'timeout'
    if isinstance(exc, requests.ConnectionError):return 'connection_failed'
    return 'request_or_processing_error'


def html_reason(markup):
    soup = BeautifulSoup(markup, 'html.parser')
    for tag in soup(['script','style','nav']):tag.decompose()
    visible = soup.get_text(' ', strip=True)
    if re.search(r'verify (?:you are|that you are) (?:a )?human|captcha|checking your browser|just a moment', visible, re.I):
        return 'human_verification_required'
    if soup.find('input',attrs={'type':'password'}) or re.search(r'institutional login|sign in to access|log in to access|authentication required',visible,re.I):
        return 'authentication_required'
    if re.search(r'purchase access|purchase this article|rent this article',visible,re.I):
        return 'purchase_access_page'
    if re.search(r'access denied',visible,re.I):return 'access_forbidden'
    return 'missing_pdf_link'


def access_summary(attempts, *, success=False, budget_exhausted=False):
    reasons=list(dict.fromkeys(a['reason'] for a in attempts if a.get('reason')))
    content=[a for a in attempts if a.get('attempted',True) and a.get('origin')!='crossref_metadata']
    content_reasons={a.get('reason') for a in content}
    priority=['human_verification_required','authentication_required','access_forbidden','purchase_access_page',
              'rate_limited','tls_error','timeout','connection_failed','server_error','invalid_pdf',
              'encrypted_or_empty_pdf','too_large','not_found','missing_pdf_link','non_pdf_response']
    primary='validated_pdf' if success else next((r for r in priority if r in content_reasons),'fulltext_unavailable')
    if not success and content and all(a.get('reason') in NETWORK_REASONS for a in content):
        primary=next((a['reason'] for a in content), 'connection_failed')
    if budget_exhausted and not success:
        reasons.append('request_budget_exhausted')
        if primary=='fulltext_unavailable':primary='request_budget_exhausted'
    actions={
        'authentication_required':'Open publisher through library browser session; user completes sign-in/MFA if requested.',
        'access_forbidden':'Inspect publisher in browser. HTTP 403 does not prove absence of institutional subscription.',
        'human_verification_required':'Open publisher in browser; user handles any human-verification challenge.',
        'purchase_access_page':'Check institutional browser access; purchase page does not prove absence of subscription.',
        'rate_limited':'Retry after provider rate limit clears; do not treat as no matching paper.',
        'connection_failed':'Check network or execution permissions and retry; subscription access was not tested.',
        'timeout':'Retry connection later; timeout does not establish access entitlement.',
        'tls_error':'Check certificate/network configuration; retain TLS verification.',
        'missing_pdf_link':'Inspect publisher browser page for main-paper PDF; resolver found no usable PDF link.',
        'validated_pdf':'Readable PDF retrieved; institutional entitlement remains unverified.'}
    return {'outcome':primary,'reasons':reasons,'validated_pdf':success,
            'request_budget_exhausted':bool(budget_exhausted),
            'institutional_entitlement':'not_verified',
            'next_action':actions.get(primary,'Inspect route diagnostics and obtain a readable main-paper PDF before analysis.')}


def safe_url(url):
    parts = urlsplit(str(url))
    return urlunsplit((parts.scheme, parts.hostname or '', parts.path, '', ''))


def http_url(url):
    return isinstance(url, str) and url.startswith(('https://', 'http://')) and not urlsplit(url).username


def pdf_links(html, base):
    soup = BeautifulSoup(html, 'html.parser')
    found = []
    for tag in soup.find_all('meta'):
        if (tag.get('name') or tag.get('property') or '').lower() in ('citation_pdf_url', 'wkhealth_pdf_url', 'eprints.document_url'):
            found.append(urljoin(base, tag.get('content', '')))
    for tag in soup.find_all('link'):
        if tag.get('type', '').lower() == 'application/pdf':
            found.append(urljoin(base, tag.get('href', '')))
    for tag in soup.find_all('a', href=True):
        href = tag['href']
        label = tag.get_text(' ', strip=True)
        # Avoid collecting cited articles and supplementary PDFs as main paper.
        if re.search(r'supplement|supporting|reference', href + ' ' + label, re.I):
            continue
        if re.search(r'\.pdf(?:$|[?#])|/(?:epdf|pdf|pdfdirect)/', href, re.I) or re.fullmatch(r'(?:download\s+)?(?:full[ -]?text\s+)?pdf(?:\s+download)?', label, re.I):
            found.append(urljoin(base, href))
    return list(dict.fromkeys(u for u in found if http_url(u)))[:8]


def html_redirects(html, base):
    soup = BeautifulSoup(html, 'html.parser')
    redirects = []
    for tag in soup.find_all('meta'):
        if tag.get('http-equiv', '').lower() == 'refresh':
            match = re.search(r'url\s*=\s*(.+)$', tag.get('content', ''), re.I)
            if match:
                url = urljoin(base, match.group(1).strip().strip("\"'"))
                if http_url(url):
                    redirects.append(url)
    return redirects[:2]


def resolve_unpaywall_pdf(doi):
    # Explicit contact configuration only; never silently transmit a stored address.
    email = os.environ.get('CHEM_MAT_HUB_UNPAYWALL_EMAIL')
    if not email:
        return None
    try:
        r = requests.get('https://api.unpaywall.org/v2/' + quote(doi, safe=''), params={'email': email}, timeout=(10, 15))
        r.raise_for_status()
        location = r.json().get('best_oa_location') or {}
        return location.get('url_for_pdf') or location.get('url')
    except requests.RequestException:
        return None


def persist_pdf(body, destination):
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise FileExistsError('Refusing to overwrite a different existing PDF')
    else:
        with path.open('xb') as stream:
            stream.write(body)
    return {'saved_pdf': str(path.resolve()), 'pdf_sha256': hashlib.sha256(body).hexdigest()}


def collect(hub, articles, directory, limit=5, *, ocr=False):
    """Bounded, serial downloads with resumable local evidence files and manifest."""
    import json
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for article in articles[:limit]:
        doi = article.get('doi')
        target = article.get('open_access_pdf') or doi
        row = {'title': article.get('title'), 'doi': doi}
        if not target:
            records.append({**row, 'status': 'no_fulltext_target'})
            continue
        identifier = hashlib.sha256(str(doi or safe_url(target)).encode()).hexdigest()[:20]
        pdf = directory / (identifier + '.pdf')
        evidence_file = directory / (identifier + '.json')
        reused = pdf.is_file()
        result = hub.deep_read_pdf(str(pdf) if reused else target, ocr=ocr, save_pdf=str(pdf))
        routes=[{'target_kind':'local_pdf' if reused else 'open_access_url' if target != doi else 'doi',
                 'status':result.get('status'),'access_summary':result.get('access_summary') or result.get('retrieval',{}).get('access_summary'),
                 'attempts':result.get('attempts') or result.get('retrieval',{}).get('attempts',[])}]
        if result.get('status') not in ('success', 'partial') and doi and target != doi and not reused:
            result = hub.deep_read_pdf(doi, ocr=ocr, save_pdf=str(pdf))
            routes.append({'target_kind':'doi','status':result.get('status'),
                           'access_summary':result.get('access_summary') or result.get('retrieval',{}).get('access_summary'),
                           'attempts':result.get('attempts') or result.get('retrieval',{}).get('attempts',[])})
        result['collection_routes']=routes
        evidence_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        row.update({k: result[k] for k in ('status', 'pages_read', 'saved_pdf', 'pdf_sha256', 'retrieval', 'browser_handoff', 'access_summary', 'attempts', 'collection_routes') if k in result})
        row.update({'evidence_file': str(evidence_file.resolve()), 'reused_local_pdf': reused})
        records.append(row)
    manifest = {'requested': min(limit, len(articles)), 'readable': sum(r['status'] in ('success', 'partial') for r in records), 'records': records}
    (directory/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return manifest


def retrieve(hub, target, doi=None):
    """Return validated PDF bytes and public diagnostics, never browser cookies."""
    attempts, queue, seen = [], [], set()
    landing = 'https://doi.org/' + doi if doi else target
    session = requests.Session()
    session._chem_fulltext = True  # no shared HTTP cache: preserve redirect/cookie state
    session.headers.update(hub.HEADERS)
    session.headers['Accept'] = 'application/pdf,text/html;q=0.9,*/*;q=0.8'

    def enqueue(url, origin, expand=True):
        if http_url(url) and url not in seen and not any(item[0] == url for item in queue):
            queue.append((url, origin, expand))

    def fetch(url, origin):
        report = {'host': urlsplit(url).hostname, 'origin': origin, 'attempted':True}
        attempts.append(report)
        try:
            with session.get(url, timeout=(10, 30), stream=True) as response:
                report['http_status'] = response.status_code
                report['response_host'] = urlsplit(response.url).hostname
                reason=http_reason(response.status_code)
                if reason:report['reason']=reason
                if response.status_code in (401,403):
                    # Bounded inspection can distinguish an actual login/challenge page
                    # from a bare denial; neither establishes subscription entitlement.
                    preview=bytearray()
                    for chunk in response.iter_content(8192):
                        preview.extend(chunk[:max(0,65536-len(preview))])
                        if len(preview)>=65536:break
                    if 'html' in response.headers.get('Content-Type','').lower() or bytes(preview).lstrip().startswith(b'<'):
                        detected=html_reason(bytes(preview).decode(response.encoding or 'utf-8',errors='replace'))
                        if detected in BROWSER_REASONS:report['reason']=detected
                response.raise_for_status()
                if int(response.headers.get('Content-Length') or 0) > MAX_BYTES:
                    report['outcome'] = 'too_large'
                    report['reason'] = 'too_large'
                    return None, response.url, ''
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        report['outcome'] = 'too_large'
                        report['reason'] = 'too_large'
                        return None, response.url, ''
                    chunks.append(chunk)
                body = b''.join(chunks)
                content_type = response.headers.get('Content-Type', '').lower()
                if body[:1024].lstrip().startswith(b'%PDF-'):
                    try:
                        with hub.fitz.open(stream=body, filetype='pdf') as document:
                            if document.is_encrypted or not len(document):
                                report['outcome'] = 'encrypted_or_empty_pdf'
                                report['reason'] = 'encrypted_or_empty_pdf'
                                return None, response.url, ''
                        report['outcome'] = 'validated_pdf'
                        report['reason'] = 'validated_pdf'
                        return body, response.url, ''
                    except Exception:
                        report['outcome'] = 'invalid_pdf'
                        report['reason'] = 'invalid_pdf'
                        return None, response.url, ''
                html = body.decode(response.encoding or 'utf-8', errors='replace') if 'html' in content_type or body.lstrip().startswith((b'<', b'<!')) else ''
                report['outcome'] = 'html_page' if html else 'non_pdf_response'
                report['reason'] = html_reason(html) if html else 'non_pdf_response'
                if html and (pdf_links(html,response.url) or html_redirects(html,response.url)) and report['reason']=='missing_pdf_link':
                    report['reason']='html_link_found'
                return None, response.url, html
        except Exception as exc:
            report['outcome'] = 'request_failed'
            report['error_type'] = type(exc).__name__
            report.setdefault('reason',exception_reason(exc))
            return None, url, ''

    try:
        if doi:
            # Try OA first, but absence never prevents publisher lookup.
            try:
                enqueue(hub.resolve_unpaywall_pdf(doi), 'unpaywall')
            except Exception:
                pass
        enqueue(landing, 'doi_publisher' if doi else 'provided_url')
        crossref_added = False
        while len(attempts) < MAX_REQUESTS:
            if not queue and doi and not crossref_added:
                crossref_added = True
                metadata_report={'host':'api.crossref.org','origin':'crossref_metadata','attempted':True}
                attempts.append(metadata_report)
                try:
                    with session.get('https://api.crossref.org/works/' + quote(doi, safe=''), timeout=(10, 20), headers={'Accept': 'application/json'}) as metadata:
                        metadata_report['http_status']=metadata.status_code
                        reason=http_reason(metadata.status_code)
                        if reason:metadata_report['reason']=reason
                        metadata.raise_for_status()
                        before=len(queue)
                        for link in metadata.json().get('message', {}).get('link', []):
                            if link.get('content-type') == 'application/pdf':
                                enqueue(link.get('URL'), 'crossref_fulltext', False)
                        metadata_report['outcome']='metadata_pdf_links_found' if len(queue)>before else 'metadata_no_pdf_link'
                        metadata_report['reason']='metadata_link_found' if len(queue)>before else 'missing_pdf_link'
                except Exception as exc:
                    metadata_report.update(outcome='request_failed',error_type=type(exc).__name__)
                    metadata_report.setdefault('reason',exception_reason(exc))
            if not queue:
                break
            if len(attempts)>=MAX_REQUESTS:break
            url, origin, expand = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            body, final_url, html = fetch(url, origin)
            if body:
                return body, {'status': 'success', 'source_pdf_url': safe_url(final_url), 'retrieval_route': origin,
                              'access_basis': 'local_network_or_public_access; institutional_entitlement_not_verified', 'attempts': attempts,
                              'access_summary':access_summary(attempts,success=True)}
            if html and expand:
                if origin in ('doi_publisher', 'provided_url', 'publisher_html_redirect'):
                    landing = safe_url(final_url)
                for redirect in html_redirects(html, final_url):
                    enqueue(redirect, 'publisher_html_redirect')
                for link in pdf_links(html, final_url):
                    enqueue(link, 'publisher_pdf_link', False)
        summary=access_summary(attempts,budget_exhausted=bool(queue) and len(attempts)>=MAX_REQUESTS)
        network_failed=summary['outcome'] in NETWORK_REASONS
        blocked=any(a.get('reason') in BROWSER_REASONS and a.get('origin')!='crossref_metadata' for a in attempts)
        return None, {'status': 'network_error' if network_failed else 'browser_required' if blocked else 'fulltext_unavailable',
                      'message': summary['next_action'], 'access_summary':summary,
                      'attempts': attempts,
                      'browser_handoff': {'publisher_url': safe_url(landing),
                                          'library_access_url': 'https://lib.arizona.edu/find/connect/proxy-url',
                                          'next_step': 'Open publisher in existing browser session. If needed, use UofA library link generator and complete NetID/MFA yourself. Download main paper PDF, then pass local path to --deep-read.'}}
    finally:
        session.close()
