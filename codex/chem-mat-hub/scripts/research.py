"""Search controls and evidence extraction layered over upstream database adapters."""
import concurrent.futures
from contextlib import closing
import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

LITERATURE = ('openalex', 'semantic-scholar', 'europe-pmc', 'arxiv', 'crossref',
              'scopus', 'osti', 'doaj', 'datacite', 'pubmed', 'core', 'zenodo')
STATE = threading.local()
RATE_LOCK = threading.Lock()
LAST_CALL = {}


@dataclasses.dataclass(frozen=True)
class Search:
    max_results: int = 50
    per_source: int = 30
    page_size: int = 20
    max_pages: int = 10
    year_from: int | None = None
    year_to: int | None = None
    phrases: tuple = ()
    exclude: tuple = ()
    synonyms: tuple = ()
    sources: tuple = LITERATURE
    enrich: int = 8
    require_all: bool = False
    min_relevance: int = 1

    def validate(self):
        for name in ('max_results', 'per_source', 'page_size', 'max_pages'):
            if getattr(self, name) <= 0:
                raise ValueError(f'{name} must be positive')
        if self.page_size > 100:
            raise ValueError('page_size must be <= 100 (portable provider limit)')
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError('year_from must be <= year_to')
        if self.enrich < 0:
            raise ValueError('enrich must be >= 0')
        if not 0 <= self.min_relevance <= 100:
            raise ValueError('min_relevance must be 0..100')
        if not self.sources or any(s not in LITERATURE for s in self.sources):
            raise ValueError('Invalid literature source')
        for group in self.synonyms:
            if len(group.split('|')) < 2 or any(not x.strip() for x in group.split('|')):
                raise ValueError('Synonym groups require at least two terms: PBO|Zylon')
        return self


def variants(query, synonyms):
    values = [query]
    for group in synonyms:
        terms = [x.strip() for x in group.split('|')]
        original = list(values)
        for text in original:
            for term in terms:
                if re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, re.I):
                    for other in terms:
                        replacement = re.sub(r'(?<!\w)' + re.escape(term) + r'(?!\w)', lambda _: other, text, flags=re.I)
                        if replacement not in values:
                            values.append(replacement)
                            if len(values) > 16:
                                raise ValueError('Synonym expansion exceeds 16 queries; narrow groups')
    return values


def normalize_doi(value):
    if not value:
        return None
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', str(value).strip(), flags=re.I)
    return value.lower() if re.match(r'^10\.\d{4,9}/\S+$', value) else None


def identity(article):
    doi = normalize_doi(article.get('doi'))
    return ('doi', doi) if doi else ('title', re.sub(r'\W+', '', article.get('title', '').casefold()))


def merge_articles(articles):
    merged = []
    by_doi, by_title = {}, {}
    for raw in articles:
        a = dict(raw)
        title_key = re.sub(r'\W+', '', a.get('title', '').casefold())
        if not title_key:
            continue
        doi = normalize_doi(a.get('doi'))
        target = by_doi.get(doi) if doi else None
        if target is None:
            # Different genuine DOIs may share generic titles; do not collapse them.
            candidate = by_title.get(title_key)
            if candidate is not None and (not doi or not normalize_doi(candidate.get('doi'))):
                target = candidate
        for field in ('abstract',):
            if a.get(field) and any(p in str(a[field]) for p in ('full text accessible via DOI', 'full publication text accessible', 'Structured abstract indexed', 'Abstract unavailable')):
                a[field] = None
        if doi:
            a['doi'] = 'https://doi.org/' + doi
        source = a.get('source_database')
        if target is None:
            a['source_databases'] = [source] if source else []
            merged.append(a)
            target = a
            by_title[title_key] = target
        else:
            if source and source not in target['source_databases']:
                target['source_databases'].append(source)
            for field in ('doi', 'abstract', 'year', 'open_access_pdf', 'journal'):
                if a.get(field) and (not target.get(field) or field == 'abstract' and len(a[field]) > len(target[field])):
                    target[field] = a[field]
        if doi:
            by_doi[doi] = target
    return merged


def accepted(a, config):
    text = f"{a.get('title') or ''} {a.get('abstract') or ''}".casefold()
    if any(p.casefold() not in text for p in config.phrases):
        return False
    if any(re.search(r'(?<!\w)' + re.escape(p.casefold()) + r'(?!\w)', text) for p in config.exclude):
        return False
    if config.year_from or config.year_to:
        try:
            year = int(a.get('year'))
        except (TypeError, ValueError):
            return False
        if config.year_from and year < config.year_from or config.year_to and year > config.year_to:
            return False
    return True


