"""Connected Papers & Citation Network snowballing explorer."""
import concurrent.futures
import re
import urllib.parse
import xml.etree.ElementTree as ET
import requests

from lit_discovery.core.relevance import reconstruct_inverted_abstract
from lit_discovery.core.unpaywall import resolve_unpaywall_pdf
from lit_discovery.intelligence.scite_consensus import resolve_scite_tallies

HEADERS = {"User-Agent": "LitDiscovery/1.0"}


def resolve_seed_work(seed_input: str):
    """Resolves arbitrary user input into an OpenAlex work record.

    Supports:
    - arXiv URLs (http://arxiv.org/abs/1409.4962v1) and bare arXiv IDs (1409.4962)
    - DOIs (10.1038/s41563-022-01195-4 or https://doi.org/...)
    - OpenAlex Work IDs (W2952052407 or https://openalex.org/W2952052407)
    - PubMed URLs and PMIDs (33895240 or https://pubmed.ncbi.nlm.nih.gov/...)
    - Paper titles and topic search queries
    """
    seed = seed_input.strip()

    # 1. arXiv URL or arXiv ID resolution
    m_arxiv = re.search(
        r'(?:arxiv\.org/(?:abs|pdf)/|arxiv:)?([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/[0-9]{7})(?:v\d+)?',
        seed,
        re.IGNORECASE
    )
    if "arxiv" in seed.lower() or (m_arxiv and "." in m_arxiv.group(1)):
        if m_arxiv:
            aid = m_arxiv.group(1)
            # 1a. Try official DataCite DOI for arXiv
            try:
                r = requests.get(
                    f"https://api.openalex.org/works/https://doi.org/10.48550/arxiv.{aid}",
                    headers=HEADERS,
                    timeout=10
                )
                if r.status_code == 200:
                    return r.json()
            except Exception:
                pass

            # 1b. Query arXiv export API to obtain exact title or published journal DOI
            try:
                r_ax = requests.get(f"https://export.arxiv.org/api/query?id_list={aid}", headers=HEADERS, timeout=8)
                if r_ax.status_code == 200:
                    root = ET.fromstring(r_ax.text)
                    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
                    entry = root.find("atom:entry", ns)
                    if entry is not None:
                        # Check for peer-reviewed journal DOI
                        doi_elem = entry.find("arxiv:doi", ns)
                        if doi_elem is not None and doi_elem.text:
                            r_doi = requests.get(
                                f"https://api.openalex.org/works/https://doi.org/{doi_elem.text.strip()}",
                                headers=HEADERS,
                                timeout=10
                            )
                            if r_doi.status_code == 200:
                                return r_doi.json()

                        # Search OpenAlex by paper title
                        t_elem = entry.find("atom:title", ns)
                        if t_elem is not None and t_elem.text:
                            clean_title = t_elem.text.strip().replace("\n", " ")
                            r_title = requests.get(
                                "https://api.openalex.org/works",
                                params={"search": clean_title, "per_page": 1},
                                headers=HEADERS,
                                timeout=10
                            )
                            if r_title.status_code == 200:
                                results = r_title.json().get("results", [])
                                if results:
                                    return results[0]
            except Exception:
                pass

    # 2. OpenAlex Work ID (e.g. W2952052407 or https://openalex.org/W2952052407)
    m_wid = re.search(r'\b(W\d{8,12})\b', seed)
    if m_wid:
        try:
            r = requests.get(f"https://api.openalex.org/works/{m_wid.group(1)}", headers=HEADERS, timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass

    # 3. Standard DOI resolution (10.xxxx/yyyy)
    m_doi = re.search(r'(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', seed)
    if m_doi:
        doi = m_doi.group(1).rstrip(".")
        try:
            r = requests.get(f"https://api.openalex.org/works/https://doi.org/{doi}", headers=HEADERS, timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass

        # Fallback: Query Crossref to extract title, then search OpenAlex
        try:
            r_cr = requests.get(f"https://api.crossref.org/works/{doi}", headers=HEADERS, timeout=8)
            if r_cr.status_code == 200:
                titles = r_cr.json().get("message", {}).get("title", [])
                if titles:
                    r_s = requests.get(
                        "https://api.openalex.org/works",
                        params={"search": titles[0], "per_page": 1},
                        headers=HEADERS,
                        timeout=10
                    )
                    if r_s.status_code == 200:
                        results = r_s.json().get("results", [])
                        if results:
                            return results[0]
        except Exception:
            pass

    # 4. PubMed / NLM PMID resolution
    m_pmid = re.search(r'(?:pmid[:\s/]+|pubmed\.ncbi\.nlm\.nih\.gov/|pubmed/)(\d{6,9})', seed, re.IGNORECASE)
    if m_pmid:
        try:
            pmid = m_pmid.group(1)
            r = requests.get(
                "https://api.openalex.org/works",
                params={"filter": f"pmid:{pmid}", "per_page": 1},
                headers=HEADERS,
                timeout=10
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    return results[0]
        except Exception:
            pass

    # 5. General Fallback: Search OpenAlex by query text / title
    clean_search = re.sub(r'https?://[^\s]+', '', seed).strip() or seed
    try:
        r = requests.get(
            "https://api.openalex.org/works",
            params={"search": clean_search, "per_page": 1},
            headers=HEADERS,
            timeout=10
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                return results[0]
    except Exception:
        pass

    return None


def explore_citation_graph(seed_doi_or_query, mode="related", limit=6):
    """Explores citation networks around a seed paper (related co-citations, forward citing works, or backward seminal references)."""
    seed_work = resolve_seed_work(seed_doi_or_query)
    if not seed_work:
        return {
            "status": "not_found",
            "seed_query": seed_doi_or_query,
            "message": f"No works matching seed query: {seed_doi_or_query}"
        }

    work_id = seed_work.get("id", "").split("/")[-1]
    seed_info = {
        "title": seed_work.get("title"),
        "doi": seed_work.get("doi"),
        "year": seed_work.get("publication_year"),
        "openalex_id": work_id
    }

    try:
        if mode in ["forward", "cites"]:
            graph_url = f"https://api.openalex.org/works?filter=cites:{work_id}&per-page={limit}"
        elif mode in ["backward", "cited_by"]:
            ref_ids = [ref.split("/")[-1] for ref in seed_work.get("referenced_works", [])[:limit]]
            if not ref_ids:
                return {
                    "status": "success",
                    "seed_paper": seed_info,
                    "mode": mode,
                    "total_connected": 0,
                    "connected_works": [],
                    "message": "No referenced foundational works are indexed for this paper/preprint."
                }
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
