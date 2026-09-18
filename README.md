<div align="center">

# 🔬 LitDiscovery

### The Open-Source Scientific Literature Discovery & Research Intelligence Platform
**An open-source, local-first alternative to Elicit, SciSpace, Connected Papers, and Consensus.**

[![CI Test Suite](https://github.com/rehan/lit-discovery/actions/workflows/ci.yml/badge.svg)](https://github.com/rehan/lit-discovery/actions)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com)
[![PyMuPDF](https://img.shields.io/badge/PyMuPDF-In--Memory-red.svg)](https://pymupdf.readthedocs.io/)
[![Engines](https://img.shields.io/badge/Academic%20Engines-12%20Federated-success.svg)](#12-federated-academic-engines)
[![scite.ai](https://img.shields.io/badge/scite.ai-Smart%20Citations-purple.svg)](https://scite.ai)
[![Zotero](https://img.shields.io/badge/Zotero-BibTeX%20%26%20RIS-red.svg)](https://www.zotero.org)

</div>

---

## 🌟 Executive Summary

**LitDiscovery** is an enterprise-grade, extensible research intelligence engine designed for researchers, scientists, and engineers. It federates **12 academic literature databases concurrently**, resolves **direct legal open-access PDFs** via Unpaywall, validates scientific claims through **scite.ai Smart Citations** (Supporting vs. Contrasting tallies), snowballs citation networks like **Connected Papers**, and extracts experimental recipes and material parameters into a comparative synthesis matrix like **Elicit and SciSpace**—all while running **100% locally with complete data privacy and zero subscription fees**.

```
                           ┌────────────────────────────────────────┐
                           │       User Query / Research Topic      │
                           └───────────────────┬────────────────────┘
                                               │
               ┌───────────────────────────────┴──────────────────────────────┐
               ▼                               ▼                              ▼
      [Zero-Auth Engines]              [Academic Preprints]           [Authoritative Repos]
      • OpenAlex (250M works)          • arXiv (Physics/CS/Math)      • PubMed (NLM/NIH)
      • Crossref (150M records)        • Europe PMC (Bio/Life Sci)    • DOE OSTI (Energy/Mats)
      • DOAJ (Open Journals)           • Zenodo (CERN Datasets)       • Semantic Scholar (S2)*
      • DataCite (Theses/Data)                                        • Elsevier Scopus*
                                                                      • CORE (Universities)*
               │                               │                              │
               └───────────────────────────────┬──────────────────────────────┘
                                               │ (Concurrent Execution)
                                               ▼
                              ┌───────────────────────────────────┐
                              │  Deduplication & Relevance Rank   │
                              │  (Normalizer & Keyword Coverage)  │
                              └─────────────────┬─────────────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
        [Unpaywall Resolver]                                    [scite.ai Consensus Engine]
     Direct OA PDF URL Resolution                            Smart Citations Empirical Sentiment
     (Zero Captcha / Direct Stream)                          🟢 Supporting vs. 🔴 Contrasting
                     │                                                     │
                     └──────────────────────────┬──────────────────────────┘
                                                │
               ┌────────────────────────────────┴────────────────────────────────┐
               ▼                                                                 ▼
   [PyMuPDF In-Memory Reader]                                      [Synthesis & Export Layer]
• Full-text extraction without disk writes                       • Elicit-style Comparative Matrix
• Automated experimental parameter mining                        • 1-Click Zotero / Overleaf (.bib)
  (Conductivity, Polymer matrix, Modulus, Td)                    • 1-Click Mendeley / EndNote (.ris)
```

---

## ⚖️ Feature Comparison: LitDiscovery vs. Commercial Platforms

| Capability | LitDiscovery (Ours) | Elicit.com | SciSpace | Connected Papers | Consensus.app |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Pricing** | **Free & Open Source (MIT)** | $300 - $600 / yr | $144 - $240 / yr | $108 - $180 / yr | $100 - $200 / yr |
| **Federated Search Engines** | **12 Engines** | 1 (S2) | 1 (Crossref/S2) | 1 (S2) | 1 (S2) |
| **DOE OSTI & CERN Zenodo** | ✅ **Built-in** | ❌ | ❌ | ❌ | ❌ |
| **scite.ai Smart Citations** | ✅ **Native** | ❌ | ❌ | ❌ | Partial |
| **Citation Graph Snowballing** | ✅ **3 Modes** | ❌ | ❌ | ✅ Co-citation only | ❌ |
| **Comparative Synthesis Matrix** | ✅ **Markdown & JSON** | ✅ Web only | ✅ Web only | ❌ | ❌ |
| **In-Memory PDF Stream Parsing** | ✅ **PyMuPDF (`fitz`)** | Cloud only | Cloud only | ❌ | ❌ |
| **Official Publisher BibTeX/RIS** | ✅ **Direct DOI Sync** | Limited | Limited | ❌ | ❌ |
| **Local Web UI & CLI** | ✅ **Both Included** | Web only | Web only | Web only | Web only |
| **Privacy & Zero Data Logging** | ✅ **Runs Locally** | ❌ Cloud tracked | ❌ Cloud tracked | ❌ Cloud tracked | ❌ Cloud tracked |

---

## ⚡ Key Capabilities

### 1. 12 Federated Academic Literature Engines
Concurrently searches across 12 primary sources:
1. **OpenAlex**: Global multi-disciplinary bibliographic graph (250M+ records)
2. **Crossref**: Official publisher metadata registry (150M+ DOIs)
3. **arXiv**: Cornell open-access repository for Physics, Materials, Math, and CS
4. **Semantic Scholar**: Allen Institute AI academic graph *(Optional API Key)*
5. **Europe PMC**: Comprehensive life sciences, biochemistry, and biomedicine literature
6. **Elsevier Scopus**: Curated peer-reviewed indexing *(Optional API Key)*
7. **CORE**: World's largest aggregator of open access research papers *(Optional API Key)*
8. **PubMed (NLM/NIH)**: National Library of Medicine biomedical & chemistry citations
9. **DOE OSTI**: U.S. Department of Energy national laboratories reports and papers
10. **DOAJ**: Directory of Open Access Journals (peer-reviewed, gold open access)
11. **DataCite**: International research data repositories, dissertations, and preprints
12. **Zenodo (CERN)**: Open research, materials science datasets, and preprints

### 2. Empirical Consensus Verification via scite.ai
Automatically resolves citation sentiment classification:
- 🟢 **Supporting Citations**: Independent papers that replicated or validated findings.
- 🔴 **Contrasting / Contradicting Citations**: Papers questioning or refuting claims.
- ⚪ **Mentioning Citations**: Contextual citations without strong empirical stance.
- **Consensus Ratio**: Quantifies agreement level across the broader literature.

### 3. Connected Papers & Citation Snowballing
Trace the evolutionary network of scientific ideas:
- **`related`**: Bibliographically coupled and co-cited works (Connected Papers graph).
- **`forward` (`cites`)**: Recent publications that build on and cite the seed paper.
- **`backward` (`cited_by`)**: Foundational seminal references cited by the seed paper.

### 4. PyMuPDF In-Memory Full-Text Deep Reader
- Downloads and processes open-access PDFs in RAM stream (zero disk footprint).
- Extracts sections: Materials & Methods, Results & Discussion, Conclusions.
- Regex extraction for experimental parameters:
  - Ionic Conductivity ($\sigma$ in $\text{mS}\cdot\text{cm}^{-1}$)
  - High-performance Polymer Matrix (PBO / Zylon, Kevlar, Kapton, PVDF, PTFE, PEEK, Nafion)
  - Ionic Liquids / Salts ([EMIM][TFSI], [BMIM][BF4], LiTFSI, etc.)
  - Thermal Decomposition Temperature ($T_d$ in °C)
  - Mechanical Modulus ($E$ in $\text{GPa}$ or $\text{MPa}$) and Stretchability ($\%$)

### 5. 1-Click Publisher Reference Exports
- Uses DOI content negotiation (`Accept: application/x-bibtex` and `Accept: application/x-research-info-systems`) to retrieve exact publisher-formatted citations.
- Direct drop-in for **Zotero**, **Mendeley**, **EndNote**, and **Overleaf / LaTeX**.

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/rehan/lit-discovery.git
cd lit-discovery

# Install in editable mode
pip install -e .
```

*Prerequisites: Python 3.10+.*

### Optional API Keys
LitDiscovery works immediately with **9 zero-auth engines**! For higher rate limits on commercial databases, configure your `.env` file:

```bash
cp .env.example .env
```

Edit `.env`:
```env
S2_API_KEY=your_semantic_scholar_api_key
CORE_API_KEY=your_core_ac_uk_key
SCOPUS_API_KEY=your_elsevier_scopus_key
UNPAYWALL_EMAIL=your_university_email@domain.edu
```

---

## 💻 CLI Usage

The `lit-discovery` CLI gives you terminal superpowers:

```bash
# 1. Search across 12 literature engines with Elicit-style synthesis
lit-discovery search "polybenzoxazole ionogel ionic conductivity"

# 2. Search and export citations directly to Zotero BibTeX and Mendeley RIS
lit-discovery search "solid state battery aramid nanofiber" --bib references.bib --ris references.ris

# 3. Explore Connected Papers citation graph for a seed paper
lit-discovery graph "10.1038/s41563-022-01195-4" --mode related --limit 6

# 4. Stream an open-access PDF into memory and extract methodology & recipes
lit-discovery read "10.1038/nature12373" --pages 20

# 5. Launch the interactive browser Web UI
lit-discovery ui --port 8000
```

---

## 🖥️ Interactive Web UI

Launch the embedded responsive Web UI with a single command:

```bash
lit-discovery ui
```

Navigate to `http://localhost:8000`:

- 🔍 **Federated Search**: Search across 12 academic engines concurrently.
- 📊 **Comparative Synthesis Matrix**: Side-by-side table comparing host polymers, electrolytes, conductivity, and thermal stability.
- 🟢 **scite.ai Badges**: Live indicators of supporting vs. contrasting citations.
- 📥 **1-Click Export**: Download `.bib` and `.ris` files instantly for your reference manager.
- 🕸️ **Citation Graph Explorer**: Interactive snowballing for seed papers.
- 📖 **Deep Reader**: Stream full-text PDFs and inspect recipe parameters in real time.

---

## 🐍 Python API Usage

Use LitDiscovery as a Python library in your own research workflows:

### Basic Search & Synthesis Matrix
```python
from lit_discovery import search_literature

results = search_literature(
    query_text="rigid-rod polybenzoxazole electrolyte",
    limit_per_engine=3,
    top_n=5
)

print(f"Total Papers Discovered: {results['total_articles_retrieved']}")
print(results["synthesis_table_markdown"])
```

### Empirical Consensus Verification (scite.ai)
```python
from lit_discovery import resolve_scite_tallies

sentiment = resolve_scite_tallies("10.1038/nature12373")
print(f"Supporting Citations: {sentiment['supporting']}")
print(f"Contrasting Citations: {sentiment['contrasting']}")
print(f"Total Citations: {sentiment['total_citations']}")
```

### Citation Network Snowballing (Connected Papers)
```python
from lit_discovery import explore_citation_graph

graph = explore_citation_graph(
    seed_doi_or_query="10.1038/s41563-022-01195-4",
    mode="related",
    limit=5
)

for paper in graph["connected_works"]:
    print(f"• {paper['title']} ({paper['year']}) -> {paper['doi']}")
```

### Reference Management Export
```python
from lit_discovery import export_zotero_references

export_zotero_references(
    articles=results["articles"],
    bib_path="library.bib",
    ris_path="library.ris"
)
```

---

## 📦 Standalone Zero-Dependency Edition

For cluster environments or quick scripts without package installation, use the standalone edition:

```bash
python standalone/lit_discovery_single.py "high performance ionogel"
```

---

## 🧪 Testing

Run the comprehensive unit and integration test suite:

```bash
pytest tests/ -v
```

---

## 📜 Citation

If you use LitDiscovery in your research, please cite:

```bibtex
@software{lit_discovery_2026,
  author = {Rehan and Research Contributors},
  title = {LitDiscovery: Open-Source Scientific Literature Discovery and Research Intelligence Platform},
  year = {2026},
  url = {https://github.com/rehan/lit-discovery},
  version = {1.0.0}
}
```

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
