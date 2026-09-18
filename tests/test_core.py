"""Unit tests for core relevance, inverted index parsing, and Unpaywall resolution."""
import pytest
from lit_discovery.core.relevance import (
    calculate_relevance_rating,
    clean_xml_abstract,
    reconstruct_inverted_abstract
)
from lit_discovery.core.unpaywall import resolve_unpaywall_pdf


def test_relevance_rating_high_match():
    query = "polybenzoxazole ionogel ionic conductivity"
    title = "High-Performance Polybenzoxazole Ionogels with Remarkable Ionic Conductivity"
    abstract = "We demonstrate a novel ionogel based on polybenzoxazole with superior ionic conductivity."
    res = calculate_relevance_rating(query, title, abstract)

    assert "score_percent" in res
    assert "confidence_tier" in res
    assert "relevance_level" in res
    assert res["score_percent"] >= 85
    assert res["confidence_tier"] == "High"


def test_relevance_rating_empty_query():
    res = calculate_relevance_rating("", "Title", "Abstract")
    assert res["score_percent"] == 85
    assert res["confidence_tier"] == "Standard"


def test_clean_xml_abstract():
    raw_html = "<jats:p>This is a <b>bold</b> experiment with &amp; symbols.</jats:p>"
    cleaned = clean_xml_abstract(raw_html)
    assert cleaned == "This is a bold experiment with & symbols."


def test_reconstruct_inverted_abstract():
    inverted = {
        "Novel": [0],
        "solid": [1],
        "polymer": [2],
        "electrolytes": [3],
        "for": [4],
        "batteries": [5]
    }
    reconstructed = reconstruct_inverted_abstract(inverted)
    assert reconstructed == "Novel solid polymer electrolytes for batteries"


def test_reconstruct_inverted_abstract_empty():
    assert reconstruct_inverted_abstract(None) is None
    assert reconstruct_inverted_abstract({}) is None


def test_unpaywall_pdf_resolution():
    # Verified open-access DOI
    pdf_url = resolve_unpaywall_pdf("10.1038/nature12373")
    assert pdf_url is not None
    assert pdf_url.startswith("http")
