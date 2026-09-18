"""Unit tests for scite.ai Smart Citations and Citation Graph snowballing."""
import pytest
from lit_discovery.intelligence.scite_consensus import resolve_scite_tallies
from lit_discovery.intelligence.citation_graph import explore_citation_graph


def test_resolve_scite_tallies_landmark():
    # Verified landmark paper with rich citation sentiment
    doi = "10.1038/nature12373"
    tallies = resolve_scite_tallies(doi)

    assert tallies is not None
    assert "total_citations" in tallies
    assert "supporting" in tallies
    assert "contrasting" in tallies
    assert tallies["total_citations"] > 0
    assert tallies["supporting"] > 0


def test_resolve_scite_tallies_invalid():
    assert resolve_scite_tallies("") is None
    assert resolve_scite_tallies(None) is None
    assert resolve_scite_tallies("invalid_doi") is None


def test_explore_citation_graph_openalex():
    # Known OpenAlex DOI
    res = explore_citation_graph("10.1038/s41563-022-01195-4", mode="related", limit=3)

    assert res is not None
    assert res.get("status") == "success"
    assert "seed_paper" in res
    assert "connected_works" in res
    assert len(res["connected_works"]) <= 3
