"""Publisher-grade BibTeX and RIS citation export for Zotero, Mendeley & Overleaf."""
import concurrent.futures
import re
import requests

HEADERS = {"User-Agent": "LitDiscovery/1.0 (mailto:rehan@arizona.edu)"}

def fetch_doi_citation_metadata(doi, format_type="bibtex"):
    """Fetches official publisher citation metadata via DOI content negotiation."""
    if not doi:
        return None
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if not clean_doi or "10." not in clean_doi:
        return None
    mime = "application/x-bibtex" if format_type == "bibtex" else "application/x-research-info-systems"
    try:
        r = requests.get(f"https://doi.org/{clean_doi}", headers={"Accept": mime, **HEADERS}, timeout=8)
        if r.status_code == 200 and r.text.strip():
            return r.text.strip()
    except Exception:
        pass
    return None

def export_zotero_references(articles, bib_path=None, ris_path=None):
    """Exports articles into BibTeX (.bib) and RIS (.ris) files."""
    bib_entries = []
    ris_entries = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        bib_futs = {}
        ris_futs = {}
        for idx, a in enumerate(articles):
            doi = a.get("doi")
            if doi and "10." in doi:
                if bib_path:
                    bib_futs[idx] = ex.submit(fetch_doi_citation_metadata, doi, "bibtex")
                if ris_path:
                    ris_futs[idx] = ex.submit(fetch_doi_citation_metadata, doi, "ris")
                    
        for idx, a in enumerate(articles):
            doi = a.get("doi")
            title = a.get("title", "Untitled")
            authors = a.get("authors", [])
            author_str = " and ".join(authors) if authors else "Unknown"
            year = a.get("year") or 2024
            journal = a.get("journal") or "Academic Publication"
            
            if bib_path:
                entry = None
                if idx in bib_futs:
                    try:
                        entry = bib_futs[idx].result()
                    except Exception:
                        pass
                if not entry:
                    cite_key = f"{(authors[0].split()[-1] if authors else 'Ref')}_{year}_{idx}"
                    clean_key = re.sub(r'[^a-zA-Z0-9_]', '', cite_key)
                    entry = (
                        f"@article{{{clean_key},\n"
                        f"  title={{{title}}},\n"
                        f"  author={{{author_str}}},\n"
                        f"  journal={{{journal}}},\n"
                        f"  year={{{year}}}"
                        + (f",\n  doi={{{doi}}}" if doi else "")
                        + "\n}"
                    )
                bib_entries.append(entry)
                
            if ris_path:
                entry = None
                if idx in ris_futs:
                    try:
                        entry = ris_futs[idx].result()
                    except Exception:
                        pass
                if not entry:
                    lines = [
                        "TY  - JOUR",
                        f"TI  - {title}",
                        f"JO  - {journal}",
                        f"PY  - {year}"
                    ]
                    for aut in authors:
                        lines.append(f"AU  - {aut}")
                    if doi:
                        lines.append(f"DO  - {doi}")
                    lines.append("ER  - ")
                    entry = "\n".join(lines)
                ris_entries.append(entry)
                
    if bib_path and bib_entries:
        with open(bib_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(bib_entries))
            
    if ris_path and ris_entries:
        with open(ris_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(ris_entries))
            
    return {
        "bibtex_count": len(bib_entries),
        "ris_count": len(ris_entries),
        "bib_path": bib_path,
        "ris_path": ris_path
    }
