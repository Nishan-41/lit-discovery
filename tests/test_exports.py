"""Unit tests for Zotero, BibTeX, and RIS citation export module."""
import os
import tempfile
import pytest

from lit_discovery.exports.zotero import export_zotero_references


def test_export_zotero_fallback_entries():
    articles = [
        {
            "title": "Synthesis of Super-Tough Ionogels",
            "authors": ["John Doe", "Jane Smith"],
            "year": 2024,
            "journal": "Nature Materials",
            "doi": "https://doi.org/10.1038/s41563-020-00831-2"
        },
        {
            "title": "Aramid Nanofiber Solid Electrolytes",
            "authors": ["Alice Walker"],
            "year": 2023,
            "journal": "ACS Energy Letters",
            "doi": None
        }
    ]

    with tempfile.TemporaryDirectory() as td:
        bib_file = os.path.join(td, "output.bib")
        ris_file = os.path.join(td, "output.ris")

        stats = export_zotero_references(articles, bib_path=bib_file, ris_path=ris_file)

        assert stats["bibtex_count"] == 2
        assert stats["ris_count"] == 2

        assert os.path.exists(bib_file)
        assert os.path.exists(ris_file)

        with open(bib_file, "r", encoding="utf-8") as f:
            bib_content = f.read()
            assert "@article" in bib_content or "@Article" in bib_content

        with open(ris_file, "r", encoding="utf-8") as f:
            ris_content = f.read()
            assert "TY  - JOUR" in ris_content
            assert "ER  - " in ris_content
