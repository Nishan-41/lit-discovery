"""Controlled provider fixtures for citation counts and OpenAlex traversal."""
from unittest.mock import Mock

import pytest

from lit_discovery.intelligence.scite_consensus import resolve_scite_tallies
from lit_discovery.intelligence.citation_graph import explore_citation_graph


def test_resolve_scite_tallies(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"supporting": 4, "contradicting": 1, "mentioning": 7, "total": 12}
    monkeypatch.setattr("lit_discovery.intelligence.scite_consensus.requests.get", Mock(return_value=response))
    tallies = resolve_scite_tallies("10.1234/fixture")
    assert tallies["total_citations"] == 12
    assert tallies["supporting"] == 4
    assert tallies["contrasting"] == 1


def test_resolve_scite_tallies_invalid():
    for value in ("", None, "invalid_doi"):
        assert resolve_scite_tallies(value) is None


@pytest.mark.parametrize("seed", ["10.1234/fixture", "http://arxiv.org/abs/1409.4962v1"])
@pytest.mark.parametrize("mode,filter_text", [("related", "related_to:"), ("forward", "cites:"), ("backward", "openalex_id:")])
def test_citation_graph_routes(seed, mode, filter_text, monkeypatch):
    work = {
        "id": "https://openalex.org/W2952052407", "title": "Synthetic seed",
        "doi": "https://doi.org/10.1234/fixture", "publication_year": 2026,
        "referenced_works": ["https://openalex.org/W1234567890"],
    }
    connected = {"id": "https://openalex.org/W1234567890", "title": "Synthetic connected work", "doi": None}
    requested = []

    def fake_get(url, **kwargs):
        requested.append(url)
        response = Mock(status_code=200)
        response.json.return_value = {"results": [connected]} if "?filter=" in url else work
        return response

    monkeypatch.setattr("lit_discovery.intelligence.citation_graph.requests.get", fake_get)
    result = explore_citation_graph(seed, mode=mode, limit=3)
    assert result["status"] == "success"
    assert result["seed_paper"]["openalex_id"] == "W2952052407"
    assert len(result["connected_works"]) == 1
    assert filter_text in requested[-1]
