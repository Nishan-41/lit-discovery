# Examples

Install the package from the repository root with `python -m pip install -e .`.

| Example | Purpose | Network |
| --- | --- | --- |
| `python examples/offline_demo.py` | Synthetic search, deduplication, provenance, and reference export | None |
| `python examples/01_basic_search.py` | Live literature search and metadata matrix | Required |
| `python examples/02_consensus_verification.py` | Provider citation tallies; not scientific verification | Required |
| `python examples/03_citation_network_snowballing.py` | OpenAlex related-work traversal | Required |
| `python examples/04_export_to_zotero.py` | Live search followed by BibTeX/RIS export | Required |

Live examples depend on provider availability and applicable credentials. Offline fixtures are illustrative and must not be cited as real publications. The advanced PDF/OCR and persistent-library workflow is documented in the [research bundle](../codex/chem-mat-hub/README.md).
