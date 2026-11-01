"""Unified literature search dispatcher orchestrating concurrent queries across 12 academic engines."""
import concurrent.futures
import re
from typing import Dict, List, Optional, Any

from lit_discovery.core.engines import (
    fetch_openalex_literature,
    fetch_crossref_literature,
    fetch_semantic_scholar_literature,
    fetch_europe_pmc_literature,
    fetch_arxiv_literature,
    fetch_scopus_literature,
    fetch_osti_literature,
    fetch_doaj_literature,
    fetch_datacite_literature,
    fetch_pubmed_literature,
    fetch_core_literature,
    fetch_zenodo_literature,
)
from lit_discovery.core.relevance import calculate_relevance_rating
from lit_discovery.core.unpaywall import resolve_unpaywall_pdf
from lit_discovery.intelligence.scite_consensus import resolve_scite_tallies
from lit_discovery.synthesis.matrix import generate_synthesis_matrix
from lit_discovery.exports.zotero import normalize_doi

AVAILABLE_ENGINES = {
    "openalex": fetch_openalex_literature,
    "crossref": fetch_crossref_literature,
    "semantic_scholar": fetch_semantic_scholar_literature,
    "europe_pmc": fetch_europe_pmc_literature,
    "arxiv": fetch_arxiv_literature,
    "scopus": fetch_scopus_literature,
    "osti": fetch_osti_literature,
    "doaj": fetch_doaj_literature,
    "datacite": fetch_datacite_literature,
    "pubmed": fetch_pubmed_literature,
    "core": fetch_core_literature,
    "zenodo": fetch_zenodo_literature,
}


def search_literature(
    query_text: str,
    selected_engines: Optional[List[str]] = None,
    limit_per_engine: int = 5,
    top_n: int = 10,
    enrich: bool = True
) -> Dict[str, Any]:
    """Dispatches query across scientific literature engines concurrently.

    Args:
        query_text: Natural language or boolean search string.
        selected_engines: List of engine keys (e.g. ['openalex', 'arxiv', 'pubmed']).
                          If None, all 12 engines are queried.
        limit_per_engine: Number of results requested per engine.
        top_n: Number of highest-relevance articles to return in final enriched set.
        enrich: Whether to query Unpaywall and scite.ai for top results.

    Returns:
        Structured search results with synthesis matrix and enriched metadata.
    """
    if not query_text.strip():
        raise ValueError("query must not be empty")
    if limit_per_engine <= 0 or top_n <= 0:
        raise ValueError("result limits must be positive")
    raw_articles = []
    engines_to_run = {}

    if not selected_engines:
        engines_to_run = AVAILABLE_ENGINES
    else:
        norm_keys = [k.lower().strip().replace(" ", "_").replace("-", "_") for k in selected_engines]
        for k, fn in AVAILABLE_ENGINES.items():
            if k in norm_keys:
                engines_to_run[k] = fn
        unknown = set(norm_keys) - set(AVAILABLE_ENGINES)
        if unknown:
            raise ValueError("Unknown engines: " + ", ".join(sorted(unknown)))

    # 1. Concurrent multi-engine execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(engines_to_run) or 4) as executor:
        future_map = {
            executor.submit(fn, query_text, limit_per_engine): name
            for name, fn in engines_to_run.items()
        }
        for fut in concurrent.futures.as_completed(future_map):
            name = future_map[fut]
            try:
                res = fut.result()
                if res and isinstance(res, list):
                    raw_articles.extend(dict(article, source_databases=[name]) for article in res)
            except Exception:
                pass

    # 2. Merge duplicate identity while retaining provider provenance.
    articles = []
    by_doi, by_title = {}, {}
    for raw in raw_articles:
        art = dict(raw)
        title_key = re.sub(r"\W+", "", (art.get("title") or "").casefold())
        doi = normalize_doi(art.get("doi"))
        doi_key = doi.casefold() if doi else None
        target = by_doi.get(doi_key) if doi_key else None
        if target is None and title_key:
            candidate = by_title.get(title_key)
            if candidate is not None and (not doi_key or not normalize_doi(candidate.get("doi"))):
                target = candidate
        if target is None:
            if not title_key and not doi_key:
                continue
            if doi:
                art["doi"] = "https://doi.org/" + doi
            art["source_databases"] = sorted(set(art.get("source_databases") or []))
            articles.append(art)
            target = art
        else:
            target["source_databases"] = sorted(set(target.get("source_databases", [])) | set(art.get("source_databases", [])))
            for field in ("title", "doi", "year", "journal", "abstract", "open_access_pdf", "authors"):
                value = art.get(field)
                if value and (not target.get(field) or field == "abstract" and len(value) > len(target[field])):
                    target[field] = "https://doi.org/" + doi if field == "doi" and doi else value
        if doi_key:
            by_doi[doi_key] = target
        if title_key:
            by_title[title_key] = target
    for art in articles:
        art["relevance"] = calculate_relevance_rating(query_text, art.get("title"), art.get("abstract"))

    # 3. Sort by relevance rating descending
    articles.sort(key=lambda x: x.get("relevance", {}).get("score_percent", 0), reverse=True)
    top_articles = articles[:top_n]

    # 4. Enrich top articles with Unpaywall direct OA PDF + scite.ai Smart Citations
    if enrich and top_articles:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(top_articles), 8)) as enricher:
            pdf_futs = {}
            scite_futs = {}
            for idx, art in enumerate(top_articles):
                doi = art.get("doi")
                if doi and "10." in doi:
                    if not art.get("open_access_pdf"):
                        pdf_futs[idx] = enricher.submit(resolve_unpaywall_pdf, doi)
                    scite_futs[idx] = enricher.submit(resolve_scite_tallies, doi)

            for idx, fut in pdf_futs.items():
                try:
                    oa_url = fut.result()
                    if oa_url:
                        top_articles[idx]["open_access_pdf"] = oa_url
                except Exception:
                    pass

            for idx, fut in scite_futs.items():
                try:
                    scite_data = fut.result()
                    if scite_data:
                        top_articles[idx]["smart_citations"] = scite_data
                except Exception:
                    pass

    # 5. Generate comparative synthesis matrix
    synthesis = generate_synthesis_matrix(top_articles)

    return {
        "status": "success",
        "query": query_text,
        "engines_queried": list(engines_to_run.keys()),
        "total_articles_retrieved": len(articles),
        "total_articles_shown": len(top_articles),
        "synthesis_matrix": synthesis["records"],
        "synthesis_table_markdown": synthesis["markdown_table"],
        "articles": top_articles
    }