def relevance(query, article, synonyms):
    groups = [[x.strip().casefold() for x in group.split('|')] for group in synonyms]
    terms = re.findall(r'\w+', query.casefold())
    units, used = [], set()
    for term in terms:
        group = next((g for g in groups if term in g), [term])
        key = tuple(group)
        if key not in used:
            units.append(group)
            used.add(key)
    title = (article.get('title') or '').casefold()
    abstract = (article.get('abstract') or '').casefold()
    def has(term, text):
        return bool(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text))
    scores = [1.0 if any(has(t, title) for t in g) else 0.65 if any(has(t, abstract) for t in g) else 0 for g in units]
    return {'score_percent': round(100 * sum(scores) / max(1, len(scores))),
            'all_query_groups_matched': bool(scores) and all(score > 0 for score in scores),
            'method': 'transparent keyword groups; title weighted above abstract; not semantic confidence'}


class Transport:
    def __init__(self, request, trace_local):
        self.request = request
        self.trace_local = trace_local
        self.retries = 2
        self.cache_ttl = 86400
        self.no_cache = False
        self.cache_path = Path(os.environ.get('CHEM_MAT_HUB_CACHE_DIR', str(Path.cwd() / 'work' / 'chem-mat-hub-cache'))) / 'responses.sqlite3'

    def connection(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.cache_path, timeout=20)
        conn.execute('CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, created REAL, status INTEGER, headers TEXT, body BLOB)')
        return conn

    def shaped(self, url, kwargs):
        pager = getattr(STATE, 'pager', None)
        if not pager:
            return url, kwargs
        split = urlsplit(url)
        params = dict(parse_qsl(split.query))
        params.update(kwargs.pop('params', {}) or {})
        source, page, size, cursor = pager['source'], pager['page'], pager['size'], pager.get('cursor')
        host, path = split.hostname, split.path
        mapping = {
            'openalex': ('api.openalex.org', '/works', 'per_page', 'page'),
            'semantic-scholar': ('api.semanticscholar.org', '/graph/v1/paper/search', 'limit', 'offset'),
            'europe-pmc': ('www.ebi.ac.uk', '/europepmc/webservices/rest/search', 'pageSize', 'cursorMark'),
            'arxiv': ('export.arxiv.org', '/api/query', 'max_results', 'start'),
            'crossref': ('api.crossref.org', '/works', 'rows', 'offset'),
            'scopus': ('api.elsevier.com', '/content/search/scopus', 'count', 'start'),
            'osti': ('www.osti.gov', '/api/v1/records', 'rows', 'page'),
            'doaj': ('doaj.org', '/api/v2/search/articles/', 'pageSize', 'page'),
            'datacite': ('api.datacite.org', '/dois', 'page[size]', 'page[number]'),
            'pubmed': ('eutils.ncbi.nlm.nih.gov', '/entrez/eutils/esearch.fcgi', 'retmax', 'retstart'),
            'core': ('api.core.ac.uk', '/v3/search/works', 'limit', 'offset'),
            'zenodo': ('zenodo.org', '/api/records', 'size', 'page'),
        }
        expected_host, expected_path, count, offset = mapping[source]
        pager['last_request_is_search'] = False
        if host == expected_host and path.startswith(expected_path):
            params[count] = size
            params[offset] = cursor or '*' if source == 'europe-pmc' else (page * size if offset in ('offset', 'start', 'retstart') else page + 1)
            pager['matched'] = True
            pager['last_request_is_search'] = True
            # Europe PMC open-access filtering is not mandatory for literature discovery.
            if source == 'europe-pmc':
                params['query'] = params['query'].replace(' OPEN_ACCESS:y', '')
            if source == 'openalex' and os.getenv('OPENALEX_API_KEY'):
                params['api_key'] = os.environ['OPENALEX_API_KEY']
        kwargs['params'] = params
        return urlunsplit((split.scheme, split.netloc, split.path, '', split.fragment)), kwargs

    def __call__(self, session, method, url, **kwargs):
        url = url.replace('http://export.arxiv.org', 'https://export.arxiv.org')
        url, kwargs = self.shaped(url, dict(kwargs))
        kwargs['verify'] = True
        host = urlsplit(url).hostname
        headers = dict(session.headers)
        headers.update(kwargs.get('headers') or {})
        # Credential values affect the namespace, but are never stored as cache metadata.
        key = hashlib.sha256(json.dumps([method, url, kwargs.get('params'), kwargs.get('json'), kwargs.get('data'), sorted(headers.items())], sort_keys=True, default=str).encode()).hexdigest()
        use_cache = method.upper() == 'GET' and not self.no_cache and not getattr(session, '_chem_fulltext', False)
        record = {'host': host, 'attempts': 0, 'cache': 'miss'}
        response = None
        try:
            if use_cache:
                try:
                    with closing(self.connection()) as conn, conn:
                        row = conn.execute('SELECT created,status,headers,body FROM responses WHERE key=?', (key,)).fetchone()
                    if row and time.time() - row[0] < self.cache_ttl:
                        response = requests.Response()
                        response.status_code, response.headers, response._content = row[1], requests.structures.CaseInsensitiveDict(json.loads(row[2])), row[3]
                        response.url = url
                        response.encoding = 'utf-8'
                        record['cache'] = 'hit'
                except (OSError, sqlite3.Error):
                    record['cache'] = 'unavailable'
            if response is None:
                for attempt in range(self.retries + 1):
                    record['attempts'] += 1
                    interval = 3.0 if host == 'export.arxiv.org' else 1.05 if host == 'api.semanticscholar.org' else 0.35 if host == 'eutils.ncbi.nlm.nih.gov' else 0
                    if interval:
                        with RATE_LOCK:
                            delay = max(0, LAST_CALL.get(host, 0) + interval - time.monotonic())
                            LAST_CALL[host] = time.monotonic() + delay
                        time.sleep(delay)
                    try:
                        response = self.request(session, method, url, **kwargs)
                    except (requests.Timeout, requests.ConnectionError):
                        if attempt == self.retries:
                            raise
                        time.sleep(min(2 ** attempt, 5))
                        continue
                    if response.status_code not in (408, 429, 500, 502, 503, 504) or attempt == self.retries:
                        break
                    try:
                        delay = float(response.headers.get('Retry-After', 2 ** attempt))
                    except ValueError:
                        delay = 2 ** attempt
                    # Do not retry earlier than the server requests or block indefinitely.
                    if delay > 30:
                        record['retry_deferred'] = True
                        break
                    time.sleep(max(0, delay))
                if use_cache and response.status_code == 200 and len(response.content) < 10_000_000:
                    safe_headers = {k: v for k, v in response.headers.items() if k.lower() in ('content-type', 'content-encoding')}
                    try:
                        with closing(self.connection()) as conn, conn:
                            conn.execute('INSERT OR REPLACE INTO responses VALUES(?,?,?,?,?)', (key, time.time(), response.status_code, json.dumps(safe_headers), response.content))
                    except (OSError, sqlite3.Error):
                        record['cache'] = 'unavailable'
            record['http_status'] = response.status_code
            if response.status_code == 200:
                pager = getattr(STATE, 'pager', None)
                if pager and pager.get('last_request_is_search'):
                    try:
                        payload = response.json() if pager['source'] != 'arxiv' else None
                        paths = {'openalex': ('results',), 'semantic-scholar': ('data',),
                                 'europe-pmc': ('resultList', 'result'), 'crossref': ('message', 'items'),
                                 'scopus': ('search-results', 'entry'), 'osti': (), 'doaj': ('results',),
                                 'datacite': ('data',), 'pubmed': ('esearchresult', 'idlist'),
                                 'core': ('results',), 'zenodo': ('hits', 'hits')}
                        if pager['source'] == 'arxiv':
                            import xml.etree.ElementTree as ET
                            payload = ET.fromstring(response.text).findall('{http://www.w3.org/2005/Atom}entry')
                        else:
                            for field in paths[pager['source']]:
                                payload = payload[field]
                        pager['schema_verified'] = isinstance(payload, list)
                        pager['remote_records'] = len(payload) if isinstance(payload, list) else None
                        if pager['source'] == 'europe-pmc':
                            pager['next_cursor'] = response.json().get('nextCursorMark')
                    except (ValueError, KeyError, TypeError):
                        pager['schema_verified'] = False
            return response
        except requests.RequestException as exc:
            record['error_type'] = type(exc).__name__
            raise
        finally:
            if getattr(self.trace_local, 'trace', None) is not None:
                self.trace_local.trace.append(record)


