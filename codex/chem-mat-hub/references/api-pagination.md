# API pagination references

These primary sources were checked when adding pagination. Existing source normalizers are retained and request controls are tested for all twelve adapters.

- [OpenAlex paging](https://help.openalex.org/api/paging/): page and per_page; supported portable page size at most 100.
- [Crossref REST API](https://github.com/CrossRef/rest-api-doc): rows and offset; bounded queries remain below the 10,000 offset limit.
- [Semantic Scholar API](https://api.semanticscholar.org/api-docs/): paper search limit and offset.
- [Europe PMC REST API](https://europepmc.org/RestfulWebService): pageSize and cursorMark / nextCursorMark.
- [arXiv API manual](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md): start and max_results; consecutive network requests are spaced at least three seconds apart.
- [OSTI API](https://www.osti.gov/api/v1/docs): rows and page.
- [DataCite pagination](https://support.datacite.org/docs/pagination): page[size] and page[number].
- [Zenodo developers](https://developers.zenodo.org/): size and page.
- [CORE API](https://core.ac.uk/services/api): retained search endpoint with limit and offset.
- [PyMuPDF OCR](https://github.com/pymupdf/PyMuPDF/blob/main/README.md): text pages, tables and OCR. The installed PyMuPDF OCR backend was verified with bundled English language data.

Provider request syntax can change. A successful response does not prove a particular search exhausted all literature. Inspect source diagnostics and pagination stop reasons.
