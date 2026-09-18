"""Unit tests for synthesis, material parameter extraction, and comparative matrix."""
import pytest
from lit_discovery.synthesis.deep_reader import extract_material_properties, extract_sections_from_text
from lit_discovery.synthesis.matrix import generate_synthesis_matrix


def test_extract_material_properties_all_fields():
    sample_text = """
    The synthesized polybenzoxazole (PBO) matrix demonstrated a high tensile modulus of 150 GPa
    and an elongation of 3.2%. When swollen with [EMIM][TFSI] ionic liquid at 80 wt%,
    the resulting ionogel exhibited an outstanding ionic conductivity of 12.5 mS/cm at 25 °C
    and a thermal degradation temperature of 550 °C.
    """
    props = extract_material_properties(sample_text)

    assert "polymer_matrix" in props
    assert any("PBO" in p or "polybenzoxazole" in p for p in props["polymer_matrix"])

    assert "ionic_conductivity" in props
    assert any("12.5 mS/cm" in c for c in props["ionic_conductivity"])

    assert "mechanical_modulus" in props
    assert any("150 GPa" in m for m in props["mechanical_modulus"])

    assert "thermal_properties" in props
    assert any("550 °C" in t or "25 °C" in t for t in props["thermal_properties"])


def test_extract_material_properties_empty():
    props = extract_material_properties("")
    assert props == {}


def test_extract_sections():
    paper_text = """
    Abstract: We report on ionogels.
    Materials and Methods: All chemicals were purchased from Sigma Aldrich.
    Results and Discussion: The ionic conductivity was measured using impedance spectroscopy.
    Conclusions: In summary, this work provides a new route.
    """
    sections = extract_sections_from_text(paper_text)
    assert sections["experimental_methods"] is not None
    assert "Sigma Aldrich" in sections["experimental_methods"]
    assert sections["results_and_discussion"] is not None
    assert "impedance spectroscopy" in sections["results_and_discussion"]
    assert sections["conclusions"] is not None
    assert "In summary" in sections["conclusions"]


def test_generate_synthesis_matrix():
    articles = [
        {
            "title": "Rigid-Rod Polybenzoxazole Ionogel Electrolytes",
            "authors": ["Rehan et al.", "Collaborator B"],
            "year": 2025,
            "abstract": "PBO ionogels with [EMIM][TFSI] have conductivity of 8.4 mS/cm and modulus of 120 GPa.",
            "doi": "https://doi.org/10.1000/182",
            "open_access_pdf": "https://example.com/paper.pdf",
            "smart_citations": {"total_citations": 12, "supporting": 4, "contrasting": 1}
        }
    ]
    res = generate_synthesis_matrix(articles)

    assert "records" in res
    assert "markdown_table" in res
    assert len(res["records"]) == 1

    rec = res["records"][0]
    assert rec["title"] == "Rigid-Rod Polybenzoxazole Ionogel Electrolytes"
    assert "PBO" in rec["polymer_matrix"] or "polybenzoxazole" in rec["polymer_matrix"]
    assert "| Paper / Author |" in res["markdown_table"]