def paged(function, source, config, query):
    found, seen = [], set()
    cursor = None
    stop = 'page_budget_reached'
    pages = 0
    # Fixed size maintains correct offsets on final partial pages.
    size = min(config.page_size, config.per_source)
    for page in range(config.max_pages):
        STATE.pager = {'source': source, 'page': page, 'size': size, 'cursor': cursor, 'matched': False}
        try:
            items = function(query)
            metadata = STATE.pager
        finally:
            STATE.pager = None
        pages += 1
        if not isinstance(items, list):
            stop = 'unexpected_response'
            break
        if not items and metadata.get('schema_verified') and metadata.get('remote_records', 0) > 0:
            stop = 'adapter_parse_failed'
            break
        new = [a for a in items if identity(a) not in seen]
        for a in new:
            seen.add(identity(a))
            found.append(a)
        if len(found) >= config.per_source:
            stop = 'per_source_limit_reached'
            break
        if not new:
            stop = 'empty_source_page' if not items and metadata.get('schema_verified') and metadata.get('remote_records') == 0 else 'empty_or_repeated_page'
            break
        if len(items) < size:
            stop = 'short_page'
            break
        if not metadata.get('matched'):
            stop = 'adapter_pagination_not_matched'
            break
        if source == 'europe-pmc':
            next_cursor = metadata.get('next_cursor')
            if not next_cursor or next_cursor == cursor:
                stop = 'cursor_exhausted'
                break
            cursor = next_cursor
    return found[:config.per_source], {'source': source, 'query': query, 'pages': pages,
                                       'records': min(len(found), config.per_source), 'stop_reason': stop}


