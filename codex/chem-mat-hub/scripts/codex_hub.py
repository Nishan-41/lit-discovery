"""Codex entrypoint: existing engine plus credential-safe source diagnostics."""
import argparse
import concurrent.futures
import importlib.util
import json
import os
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

import requests
import unified_chem_mat_hub as hub
import research

SOURCES = {
    'pubchem': ('query_pubchem', None, 'ethanol'),
    'pubchem-experimental': ('query_pubchem_experimental_and_ghs', None, 'ethanol'),
    'chemspider': ('query_chemspider', 'RSC_KEY', 'ethanol'),
    'comptox': ('query_comptox', 'CTX_KEY', 'ethanol'),
    'materials-project': ('query_materials_project', None, 'SiO2'),
    'nomad': ('query_nomad', None, 'SiO2'),
    'cod': ('query_cod', None, 'SiO2'),
    'aflow': ('query_aflow', None, 'SiO2'),
    'oqmd': ('query_oqmd', None, 'SiO2'),
    'c2db': ('query_c2db', None, 'MoS2'),
    'mofdb': ('query_mofdb', None, 'UiO-66'),
    'ilthermo': ('query_ilthermo', None, 'EMIM TFSI'),
    'nist-webbook': ('query_nist_webbook', None, 'ethanol'),
    'openalex': ('fetch_openalex_literature', None, 'ionogel'),
    'semantic-scholar': ('fetch_semantic_scholar_literature', None, 'ionogel'),
    'europe-pmc': ('fetch_europe_pmc_literature', None, 'ionogel'),
    'arxiv': ('fetch_arxiv_literature', None, 'ionogel'),
    'crossref': ('fetch_crossref_literature', None, 'ionogel'),
    'scopus': ('fetch_scopus_literature', 'SCOPUS_KEY', 'ionogel'),
    'osti': ('fetch_osti_literature', None, 'ionogel'),
    'doaj': ('fetch_doaj_literature', None, 'ionogel'),
    'datacite': ('fetch_datacite_literature', None, 'ionogel'),
    'pubmed': ('fetch_pubmed_literature', None, 'ionogel'),
    'core': ('fetch_core_literature', 'CORE_KEY', 'ionogel'),
    'zenodo': ('fetch_zenodo_literature', None, 'ionogel'),
    'scite': ('resolve_scite_tallies', None, '10.1038/s41467-023-388 ionogel'),
    'unpaywall': ('resolve_unpaywall_pdf', None, '10.1038/s41586-021-03819-2'),
}
# Known DOI for enrichment probes; no arbitrary search expression sent as DOI.
SOURCES['scite'] = ('resolve_scite_tallies', None, '10.1038/s41586-021-03819-2')
LOCAL = threading.local()
DIAGNOSTICS = []
LOCK = threading.Lock()
REQUEST = requests.sessions.Session.request


def observed_request(session, method, url, **kwargs):
    record = {'host': urlsplit(url).hostname}
    try:
        response = REQUEST(session, method, url, **kwargs)
        record['http_status'] = response.status_code
        return response
    except requests.RequestException as exc:
        record['error_type'] = type(exc).__name__
        raise
    finally:
        if getattr(LOCAL, 'trace', None) is not None:
            LOCAL.trace.append(record)


requests.sessions.Session.request = observed_request


