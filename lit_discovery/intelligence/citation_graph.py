"""Connected Papers & Citation Network snowballing explorer."""
import concurrent.futures
import urllib.parse
import requests

from lit_discovery.core.relevance import reconstruct_inverted_abstract
from lit_discovery.core.unpaywall import resolve_unpaywall_pdf
from lit_discovery.intelligence.scite_consensus import resolve_scite_tallies

HEADERS = {"User-Agent": "LitDiscovery/1.0 (mailto:rehan@arizona.edu)"}

def explore_citation_graph(seed_doi_or_query, mode="related", limit=6):
    """Explores citation networks around a seed paper (related co-citations, forward citing works, or backward seminal references)."""
    seed = seed_doi_or_query.strip()
    if seed.startswith("http"):
        seed_url = f"https://api.openalex.org/works/{seed}"
    elif "10." in seed:
        seed_url = f"https://api.openalex.org/works/https://doi.org/{seed}"
    else:
        seed_url = f"https://api.openalex.org/works?search={urllib.parse.quote(seed)}&per_page=1"

    try:
        r_seed = requests.get(seed_url, headers=HEADERS, timeout=12)
        if r_seed.status_code != 200:
            # Fallback to search query
            fallback_url = f"https://api.openalex.org/works?search={urllib.parse.quote(seed)}&per_page=1"
            r_seed = requests.get(fallback_url, headers=HEADERS, timeout=12)

        if r_seed.status_code != 200:
            return {"status": "error", "error": f"Seed paper not found on OpenAlex (HTTP {r_seed.status_code})"}

        data = r_seed.json()
        results_list = data.get("results")
        if results_list is not None:
            if not results_list:
                return {"status": "not_found", "message": f"No works matching seed query: {seed}"}
            seed_work = results_list[0]
        else:
            seed_work = data

        work_id = seed_work.get("id", "").split("/")[-1]
        seed_info = {
            "title": seed_work.get("title"),
            "doi": seed_work.get("doi"),
            "year": seed_work.get("publication_year"),
            "openalex_id": work_id
        }

        if mode in ["forward", "cites"]:
            graph_url = f"https://api.openalex.org/works?filter=cites:{work_id}&per-page={limit}"
        elif mode in ["backward", "cited_by"]:
            ref_ids = [ref.split("/")[-1] for ref in seed_work.get("referenced_works", [])[:limit]]
            if not ref_ids:
                return {"status": "not_found", "message": "No referenced works recorded for this seed paper."}
            graph_url = f"https://api.openalex.org/works?filter=openalex_id:{'|'.join(ref_ids)}&per-page={limit}"
        else:
            graph_url = f"https://api.openalex.org/works?filter=related_to:{work_id}&per-page={limit}"

        r_graph = requests.get(graph_url, headers=HEADERS, timeout=12)
        if r_graph.status_code != 200:
            return {"status": "error", "error": f"Failed to retrieve citation graph (HTTP {r_graph.status_code})"}

        results = r_graph.json().get("results", [])
        connected_articles = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            scite_futs = {}
            for idx, w in enumerate(results):
                doi = w.get("doi")
                if doi:
                    scite_futs[idx] = ex.submit(resolve_scite_tallies, doi)
            for idx, w in enumerate(results):
                abstract = reconstruct_inverted_abstract(w.get("abstract_inverted_index"))
                doi = w.get("doi")
                oa = w.get("open_access", {})
                pdf_url = oa.get("oa_url") if oa.get("is_oa") else None
                if not pdf_url and doi:
                    pdf_url = resolve_unpaywall_pdf(doi)
                sc = scite_futs[idx].result() if idx in scite_futs else None
                authors = [a.get("author", {}).get("display_name") for a in w.get("authorships", []) if a.get("author", {}).get("display_name")]
                connected_articles.append({
                    "title": w.get("title"),
                    "doi": doi,
                    "authors": authors[:5],
                    "year": w.get("publication_year"),
                    "abstract": abstract,
                    "open_access_pdf": pdf_url,
                    "smart_citations": sc,
                    "journal": w.get("primary_location", {}).get("source", {}).get("display_name") if w.get("primary_location") and w.get("primary_location", {}).get("source") else None
                })
        return {
            "status": "success",
            "seed_paper": seed_info,
            "mode": mode,
            "total_connected": len(connected_articles),
            "connected_works": connected_articles
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
