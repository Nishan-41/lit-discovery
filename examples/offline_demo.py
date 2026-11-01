"""Reproducible search/export demonstration with synthetic, non-publication fixtures."""
from pathlib import Path
import tempfile
from unittest.mock import patch

from lit_discovery import export_zotero_references, search_literature


def main():
    shared = {
        "title": "Synthetic fixture: polymer electrolyte conductivity",
        "authors": ["Demo Researcher"],
        "abstract": "Synthetic metadata for the offline demonstration.",
        "year": None,
        "doi": None,
    }
    second = {
        "title": "Synthetic fixture: aramid polymer electrolyte",
        "authors": ["Example Author"],
        "abstract": "Synthetic metadata; not a real publication.",
        "doi": None,
    }
    adapters = {
        "crossref": lambda query, limit: [shared],
        "openalex": lambda query, limit: [dict(shared), second],
    }
    with patch.dict("lit_discovery.core.dispatcher.AVAILABLE_ENGINES", adapters, clear=True):
        result = search_literature("polymer electrolyte", enrich=False)
    with tempfile.TemporaryDirectory(prefix="lit-discovery-demo-") as temporary:
        stats = export_zotero_references(
            result["articles"], bib_path=Path(temporary) / "references.bib",
            ris_path=Path(temporary) / "references.ris",
        )
        shared_record = next(paper for paper in result["articles"] if paper["title"] == shared["title"])
        print("LitDiscovery | offline demonstration")
        print("Data: synthetic fixtures; no network requests")
        print(f"Adapters: {len(adapters)} | Unique papers: {result['total_articles_retrieved']} | Returned: {result['total_articles_shown']}")
        print("Sources merged: " + ", ".join(shared_record["source_databases"]))
        print(f"Exports: {stats['bibtex_count']} BibTeX entries, {stats['ris_count']} RIS entries")


if __name__ == "__main__":
    main()