def search(hub, runtime, query_text=None, *, query=None, max_results=None, config=None):
    query_text = query_text or query
    if not query_text or not query_text.strip():
        raise ValueError('Search query must be nonempty')
    config = config or getattr(runtime, 'SEARCH_CONFIG', Search())
    if max_results is not None:
        config = dataclasses.replace(config, max_results=max_results)
    config.validate()
    queries = variants(query_text, config.synonyms)
    queries = [q + ''.join(' "' + phrase + '"' for phrase in config.phrases) for q in queries]
    articles, pagination = [], []
    offset = len(runtime.DIAGNOSTICS)
    # One worker per provider keeps synonym queries within provider rate limits.
    def provider(source):
        all_items, log = [], []
        function = getattr(hub, runtime.SOURCES[source][0])
        for q in queries:
            items, info = paged(function, source, config, q)
            all_items.extend(items)
            log.append(info)
        return all_items, log
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(config.sources))) as pool:
        for items, log in pool.map(provider, config.sources):
            articles.extend(items)
            pagination.extend(log)
    merged = merge_articles(articles)
    selected = [a for a in merged if accepted(a, config)]
    for article in selected:
        article['relevance'] = relevance(query_text, article, config.synonyms)
    before_relevance = len(selected)
    selected = [a for a in selected if a['relevance']['score_percent'] >= config.min_relevance and
                (not config.require_all or a['relevance']['all_query_groups_matched'])]
    relevance_excluded = before_relevance - len(selected)
    selected.sort(key=lambda a: a['relevance']['score_percent'], reverse=True)
    selected = selected[:config.max_results]
    def enrich(article):
        doi = normalize_doi(article.get('doi'))
        if doi:
            if not article.get('open_access_pdf'):
                article['open_access_pdf'] = hub.resolve_unpaywall_pdf(doi)
            article['smart_citations'] = hub.resolve_scite_tallies(doi)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(enrich, selected[:config.enrich]))
    matrix = synthesis(hub, selected)
    return {'query': query_text, 'search_controls': dataclasses.asdict(config),
            'query_variants': queries, 'raw_records_retrieved': len(articles),
            'total_articles_retrieved': len(merged), 'articles_returned': len(selected),
            'records_excluded_by_metadata_filters': sum(not accepted(a, config) for a in merged),
            'records_excluded_by_relevance_controls': relevance_excluded,
            'coverage_note': 'Bounded retrieval, not an exhaustive review. Phrase, exclusion and year filters apply to retrieved title/abstract/year metadata. Missing years are excluded when year filtering is active. Source stop reasons are not proof of scientific exhaustion.',
            'pagination': pagination, 'source_diagnostics': runtime.DIAGNOSTICS[offset:],
            'articles': selected, 'synthesis_matrix': matrix['records'],
            'synthesis_table_markdown': matrix['markdown_table']}


