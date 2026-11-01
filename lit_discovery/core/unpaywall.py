"""Automated legal open-access PDF resolver via Unpaywall API."""
import os

import requests

def resolve_unpaywall_pdf(doi, email=None):
    """Resolves direct legal open-access PDF URLs for any DOI via Unpaywall."""
    email = email or os.getenv("CHEM_MAT_HUB_UNPAYWALL_EMAIL") or os.getenv("UNPAYWALL_EMAIL")
    if not doi or not email:
        return None
    clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    try:
        r = requests.get(f"https://api.unpaywall.org/v2/{clean_doi}", params={"email": email}, timeout=5)
        if r.status_code == 200:
            best = r.json().get("best_oa_location") or {}
            return best.get("url_for_pdf") or best.get("url")
    except Exception:
        pass
    return None