def wrap(name, function, key):
    def call(*args, **kwargs):
        previous = getattr(LOCAL, 'trace', None)
        LOCAL.trace = []
        error = None
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            error = type(exc).__name__
            result = {'status': 'error', 'error_type': error}
        trace = LOCAL.trace
        LOCAL.trace = previous
        failed = [r for r in trace if r.get('error_type') or r.get('http_status', 200) >= 400]
        if key and not getattr(hub, key):
            status = 'missing_key'
        elif name == 'unpaywall' and not os.getenv('CHEM_MAT_HUB_UNPAYWALL_EMAIL') and not trace:
            status = 'skipped_opt_in'
        elif error:
            status = 'parse_or_runtime_error'
        elif failed:
            status = 'partial' if result and (isinstance(result,list) or isinstance(result,dict) and result.get('sets_retrieved',0)>0) else 'request_failed'
        elif isinstance(result, dict) and result.get('status') in ('error', 'skipped', 'not_found', 'partial', 'identity_unresolved', 'schema_error'):
            status = result['status']
        elif not result:
            pager = getattr(research.STATE, 'pager', None)
            if pager and pager.get('schema_verified'):
                status = 'no_matches' if pager.get('remote_records') == 0 else 'adapter_parse_failed'
            elif pager and pager.get('matched'):
                status = 'adapter_parse_failed'
            else:
                status = 'empty_or_unparsed'
        else:
            status = 'returned_data'
        with LOCK:
            count = len(result) if isinstance(result,list) else result.get('sets_retrieved') if isinstance(result,dict) else None
            DIAGNOSTICS.append({'source': name, 'status': status, 'requests': trace,
                                'records': count})
        if failed and isinstance(result, dict) and result.get('status') in ('not_found', 'timeout'):
            result['engine_status'] = result.get('status')
            result['status'] = 'error'
            result['source_status'] = 'request_failed'
        return result
    return call


for source, (function_name, credential, _) in SOURCES.items():
    setattr(hub, function_name, wrap(source, getattr(hub, function_name), credential))

SEARCH_CONFIG = research.Search()
research.install(hub, sys.modules[__name__])


def query_source(source, query, *, probe=False):
    function = getattr(hub, SOURCES[source][0])
    if source == 'ilthermo' and probe:
        return function(query,max_sets=1)
    if source in ('materials-project', 'nomad', 'cod', 'aflow', 'oqmd', 'c2db'):
        return function(formula=query)
    return function(query)


def doctor():
    keys = ['MP_KEY', 'RSC_KEY', 'SCOPUS_KEY', 'CTX_KEY', 'S2_KEY', 'CORE_KEY']
    return {'python': sys.executable,
            'credentials': {k: bool(getattr(hub, k)) for k in keys},
            'dependencies': {m: bool(importlib.util.find_spec(m)) for m in
                             ['requests', 'bs4', 'dotenv', 'fitz', 'CoolProp']},
            'environment_override_configured': bool(os.getenv('CHEM_MAT_HUB_ENV_FILE')),
            'sources': list(SOURCES),
            'cache_directory': str(TRANSPORT.cache_path.parent),
            'ocr': {'tesseract_command_available': bool(research.shutil.which('tesseract')),
                    'language_data_configured': bool(os.getenv('TESSDATA_PREFIX')),
                    'bundled_english_model_available': (Path(__file__).resolve().parent.parent / 'assets/tessdata/eng.traineddata').is_file()},
            'upstream': __import__('sync_upstream').check()}