VALUE = r'[-+]?\d+(?:\.\d+)?(?:\s*[x×*]\s*10\s*\^?\s*[-−]?\d+|[eE][-+]?\d+)?'
QUANTITY = re.compile(r'(?P<value>' + VALUE + r')\s*(?P<unit>(?:mS|µS|μS|uS|S)\s*(?:/\s*cm|[·\s]*cm\s*[-−^]?\s*1)|GPa|MPa|kPa|°\s*C|deg\s*C|K|%)(?!\w)', re.I)
LABELS = {
    'ionic_conductivity': r'ionic\s+conductivity|conductivity',
    'youngs_modulus': r"Young[’']?s?\s+modulus|elastic\s+modulus",
    'storage_modulus': r'storage\s+modulus',
    'loss_modulus': r'loss\s+modulus',
    'tensile_strength': r'tensile\s+strength|ultimate\s+(?:tensile\s+)?strength',
    'modulus_unspecified': r'\bmodulus\b',
    'degradation_temperature': r'degradation\s+(?:temperature|onset)|decomposition\s+(?:temperature|onset)|\bTd\b',
    'glass_transition_temperature': r'glass\s+transition|\bTg\b',
    'melting_temperature': r'melting\s+(?:point|temperature)|\bTm\b',
    'elongation_at_break': r'elongation\s+at\s+break|strain\s+at\s+break',
}


def evidence(text, *, page=None, source='text', doi=None):
    records = []
    # Decimal points are preserved; punctuation ends a contextual statement.
    sentences = re.split(r'(?<=[;!?])\s*|(?<!\d)\.\s+(?=[A-Z])|\n\s*\n', text)
    for sentence in sentences:
        for match in QUANTITY.finditer(sentence):
            unit = match.group('unit')
            family = 'conductivity' if re.search(r'S', unit, re.I) else 'stress' if 'pa' in unit.lower() else 'strain' if '%' in unit else 'temperature'
            allowed = ('ionic_conductivity',) if family == 'conductivity' else ('youngs_modulus', 'storage_modulus', 'loss_modulus', 'tensile_strength', 'modulus_unspecified') if family == 'stress' else ('elongation_at_break',) if family == 'strain' else ('degradation_temperature', 'glass_transition_temperature', 'melting_temperature')
            candidates = []
            for label in allowed:
                for name in re.finditer(LABELS[label], sentence, re.I):
                    distance = match.start() - name.end()
                    if 0 <= distance <= 80 and not QUANTITY.search(sentence[name.end():match.start()]):
                        candidates.append((distance, label))
            candidates.sort()
            # Prefer a specific modulus label over its embedded generic word.
            if family == 'stress' and any(c[1].endswith('modulus') for c in candidates):
                candidates = [c for c in candidates if c[1] != 'modulus_unspecified']
            label = candidates[0][1] if candidates else 'unclassified_' + family
            quote = ' '.join(sentence[max(0, match.start()-550):match.end()+550].split())
            records.append({'property': label, 'value_text': match.group('value'), 'unit': unit,
                            'page': page, 'source': source, 'doi': doi,
                            'evidence_quote': quote[:1200],
                            'status': 'candidate_requires_verification' if candidates else 'unclassified',
                            'sample_context': ' '.join(sentence[max(0, match.start()-160):match.end()+160].split())})
    return records


def properties(hub, text):
    # Keep identity mentions from upstream; replace its broad value inference.
    output = hub._original_extract(text)
    for key in ('thermal_properties', 'mechanical_modulus', 'stretchability', 'ionic_conductivity'):
        output.pop(key, None)
    records = evidence(text)
    mapping = {'ionic_conductivity': 'ionic_conductivity', 'degradation_temperature': 'thermal_properties',
               'glass_transition_temperature': 'thermal_properties', 'melting_temperature': 'thermal_properties',
               'youngs_modulus': 'mechanical_modulus', 'storage_modulus': 'mechanical_modulus',
               'loss_modulus': 'mechanical_modulus', 'modulus_unspecified': 'mechanical_modulus',
               'tensile_strength': 'tensile_strength', 'elongation_at_break': 'stretchability'}
    for r in records:
        if r['property'] in mapping:
            output.setdefault(mapping[r['property']], []).append(r['property'] + ': ' + r['value_text'] + ' ' + r['unit'])
    output['evidence_candidates'] = records
    return output


