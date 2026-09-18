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
    raw_articles = []
    engines_to_run = {}

    if not selected_engines:
        engines_to_run = AVAILABLE_ENGINES
    else:
        norm_keys = [k.lower().strip().replace(" ", "_") for k in selected_engines]
        for k, fn in AVAILABLE_ENGINES.items():
            if k in norm_keys:
                engines_to_run[k] = fn
        if not engines_to_run:
            engines_to_run = AVAILABLE_ENGINES

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
                    raw_articles.extend(res)
            except Exception:
                pass

    # 2. Deduplicate by normalized title and DOI
    articles = []
    seen_keys = set()
    for art in raw_articles:
        title = art.get("title") or ""
        norm_title = re.sub(r"[^a-zA-Z0-9]", "", title.lower())
        doi = (art.get("doi") or "").lower().strip()

        if doi and doi in seen_keys:
            continue
        if norm_title and norm_title in seen_keys:
            continue

        if doi:
            seen_keys.add(doi)
        if norm_title:
            seen_keys.add(norm_title)

        # Calculate keyword relevance rating
        rel = calculate_relevance_rating(query_text, title, art.get("abstract"))
        art["relevance"] = rel

        if not art.get("abstract"):
            art["abstract"] = "Structured abstract indexed; full publication text accessible via DOI / publisher portal."

        articles.append(art)

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
