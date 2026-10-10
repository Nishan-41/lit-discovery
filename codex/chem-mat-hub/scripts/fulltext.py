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
        if result.get('status') not in ('success', 'partial') and doi and target != doi and not reused:
            result = hub.deep_read_pdf(doi, ocr=ocr, save_pdf=str(pdf))
        evidence_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        row.update({k: result[k] for k in ('status', 'pages_read', 'saved_pdf', 'pdf_sha256', 'retrieval', 'browser_handoff') if k in result})
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
    blocked = False

    def enqueue(url, origin, expand=True):
        if http_url(url) and url not in seen and not any(item[0] == url for item in queue):
            queue.append((url, origin, expand))

    def fetch(url, origin):
        nonlocal blocked
        report = {'host': urlsplit(url).hostname, 'origin': origin}
        attempts.append(report)
        try:
            with session.get(url, timeout=(10, 30), stream=True) as response:
                report['http_status'] = response.status_code
                if response.status_code in (401, 403):
                    blocked = True
                response.raise_for_status()
                if int(response.headers.get('Content-Length') or 0) > MAX_BYTES:
                    report['outcome'] = 'too_large'
                    return None, response.url, ''
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        report['outcome'] = 'too_large'
                        return None, response.url, ''
                    chunks.append(chunk)
                body = b''.join(chunks)
                content_type = response.headers.get('Content-Type', '').lower()
                if body[:1024].lstrip().startswith(b'%PDF-'):
                    try:
                        with hub.fitz.open(stream=body, filetype='pdf') as document:
                            if document.is_encrypted or not len(document):
                                report['outcome'] = 'encrypted_or_empty_pdf'
                                return None, response.url, ''
                        report['outcome'] = 'validated_pdf'
                        return body, response.url, ''
                    except Exception:
                        report['outcome'] = 'invalid_pdf'
                        return None, response.url, ''
                html = body.decode(response.encoding or 'utf-8', errors='replace') if 'html' in content_type or body.lstrip().startswith((b'<', b'<!')) else ''
                report['outcome'] = 'html_page' if html else 'non_pdf_response'
                if html and re.search(r'captcha|access denied|institutional login|sign in to access|purchase access|verify you are human', html, re.I):
                    blocked = True
                return None, response.url, html
        except Exception as exc:
            report['outcome'] = 'request_failed'
            report['error_type'] = type(exc).__name__
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
                try:
                    with session.get('https://api.crossref.org/works/' + quote(doi, safe=''), timeout=(10, 20), headers={'Accept': 'application/json'}) as metadata:
                        metadata.raise_for_status()
                        for link in metadata.json().get('message', {}).get('link', []):
                            if link.get('content-type') == 'application/pdf':
                                enqueue(link.get('URL'), 'crossref_fulltext', False)
                except Exception as exc:
                    attempts.append({'host': 'api.crossref.org', 'origin': 'crossref_metadata', 'outcome': 'request_failed', 'error_type': type(exc).__name__})
            if not queue:
                break
            url, origin, expand = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            body, final_url, html = fetch(url, origin)
            if body:
                return body, {'status': 'success', 'source_pdf_url': safe_url(final_url), 'retrieval_route': origin,
                              'access_basis': 'local_network_or_public_access; institutional_entitlement_not_verified', 'attempts': attempts}
            if html and expand:
                if origin in ('doi_publisher', 'provided_url', 'publisher_html_redirect'):
                    landing = safe_url(final_url)
                for redirect in html_redirects(html, final_url):
                    enqueue(redirect, 'publisher_html_redirect')
                for link in pdf_links(html, final_url):
                    enqueue(link, 'publisher_pdf_link', False)
        network_failed = attempts and all(a.get('error_type') in ('ConnectionError', 'Timeout', 'ConnectTimeout', 'ReadTimeout') for a in attempts)
        return None, {'status': 'network_error' if network_failed else 'browser_required' if blocked else 'fulltext_unavailable',
                      'message': 'No validated PDF retrieved. Use publisher/library browser access, then read downloaded local PDF.',
                      'attempts': attempts,
                      'browser_handoff': {'publisher_url': safe_url(landing),
                                          'library_access_url': 'https://lib.arizona.edu/find/connect/proxy-url',
                                          'next_step': 'Open publisher in existing browser session. If needed, use UofA library link generator and complete NetID/MFA yourself. Download main paper PDF, then pass local path to --deep-read.'}}
    finally:
        session.close()
