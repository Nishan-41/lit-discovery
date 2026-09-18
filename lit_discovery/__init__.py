"""LitDiscovery: Scientific literature discovery, smart citation consensus, and research intelligence platform."""

__version__ = "1.0.0"
__author__ = "Rehan & Research Contributors (University of Arizona)"

from lit_discovery.core.dispatcher import search_literature, AVAILABLE_ENGINES
from lit_discovery.core.unpaywall import resolve_unpaywall_pdf
from lit_discovery.intelligence.scite_consensus import resolve_scite_tallies
from lit_discovery.intelligence.citation_graph import explore_citation_graph
from lit_discovery.synthesis.deep_reader import deep_read_pdf, extract_material_properties
from lit_discovery.synthesis.matrix import generate_synthesis_matrix
from lit_discovery.exports.zotero import export_zotero_references, fetch_doi_citation_metadata

__all__ = [
    "search_literature",
    "AVAILABLE_ENGINES",
    "resolve_unpaywall_pdf",
    "resolve_scite_tallies",
    "explore_citation_graph",
    "deep_read_pdf",
    "extract_material_properties",
    "generate_synthesis_matrix",
    "export_zotero_references",
    "fetch_doi_citation_metadata",
]
