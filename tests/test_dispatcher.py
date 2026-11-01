"""Search identity, source provenance, selection, and validation regressions."""
from unittest.mock import patch

import pytest

from lit_discovery import search_literature


def run(adapters, **kwargs):
    with patch.dict("lit_discovery.core.dispatcher.AVAILABLE_ENGINES", adapters, clear=True):
        return search_literature("polymer", enrich=False, **kwargs)


def test_duplicate_doi_merges_sources_and_richer_abstract():
    short = {"title": "Polymer research", "doi": "10.1234/paper", "abstract": "Short"}
    richer = dict(short, doi="https://doi.org/10.1234/paper", abstract="A longer polymer abstract")
    result = run({"one": lambda *a: [short], "two": lambda *a: [richer]})
    assert result["total_articles_retrieved"] == 1
    article = result["articles"][0]
    assert article["source_databases"] == ["one", "two"]
    assert article["abstract"] == richer["abstract"]


def test_same_title_different_dois_remain_distinct():
    papers = [{"title": "Polymer research", "doi": f"10.1234/{suffix}"} for suffix in ("a", "b")]
    assert run({"one": lambda *a: papers})["total_articles_retrieved"] == 2


def test_unknown_engine_rejected_before_request():
    with pytest.raises(ValueError, match="Unknown engines"):
        search_literature("polymer", selected_engines=["typo"], enrich=False)


def test_missing_abstract_not_replaced_with_access_claim():
    result = run({"one": lambda *a: [{"title": "Polymer research", "abstract": None}]})
    assert result["articles"][0]["abstract"] is None