def synthesis(hub, articles):
    matrix = hub._original_synthesis(articles)
    for row, article in zip(matrix['records'], articles):
        row['evidence_candidates'] = evidence(f"{article.get('title') or ''}. {article.get('abstract') or ''}", source='title_and_abstract', doi=article.get('doi'))
        row['evidence_status'] = 'unverified_metadata_extraction'
        row['tensile_strength'] = [r for r in row['evidence_candidates'] if r['property'] == 'tensile_strength']
    matrix['markdown_table'] = matrix['markdown_table'].replace('scite.ai Consensus', 'scite.ai tallies').replace('Neutral / 0', 'Unavailable or zero; inspect record')
    return matrix


def deep_read(hub, target, max_pages=None, *, ocr=False, save_pdf=None):
    if not hub.fitz:
        return {'status': 'error', 'message': 'PyMuPDF unavailable'}
    path = Path(target)
    try:
        local = path.is_file() if not target.startswith(('http://', 'https://')) else False
    except OSError:
        local = False
    doi = normalize_doi(target)
    url = None
    retrieval = None
    try:
        if local:
            document = hub.fitz.open(str(path))
        else:
            from fulltext import retrieve
            body, retrieval = retrieve(hub, target, doi)
            if body is None:
                return {**retrieval, 'target_query': target}
            url = retrieval['source_pdf_url']
            document = hub.fitz.open(stream=body, filetype='pdf')
    except Exception as exc:
        return {'status': 'error', 'error_type': type(exc).__name__, 'target_query': target}
    result = {'status': 'success', 'target_query': target, 'source_pdf_url': url,
              'total_pages': len(document), 'pages': [], 'tables': [], 'evidence_candidates': [], 'warnings': []}
    if save_pdf:
        from fulltext import persist_pdf
        try:
            result.update(persist_pdf(path.read_bytes() if local else body, save_pdf))
        except Exception as exc:
            document.close()
            return {'status': 'error', 'error_type': type(exc).__name__, 'message': 'PDF save failed; existing files are preserved'}
    if retrieval:
        result['retrieval'] = retrieval
    limit = len(document) if max_pages is None else min(len(document), max_pages)
    if limit <= 0:
        document.close()
        raise ValueError('max_pages must be positive')
    tessdata = os.environ.get('TESSDATA_PREFIX')
    bundled = Path(__file__).resolve().parent.parent / 'assets' / 'tessdata'
    known = Path(r'C:\Program Files\Tesseract-OCR\tessdata')
    if not tessdata and (bundled / 'eng.traineddata').is_file():
        tessdata = str(bundled)
    elif not tessdata and known.is_dir():
        tessdata = str(known)
    try:
        for index in range(limit):
            page = document[index]
            text = page.get_text(sort=True)
            method = 'native_text'
            if len(text.strip()) < 30:
                if ocr:
                    try:
                        textpage = page.get_textpage_ocr(language='eng', dpi=200, full=True, tessdata=tessdata)
                        text = page.get_text(textpage=textpage, sort=True)
                        method = 'ocr'
                    except Exception as exc:
                        method = 'ocr_unavailable'
                        result['warnings'].append({'page': index + 1, 'issue': 'OCR failed or runtime unavailable', 'error_type': type(exc).__name__})
                else:
                    method = 'no_extractable_text'
                    result['warnings'].append({'page': index + 1, 'issue': 'No text; try --ocr with Tesseract language data'})
            result['pages'].append({'page': index+1, 'method': method, 'text': text})
            result['evidence_candidates'].extend(evidence(text, page=index+1, source='pdf', doi=doi))
            try:
                for table in page.find_tables().tables:
                    result['tables'].append({'page': index+1, 'bbox': list(table.bbox), 'rows': table.extract(), 'status': 'candidate_requires_verification'})
            except Exception as exc:
                result['warnings'].append({'page': index+1, 'issue': 'Table extraction failed', 'error_type': type(exc).__name__})
    finally:
        document.close()
    result['pages_read'] = limit
    result['truncated'] = limit < result['total_pages']
    result['total_characters_extracted'] = sum(len(p['text']) for p in result['pages'])
    if result['warnings'] or result['truncated']:
        result['status'] = 'partial'
    full_text = '\n'.join(p['text'] for p in result['pages'])
    result['extracted_properties'] = properties(hub, full_text)
    return result


