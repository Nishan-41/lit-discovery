"""BibTeX and RIS exports with publisher metadata and explicit local fallbacks."""
import concurrent.futures
from pathlib import Path
import re

import requests

HEADERS = {"User-Agent": "LitDiscovery/1.0"}


def normalize_doi(value):
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(value or "").strip(), flags=re.I)
    return value if re.fullmatch(r"10\.\d{4,9}/\S+", value) else None


def fetch_doi_citation_metadata(doi, format_type="bibtex"):
    """Fetch a citation through DOI content negotiation; reject HTML landing pages."""
    clean_doi = normalize_doi(doi)
    if not clean_doi:
        return None
    mime = "application/x-bibtex" if format_type == "bibtex" else "application/x-research-info-systems"
    try:
        response = requests.get(
            f"https://doi.org/{clean_doi}", headers={"Accept": mime, **HEADERS}, timeout=8
        )
        text = response.text.strip()
        if response.status_code != 200:
            return None
        if format_type == "bibtex" and re.match(r"@\w+\s*[{(]", text):
            return text
        if format_type == "ris" and text.startswith("TY  -") and "ER  -" in text:
            return text
    except requests.RequestException:
        pass
    return None


def bibtex_text(value):
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#", "$": r"\$"}
    return "".join(replacements.get(char, char) for char in str(value).replace("\n", " "))


def fallback(article, index, format_type):
    title = article.get("title") or "Untitled"
    authors = article.get("authors") or []
    year = str(article.get("year") or "")
    year = year if re.fullmatch(r"\d{4}", year) else None
    doi = normalize_doi(article.get("doi"))
    fields = {"title": title}
    if authors:
        fields["author"] = " and ".join(authors)
    if article.get("journal"):
        fields["journal"] = article["journal"]
    if year:
        fields["year"] = year
    if doi:
        fields["doi"] = doi
    elif article.get("doi"):
        fields["url"] = article["doi"]
    if format_type == "bibtex":
        key = re.sub(r"[^A-Za-z0-9_]", "", f"{authors[0].split()[-1] if authors else 'Ref'}_{year or 'undated'}_{index}")
        content = ",\n".join(f"  {name}={{{bibtex_text(value)}}}" for name, value in fields.items())
        return f"@article{{{key},\n{content}\n}}"
    lines = ["TY  - JOUR", f"TI  - {title.replace(chr(10), ' ')}"]
    for name, tag in (("journal", "JO"), ("year", "PY"), ("doi", "DO"), ("url", "UR")):
        if name in fields:
            lines.append(f"{tag}  - {str(fields[name]).replace(chr(10), ' ')}")
    lines.extend(f"AU  - {author.replace(chr(10), ' ')}" for author in authors)
    return "\n".join([*lines, "ER  - "])


def export_zotero_references(articles, bib_path=None, ris_path=None):
    """Write citations without inventing missing years, authors, journals, or DOIs."""
    paths = {"bibtex": bib_path, "ris": ris_path}
    entries = {kind: [] for kind in paths}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            (index, kind): pool.submit(fetch_doi_citation_metadata, article.get("doi"), kind)
            for index, article in enumerate(articles)
            for kind, path in paths.items()
            if path and normalize_doi(article.get("doi"))
        }
        for index, article in enumerate(articles):
            for kind, path in paths.items():
                if not path:
                    continue
                future = futures.get((index, kind))
                entry = future.result() if future else None
                entries[kind].append(entry or fallback(article, index, kind))
    for kind, path in paths.items():
        if path:
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("\n\n".join(entries[kind]), encoding="utf-8")
    return {
        "bibtex_count": len(entries["bibtex"]), "ris_count": len(entries["ris"]),
        "bib_path": str(bib_path) if bib_path is not None else None,
        "ris_path": str(ris_path) if ris_path is not None else None,
    }
