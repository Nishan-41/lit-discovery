"""Unit tests for Zotero, BibTeX, and RIS citation export module."""
import os
import tempfile
import pytest

from lit_discovery.exports.zotero import export_zotero_references


def test_export_zotero_fallback_entries(monkeypatch):
    monkeypatch.setattr("lit_discovery.exports.zotero.fetch_doi_citation_metadata", lambda *args: None)
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


def test_missing_metadata_is_not_invented(tmp_path):
    bib, ris = tmp_path / "nested" / "refs.bib", tmp_path / "nested" / "refs.ris"
    export_zotero_references([{"title": "Unknown year & {sample}", "doi": "https://arxiv.org/abs/1234.5678"}], bib_path=bib, ris_path=ris)
    assert "year=" not in bib.read_text()
    assert "journal=" not in bib.read_text()
    assert "PY  -" not in ris.read_text()
    assert "DO  -" not in ris.read_text()
    assert "UR  - https://arxiv.org" in ris.read_text()
    assert r"\&" in bib.read_text() and r"\{sample\}" in bib.read_text()


def test_html_citation_response_uses_fallback(monkeypatch, tmp_path):
    from unittest.mock import Mock
    response = Mock(status_code=200, text="<html>Publisher login</html>")
    monkeypatch.setattr("lit_discovery.exports.zotero.requests.get", Mock(return_value=response))
    path = tmp_path / "refs.bib"
    export_zotero_references([{"title": "Fixture", "doi": "10.1234/fixture"}], bib_path=path)
    assert path.read_text().startswith("@article")
    assert "<html>" not in path.read_text()
