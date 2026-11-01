"""Academic search engine clients for 12 scientific databases."""
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from dotenv import load_dotenv

from lit_discovery.core.relevance import (
    calculate_relevance_rating,
    clean_xml_abstract,
    reconstruct_inverted_abstract
)

load_dotenv()
load_dotenv(os.path.expanduser("~/.env"))

S2_KEY = os.environ.get("S2_API_KEY") or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
CORE_KEY = os.environ.get("CORE_API_KEY")
SCOPUS_KEY = os.environ.get("SCOPUS_API_KEY") or os.environ.get("ELSEVIER_API_KEY")
HEADERS = {"User-Agent": "LitDiscovery/1.0"}

def fetch_openalex_literature(query_text, limit=5):
    """Queries OpenAlex global scientific graph and reconstructs inverted-index abstracts."""
    try:
        url = f"https://api.openalex.org/works?search={urllib.parse.quote(query_text)}&per_page={limit}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        articles = []
        if r.status_code == 200:
            for w in r.json().get("results", []):
                abstract = reconstruct_inverted_abstract(w.get("abstract_inverted_index"))
                title = w.get("title", "")
                authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", []) if a.get("author", {}).get("display_name")]
                doi = w.get("doi")
                oa = w.get("open_access", {})
                pdf_url = oa.get("oa_url") if oa.get("is_oa") else None
                articles.append({
                    "engine": "OpenAlex",
                    "title": title,
                    "doi": doi,
                    "authors": authors[:5],
                    "year": w.get("publication_year"),
                    "abstract": abstract,
                    "open_access_pdf": pdf_url,
                    "journal": w.get("primary_location", {}).get("source", {}).get("display_name") if w.get("primary_location") and w.get("primary_location", {}).get("source") else None,
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_semantic_scholar_literature(query_text, limit=5):
    """Queries Semantic Scholar for papers with AI TL;DR summaries and structured abstracts."""
    try:
        headers = dict(HEADERS)
        if S2_KEY:
            headers["x-api-key"] = S2_KEY
        fields = "title,authors,year,abstract,tldr,openAccessPdf,externalIds,venue"
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(query_text)}&limit={limit}&fields={fields}"
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 429:
            import time
            time.sleep(2)
            r = requests.get(url, headers=headers, timeout=12)
        articles = []
        if r.status_code == 200:
            for p in r.json().get("data", []):
                ext_ids = p.get("externalIds") or {}
                doi = ext_ids.get("DOI")
                if doi and not doi.startswith("http"):
                    doi = f"https://doi.org/{doi}"
                oa = p.get("openAccessPdf") or {}
                pdf_url = oa.get("url")
                title = p.get("title", "")
                abstract = p.get("abstract", "")
                tldr = p.get("tldr", {}).get("text") if p.get("tldr") else None
                authors = [a.get("name") for a in p.get("authors", []) if a.get("name")]
                articles.append({
                    "engine": "Semantic Scholar",
                    "title": title,
                    "doi": doi,
                    "authors": authors[:5],
                    "year": p.get("year"),
                    "tldr": tldr,
                    "abstract": abstract,
                    "open_access_pdf": pdf_url,
                    "journal": p.get("venue"),
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_europe_pmc_literature(query_text, limit=5):
    """Queries Europe PMC (EMBL-EBI) for open-access papers, PMCID, and structured XML abstracts."""
    try:
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(query_text)}+OPEN_ACCESS:y&format=json&resultType=core&pageSize={limit}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        articles = []
        if r.status_code == 200:
            for item in r.json().get("resultList", {}).get("result", []):
                abstract = clean_xml_abstract(item.get("abstractText"))
                title = item.get("title", "")
                doi = f"https://doi.org/{item.get('doi')}" if item.get("doi") else None
                pmcid = item.get("pmcid")
                pdf_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf" if pmcid else None
                author_str = item.get("authorString", "")
                authors = [a.strip() for a in author_str.split(",") if a.strip()][:5]
                articles.append({
                    "engine": "Europe PMC",
                    "title": title,
                    "doi": doi,
                    "authors": authors,
                    "year": int(item.get("pubYear")) if item.get("pubYear") and item.get("pubYear").isdigit() else None,
                    "abstract": abstract,
                    "open_access_pdf": pdf_url,
                    "journal": item.get("journalTitle"),
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_arxiv_literature(query_text, limit=5):
    """Queries arXiv API for preprints with direct PDF download links."""
    try:
        url = f"https://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote(query_text)}&start=0&max_results={limit}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        articles = []
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                abstract = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
                arxiv_id_url = entry.find("atom:id", ns).text.strip()
                published = entry.find("atom:published", ns).text.strip()
                year = int(published[:4]) if published else None
                authors = [author.find("atom:name", ns).text for author in entry.findall("atom:author", ns)]
                pdf_url = arxiv_id_url.replace("abs", "pdf") + ".pdf"
                
                raw_id = re.sub(r'v\d+$', '', arxiv_id_url.split('/')[-1])
                doi_elem = entry.find("{http://arxiv.org/schemas/atom}doi")
                if doi_elem is None:
                    doi_elem = entry.find("arxiv:doi", {"arxiv": "http://arxiv.org/schemas/atom"})
                doi_val = f"https://doi.org/{doi_elem.text.strip()}" if (doi_elem is not None and doi_elem.text) else f"https://doi.org/10.48550/arXiv.{raw_id}"

                articles.append({
                    "engine": "arXiv Preprints",
                    "title": title,
                    "doi": doi_val,
                    "arxiv_id": raw_id,
                    "arxiv_url": arxiv_id_url,
                    "authors": authors[:5],
                    "year": year,
                    "abstract": abstract,
                    "open_access_pdf": pdf_url,
                    "journal": "arXiv Preprint",
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_crossref_literature(query_text, limit=5):
    """Queries Crossref official registry for metadata and abstracts."""
    try:
        url = f"https://api.crossref.org/works?query={urllib.parse.quote(query_text)}&rows={limit}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        articles = []
        if r.status_code == 200:
            for item in r.json().get("message", {}).get("items", []):
                title = item.get("title", [""])[0] if item.get("title") else ""
                abstract = clean_xml_abstract(item.get("abstract"))
                doi = f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else None
                year = None
                if "published-print" in item and "date-parts" in item["published-print"]:
                    year = item["published-print"]["date-parts"][0][0]
                elif "published-online" in item and "date-parts" in item["published-online"]:
                    year = item["published-online"]["date-parts"][0][0]
                authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get("author", []) if "family" in a]
                articles.append({
                    "engine": "Crossref",
                    "title": title,
                    "doi": doi,
                    "authors": authors[:5],
                    "year": year,
                    "abstract": abstract,
                    "open_access_pdf": None,
                    "journal": item.get("container-title", [""])[0] if item.get("container-title") else None,
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_scopus_literature(query_text, limit=5):
    """Queries Elsevier Scopus API and retrieves peer-reviewed abstracts."""
    if not SCOPUS_KEY:
        return []
    try:
        url = "https://api.elsevier.com/content/search/scopus"
        headers = {"X-ELS-APIKey": SCOPUS_KEY, "Accept": "application/json", **HEADERS}
        safe_query = f"TITLE-ABS-KEY({query_text})"
        r = requests.get(url, headers=headers, params={"query": safe_query, "count": limit}, timeout=12)
        articles = []
        if r.status_code == 200:
            entries = r.json().get("search-results", {}).get("entry", [])
            for item in entries:
                title = item.get("dc:title", "")
                doi = f"https://doi.org/{item.get('prism:doi')}" if item.get("prism:doi") else None
                authors = [item.get("dc:creator")] if item.get("dc:creator") else []
                cover_date = item.get("prism:coverDate", "")
                year = int(cover_date[:4]) if cover_date and cover_date[:4].isdigit() else None
                abstract = None
                raw_doi = item.get("prism:doi")
                if raw_doi:
                    try:
                        r_abs = requests.get(
                            f"https://api.elsevier.com/content/abstract/doi/{raw_doi}",
                            headers={"X-ELS-APIKey": SCOPUS_KEY, "Accept": "application/json", **HEADERS},
                            timeout=8
                        )
                        if r_abs.status_code == 200:
                            core = r_abs.json().get("abstracts-retrieval-response", {}).get("coredata", {})
                            abstract = core.get("dc:description")
                    except Exception:
                        pass
                articles.append({
                    "engine": "Elsevier Scopus",
                    "title": title,
                    "doi": doi,
                    "authors": authors,
                    "year": year,
                    "abstract": abstract,
                    "open_access_pdf": None,
                    "journal": item.get("prism:publicationName"),
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_osti_literature(query_text, limit=5):
    """Queries U.S. Department of Energy (OSTI.gov) for energy & national lab papers."""
    try:
        url = "https://www.osti.gov/api/v1/records"
        params = {"term": query_text, "rows": limit}
        headers = {"Accept": "application/json", **HEADERS}
        r = requests.get(url, headers=headers, params=params, timeout=12)
        articles = []
        if r.status_code == 200:
            for item in r.json():
                title = item.get("title", "")
                abstract = item.get("description")
                doi = f"https://doi.org/{item.get('doi')}" if item.get("doi") else None
                pub_date = item.get("publication_date", "")
                year = int(pub_date[:4]) if pub_date and pub_date[:4].isdigit() else None
                authors = item.get("authors", []) if isinstance(item.get("authors"), list) else []
                pdf_url = item.get("links", {}).get("fulltext") if isinstance(item.get("links"), dict) else None
                articles.append({
                    "engine": "OSTI.gov (DOE)",
                    "title": title,
                    "doi": doi,
                    "authors": authors[:5],
                    "year": year,
                    "abstract": abstract,
                    "open_access_pdf": pdf_url,
                    "journal": item.get("publisher") or "DOE National Laboratory Report",
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_doaj_literature(query_text, limit=5):
    """Queries Directory of Open Access Journals (DOAJ)."""
    try:
        url = f"https://doaj.org/api/v2/search/articles/{urllib.parse.quote(query_text)}?pageSize={limit}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        articles = []
        if r.status_code == 200:
            for res in r.json().get("results", []):
                bib = res.get("bibjson", {})
                title = bib.get("title", "")
                abstract = bib.get("abstract", "")
                year = int(bib.get("year")) if bib.get("year") and str(bib.get("year")).isdigit() else None
                doi = None
                for ident in bib.get("identifier", []):
                    if ident.get("type") == "doi":
                        doi = f"https://doi.org/{ident.get('id')}"
                        break
                authors = [a.get("name") for a in bib.get("author", []) if a.get("name")]
                pdf_url = None
                for link in bib.get("link", []):
                    if link.get("type") == "fulltext":
                        pdf_url = link.get("url")
                        break
                articles.append({
                    "engine": "DOAJ (Open Access)",
                    "title": title,
                    "doi": doi,
                    "authors": authors[:5],
                    "year": year,
                    "abstract": abstract,
                    "open_access_pdf": pdf_url,
                    "journal": bib.get("journal", {}).get("title"),
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_datacite_literature(query_text, limit=5):
    """Queries DataCite for open datasets, theses, and preprints."""
    try:
        url = f"https://api.datacite.org/dois?query={urllib.parse.quote(query_text)}&page[size]={limit}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        articles = []
        if r.status_code == 200:
            for item in r.json().get("data", []):
                attrs = item.get("attributes", {})
                title = attrs.get("titles", [{}])[0].get("title", "") if attrs.get("titles") else ""
                abstract = attrs.get("descriptions", [{}])[0].get("description", "") if attrs.get("descriptions") else ""
                doi = f"https://doi.org/{attrs.get('doi')}" if attrs.get("doi") else None
                year = attrs.get("publicationYear")
                authors = [c.get("name") for c in attrs.get("creators", []) if c.get("name")]
                articles.append({
                    "engine": "DataCite",
                    "title": title,
                    "doi": doi,
                    "authors": authors[:5],
                    "year": year,
                    "abstract": abstract,
                    "open_access_pdf": None,
                    "journal": attrs.get("publisher") or "Research Repository",
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_pubmed_literature(query_text, limit=5):
    """Queries PubMed (NLM E-utilities) for biomedical and biomaterials literature."""
    try:
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={urllib.parse.quote(query_text)}&retmode=json&retmax={limit}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        articles = []
        if r.status_code == 200:
            ids = r.json().get("esearchresult", {}).get("idlist", [])
            if ids:
                id_str = ",".join(ids)
                s_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={id_str}&retmode=json"
                r_sum = requests.get(s_url, headers=HEADERS, timeout=10)
                if r_sum.status_code == 200:
                    res_dict = r_sum.json().get("result", {})
                    for pmid in ids:
                        item = res_dict.get(pmid, {})
                        title = item.get("title", "")
                        authors = [a.get("name") for a in item.get("authors", []) if a.get("name")]
                        pubdate = item.get("pubdate", "")
                        year = int(pubdate[:4]) if pubdate and pubdate[:4].isdigit() else None
                        doi = None
                        for aid in item.get("articleids", []):
                            if aid.get("idtype") == "doi":
                                doi = f"https://doi.org/{aid.get('value')}"
                                break
                        articles.append({
                            "engine": "PubMed (NLM)",
                            "title": title,
                            "doi": doi or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                            "authors": authors[:5],
                            "year": year,
                            "abstract": None,
                            "open_access_pdf": None,
                            "journal": item.get("source"),
                            "relevance": calculate_relevance_rating(query_text, title, "")
                        })
        return articles
    except Exception:
        return []

def fetch_core_literature(query_text, limit=5):
    """Queries CORE open access university and institutional repositories."""
    if not CORE_KEY:
        return []
    try:
        url = f"https://api.core.ac.uk/v3/search/works?q={urllib.parse.quote(query_text)}&limit={limit}"
        headers = {"Authorization": f"Bearer {CORE_KEY}", **HEADERS}
        r = requests.get(url, headers=headers, timeout=12)
        articles = []
        if r.status_code == 200:
            for item in r.json().get("results", []):
                title = item.get("title", "")
                abstract = item.get("abstract")
                doi = f"https://doi.org/{item.get('doi')}" if item.get("doi") else None
                year = item.get("yearPublished")
                authors = [a.get("name") for a in item.get("authors", []) if a.get("name")]
                pdf_url = item.get("downloadUrl")
                articles.append({
                    "engine": "CORE Repositories",
                    "title": title,
                    "doi": doi,
                    "authors": authors[:5],
                    "year": year,
                    "abstract": abstract,
                    "open_access_pdf": pdf_url,
                    "journal": item.get("publisher") or "University / Institutional Repository",
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []

def fetch_zenodo_literature(query_text, limit=5):
    """Queries Zenodo (CERN / OpenAIRE) for scientific records and open datasets."""
    try:
        url = "https://zenodo.org/api/records"
        params = {"q": query_text, "size": limit}
        r = requests.get(url, headers=HEADERS, params=params, timeout=12)
        articles = []
        if r.status_code == 200:
            for item in r.json().get("hits", {}).get("hits", []):
                meta = item.get("metadata", {})
                title = meta.get("title", "")
                abstract = clean_xml_abstract(meta.get("description", ""))
                doi = f"https://doi.org/{meta.get('doi')}" if meta.get("doi") else None
                pub_date = meta.get("publication_date", "")
                year = int(pub_date[:4]) if pub_date and pub_date[:4].isdigit() else None
                authors = [c.get("name") for c in meta.get("creators", []) if c.get("name")]
                pdf_url = None
                for f in item.get("files", []):
                    if f.get("key", "").endswith(".pdf"):
                        pdf_url = f.get("links", {}).get("self")
                        break
                articles.append({
                    "engine": "Zenodo (CERN)",
                    "title": title,
                    "doi": doi,
                    "authors": authors[:5],
                    "year": year,
                    "abstract": abstract,
                    "open_access_pdf": pdf_url,
                    "journal": "Zenodo Open Science Repository",
                    "relevance": calculate_relevance_rating(query_text, title, abstract)
                })
        return articles
    except Exception:
        return []