def main():
    global SEARCH_CONFIG
    with LOCK:
        DIAGNOSTICS.clear()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--doctor', action='store_true')
    parser.add_argument('--probe', action='store_true', help='Read-only query of every remote source')
    parser.add_argument('--database', choices=SOURCES)
    parser.add_argument('--query')
    parser.add_argument('--ilthermo-max-sets', type=int, default=50, help='Full ILThermo datasets to fetch; 0 means all exact single-component sets')
    parser.add_argument('--ilthermo-compound-id', help='Explicit NIST identity when exact name cannot resolve uniquely')
    parser.add_argument('--ilthermo-formula', help='Expected molecular formula; mismatched dataset rejected')
    parser.add_argument('--literature', help='Search all 12 literature databases')
    parser.add_argument('--output')
    parser.add_argument('--max-results', type=int, default=50)
    parser.add_argument('--per-source', type=int, default=30)
    parser.add_argument('--page-size', type=int, default=20)
    parser.add_argument('--max-pages', type=int, default=10)
    parser.add_argument('--year-from', type=int)
    parser.add_argument('--year-to', type=int)
    parser.add_argument('--phrase', action='append', default=[])
    parser.add_argument('--exclude', action='append', default=[])
    parser.add_argument('--synonyms', action='append', default=[], help='PBO|Zylon|polybenzoxazole')
    parser.add_argument('--sources', help='Comma-separated literature source names')
    parser.add_argument('--enrich', type=int, default=8, help='Enrich this many ranked papers; 0 disables enrichment')
    parser.add_argument('--require-all', action='store_true', help='Require every query keyword/synonym group in title or abstract')
    parser.add_argument('--min-relevance', type=int, default=1, help='Minimum lexical score, 0..100 (not semantic confidence)')
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--cache-ttl', type=int, default=86400)
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--deep-read')
    parser.add_argument('--save-pdf', help='Save validated main-paper PDF to this local path')
    parser.add_argument('--fetch-fulltext', type=int, default=None, help='Retrieve full text for first N search results, maximum 20')
    parser.add_argument('--pdf-dir', help='Directory for PDFs, evidence JSON and retrieval manifest')
    parser.add_argument('--max-pdf-pages', type=int)
    parser.add_argument('--ocr', action='store_true')
    parser.add_argument('--export-bibtex')
    parser.add_argument('--export-ris')
    parser.add_argument('--library-dir', help='Persistent project library; defaults to configured project')
    parser.add_argument('--no-library', action='store_true', help='Explicitly disable persistent saving for this run')
    parser.add_argument('--library-graph', action='store_true', help='Refresh graph from saved project records')
    parser.add_argument('--import-result', help='Import an existing search, citation or PDF evidence JSON')
    parser.add_argument('--paper-doi', help='Associate local PDF/evidence with a paper DOI')
    parser.add_argument('--asset-role', choices=('main','supporting'), default='main')
    parser.add_argument('--seed-doi')
    parser.add_argument('--graph-mode', choices=('related','forward','backward'), default='related')
    parser.add_argument('--graph-limit', type=int, default=15)
    parser.add_argument('--sync-check', action='store_true')
    parser.add_argument('--sync-upstream', action='store_true', help='Refresh upstream engine while retaining Codex enhancements')
    args, engine_args = parser.parse_known_args()
    if args.ilthermo_max_sets < 0:
        parser.error('--ilthermo-max-sets must be >= 0')
    import thermophysics
    thermophysics.CONFIG.update(max_sets=args.ilthermo_max_sets, compound_id=args.ilthermo_compound_id, formula=args.ilthermo_formula)
    try:
        SEARCH_CONFIG = research.Search(args.max_results, args.per_source, args.page_size, args.max_pages,
                                       args.year_from, args.year_to, tuple(args.phrase), tuple(args.exclude),
                                       tuple(args.synonyms), tuple(args.sources.split(',')) if args.sources else research.LITERATURE,
                                       args.enrich, args.require_all, args.min_relevance).validate()
        if args.retries < 0 or args.retries > 5 or args.cache_ttl < 0:
            raise ValueError('retries must be 0..5 and cache_ttl must be >= 0')
    except ValueError as exc:
        parser.error(str(exc))
    if args.fetch_fulltext is None:
        args.fetch_fulltext = 5 if args.literature and not args.no_library else 0
    if not 0 <= args.fetch_fulltext <= 20:
        parser.error('--fetch-fulltext must be 0..20')
    from project_library import Library, default_root
    library_root=Path(args.library_dir) if args.library_dir else default_root()
    if args.fetch_fulltext and not args.literature:
        parser.error('--fetch-fulltext requires --literature')
    if args.fetch_fulltext and not args.pdf_dir:
        args.pdf_dir=str(library_root/'pdfs'/'downloads')
    if args.graph_limit <= 0:
        parser.error('--graph-limit must be positive')
    if args.deep_read and not args.save_pdf and not args.no_library:
        import hashlib
        args.save_pdf=str(library_root/'pdfs'/('read-'+hashlib.sha256(args.deep_read.encode()).hexdigest()[:20]+'.pdf'))
    if args.save_pdf and not args.deep_read:
        parser.error('--save-pdf requires --deep-read')
    TRANSPORT.no_cache, TRANSPORT.cache_ttl, TRANSPORT.retries = args.no_cache, args.cache_ttl, args.retries
    if args.library_graph:
        library=Library(library_root)
        try:
            result={'status':'success','graph':library.export()}
        finally:
            library.close()
    elif args.import_result:
        library=Library(library_root)
        try:
            payload=json.loads(Path(args.import_result).read_text(encoding='utf-8-sig'))
            result=library.ingest(payload,kind='import',source=str(Path(args.import_result).resolve()),paper_doi=args.paper_doi,asset_role=args.asset_role)
        finally:
            library.close()
    elif args.seed_doi:
        result=hub.explore_citation_graph(args.seed_doi,mode=args.graph_mode,limit=args.graph_limit)
    elif args.sync_check or args.sync_upstream:
        import sync_upstream
        result = sync_upstream.refresh() if args.sync_upstream else sync_upstream.check()
    elif args.doctor:
        result = doctor()
    elif args.probe:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(query_source, name, values[2], probe=True) for name, values in SOURCES.items()]
            for future in futures:
                future.result()
        result = {'configuration': doctor(), 'source_diagnostics': sorted(DIAGNOSTICS, key=lambda d: d['source'])}
    elif args.database:
        if not args.query:
            parser.error('--database requires --query')
        if args.database in research.LITERATURE:
            result = research.search(hub, sys.modules[__name__], args.query, config=research.dataclasses.replace(SEARCH_CONFIG, sources=(args.database,)))
        else:
            result = {'data': query_source(args.database, args.query), 'source_diagnostics': DIAGNOSTICS}
    elif args.literature:
        result = hub.query_research_literature(args.literature)
    elif args.deep_read:
        result = hub.deep_read_pdf(args.deep_read, args.max_pdf_pages, ocr=args.ocr, save_pdf=args.save_pdf)
    else:
        # Preserve original engine flags, including JSON and bibliography exports.
        sys.argv = [sys.argv[0], *engine_args]
        if args.output:
            sys.argv += ['--output', args.output]
        if args.export_bibtex:
            sys.argv += ['--export-bibtex', args.export_bibtex]
        if args.export_ris:
            sys.argv += ['--export-ris', args.export_ris]
        hub.main()
        if DIAGNOSTICS:
            from diagnostics import attach
            print(json.dumps(attach({'source_diagnostics':DIAGNOSTICS},SOURCES)), file=sys.stderr)
        return
    if args.fetch_fulltext:
        from fulltext import collect
        result['fulltext_collection'] = collect(hub, result.get('articles') or [], args.pdf_dir, args.fetch_fulltext, ocr=args.ocr)
    articles = result.get('articles') or result.get('connected_works') or []
    if args.export_bibtex or args.export_ris:
        result['zotero_export'] = hub.export_zotero_references(articles, args.export_bibtex, args.export_ris)
    from diagnostics import attach
    requested=tuple(SOURCES) if args.probe else (args.database,) if args.database else SEARCH_CONFIG.sources if args.literature else ()
    attach(result,SOURCES,requested=requested)
    persistent = args.literature or args.deep_read or args.seed_doi or (args.database in (*research.LITERATURE, 'ilthermo') if args.database else False)
    if persistent and not args.no_library:
        library=None
        try:
            library=Library(library_root)
            kind='reading' if args.deep_read else 'citation' if args.seed_doi else 'properties' if args.database == 'ilthermo' else 'search'
            result['project_library']=library.ingest(result,kind=kind,query=args.deep_read or args.literature or args.query or args.seed_doi,paper_doi=args.paper_doi,asset_role=args.asset_role)
        except Exception as exc:
            result['project_library']={'status':'save_failed','error_type':type(exc).__name__,'message':'Research result returned; project library write failed'}
        finally:
            if library:
                library.close()
    attach(result,SOURCES,requested=requested)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(text, encoding='utf-8')
        print(f'Saved {args.output}')
    else:
        print(text)


if __name__ == '__main__':
    main()