def export_references(hub, articles, bib_path=None, ris_path=None):
    bib, ris, provenance = [], [], []
    articles = merge_articles(articles)
    def publisher_metadata(a):
        doi = normalize_doi(a.get('doi'))
        return (hub.fetch_doi_citation_metadata(doi, 'bibtex') if doi and bib_path else None,
                hub.fetch_doi_citation_metadata(doi, 'ris') if doi and ris_path else None)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        metadata = list(pool.map(publisher_metadata, articles))
    for index, (a, (entry_bib, entry_ris)) in enumerate(zip(articles, metadata)):
        doi = normalize_doi(a.get('doi'))
        year, title, authors = a.get('year'), a.get('title') or 'Untitled', a.get('authors') or []
        if entry_bib and not re.match(r'\s*@\w+\s*[{(]', entry_bib):
            entry_bib = None
        if entry_ris and not re.search(r'^TY  - ', entry_ris, re.M):
            entry_ris = None
        def escape(value):
            return str(value).replace('\\', r'\textbackslash{}').replace('{', r'\{').replace('}', r'\}').replace('%', r'\%').replace('&', r'\&').replace('_', r'\_').replace('#', r'\#')
        fields = {'title': title, 'author': ' and '.join(authors), 'journal': a.get('journal'), 'year': year, 'doi': doi,
                  'url': a.get('doi') if not doi else None}
        if bib_path:
            bib.append(entry_bib or '@misc{chemhub_' + str(index) + ',\n' + ',\n'.join('  ' + k + '={' + escape(v) + '}' for k, v in fields.items() if v) + '\n}')
        if ris_path:
            lines = ['TY  - GEN', 'TI  - ' + title.replace('\n', ' ')]
            lines += ['AU  - ' + str(author).replace('\n', ' ') for author in authors]
            lines += [tag + '  - ' + str(value).replace('\n', ' ') for tag, value in [('PY', year), ('JO', a.get('journal')), ('DO', doi), ('UR', a.get('doi') if not doi else None)] if value]
            lines += ['ER  - ']
            ris.append(entry_ris or '\n'.join(lines))
        provenance.append({'doi': doi, 'bibtex': 'publisher' if entry_bib else 'metadata_fallback' if bib_path else None,
                           'ris': 'publisher' if entry_ris else 'metadata_fallback' if ris_path else None})
    for filename, entries in ((bib_path, bib), (ris_path, ris)):
        if filename:
            Path(filename).write_text('\n\n'.join(entries) + ('\n' if entries else ''), encoding='utf-8')
    return {'bibtex_count': len(bib), 'ris_count': len(ris), 'bib_path': bib_path, 'ris_path': ris_path, 'provenance': provenance}


def install(hub, runtime):
    transport = Transport(runtime.REQUEST, runtime.LOCAL)
    runtime.TRANSPORT = transport
    # Assign a plain function; assigning a callable object alone does not bind Session.
    requests.sessions.Session.request = lambda session, method, url, **kwargs: transport(session, method, url, **kwargs)
    from fulltext import resolve_unpaywall_pdf
    hub.resolve_unpaywall_pdf = resolve_unpaywall_pdf
    hub._original_extract = hub.extract_material_properties
    hub._original_synthesis = hub.generate_synthesis_matrix
    hub.extract_material_properties = lambda text: properties(hub, text)
    hub.generate_synthesis_matrix = lambda articles: synthesis(hub, articles)
    hub.query_research_literature = lambda query_text=None, **kwargs: search(hub, runtime, query_text, **kwargs)
    hub.deep_read_pdf = lambda target, max_pages=None, **kwargs: deep_read(hub, target, max_pages, **kwargs)
    hub.export_zotero_references = lambda articles, bib_path=None, ris_path=None: export_references(hub, articles, bib_path, ris_path)
    original_all = hub.query_all
    def query_all(*args, **kwargs):
        offset = len(runtime.DIAGNOSTICS)
        result = original_all(*args, **kwargs)
        result['source_diagnostics'] = runtime.DIAGNOSTICS[offset:]
        return result
    hub.query_all = query_all
    original_graph = hub.explore_citation_graph
    wrapped_graph = runtime.wrap('citation-graph', original_graph, None)
    def graph(*args, **kwargs):
        offset = len(runtime.DIAGNOSTICS)
        result = wrapped_graph(*args, **kwargs)
        result['source_diagnostics'] = runtime.DIAGNOSTICS[offset:]
        return result
    hub.explore_citation_graph = graph
