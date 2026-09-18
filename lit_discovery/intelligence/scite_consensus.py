"""scite.ai Smart Citations sentiment & consensus tallies."""
import requests

HEADERS = {"User-Agent": "LitDiscovery/1.0 (mailto:rehan@arizona.edu)"}

def resolve_scite_tallies(doi):
    """Queries scite.ai API for empirical tallies: supporting, contrasting, and mentioning citations."""
    if not doi:
        return None
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if not clean_doi or "10." not in clean_doi:
        return None
    try:
        r = requests.get(f"https://api.scite.ai/tallies/{clean_doi}", headers=HEADERS, timeout=6)
        if r.status_code == 200:
            d = r.json()
            return {
                "supporting": d.get("supporting", 0),
                "contrasting": d.get("contradicting", 0),
                "contradicting": d.get("contradicting", 0),
                "mentioning": d.get("mentioning", 0),
                "total_citations": d.get("total", 0),
                "citing_publications": d.get("citingPublications", 0)
            }
    except Exception:
        pass
    return None
