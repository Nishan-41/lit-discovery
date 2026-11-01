# Architecture

LitDiscovery has two command-line entry points with different scopes. The installed `lit-discovery` package provides focused literature, citation, PDF, and materials commands. The optional Chem-Mat-Hub bundle adds research persistence and chemistry-specific controls. Both run locally and call external data providers.

## Module map

```text
lit_discovery/
  cli.py                  Argument parsing and terminal/JSON output
  core/
    engines.py            Twelve literature adapters
    dispatcher.py         Concurrent retrieval, deduplication, enrichment
    relevance.py          Keyword scoring and abstract normalization
    unpaywall.py          Opt-in open-access resolution
  intelligence/           OpenAlex citation traversal and scite tallies
  synthesis/              PDF reading and metadata synthesis
  exports/                DOI negotiation, BibTeX, and RIS
  materials/              OPTIMADE, OQMD, C2DB, and MOFdb adapters
codex/chem-mat-hub/
  scripts/codex_hub.py     Extended CLI and source diagnostics
  scripts/research.py      Pagination, retries, caching, and evidence extraction
  scripts/thermophysics.py ILThermo identity checks and quality flags
  scripts/fulltext.py      Validated PDF retrieval and access outcomes
  scripts/project_library.py SQLite catalog, run history, assets, graph export
```

## Search execution

1. Resolve selected provider names and dispatch independent searches through `ThreadPoolExecutor`.
2. Normalize DOI/title identity and deduplicate records while retaining provider provenance.
3. Rank records with transparent keyword matching, then select the requested result budget.
4. Optionally enrich selected records with open-access locations and citation counts.
5. Generate a metadata synthesis table and optional BibTeX/RIS files. Emit structured JSON separately from progress messages.

Provider calls are primarily I/O-bound, so threads provide a small, dependency-light concurrency model. Timeouts bound individual adapter calls. The base package uses one bounded request per adapter rather than an exhaustive crawl.

## Identity and exports

DOIs are normalized before deduplication; title matching is used when a DOI is absent. Different DOIs are retained even when titles coincide. Multiple provider records merge source labels and prefer richer metadata. This remains a heuristic: title-only records can be ambiguous.

Citation exports first attempt DOI content negotiation. HTML landing pages are rejected as citation payloads. Fallback exports retain available metadata and omit missing years, authors, and journals. Non-DOI identifiers remain URLs.

## Extended research persistence

The optional CLI stores paper identity, discovery runs, typed graph edges, and local assets in a SQLite catalog with companion JSON/PDF files. DOI identity is preferred; imports are content-aware and repeatable. Discovery, citation, and related-paper relationships remain distinct. PDF extraction and scientific review are separate states.

Its HTTP transport records credential-safe diagnostics, bounded pagination stop reasons, cache hits, and failures. Credential context is hashed into cache keys. Full-text responses bypass the shared HTTP cache. This machinery is not yet shared with the base package.

## Validation strategy

- Provider tests use controlled response fixtures rather than assumptions about live APIs.
- CLI tests cover help/version, rejected commands, valid JSON, exports, and invalid budgets.
- PDF tests generate local documents, including scanned pages for the optional OCR path.
- Research tests cover identity rejection, retrieval bounds, unit-conflict flags, access classifications, and persistence.
- CI tests supported Python versions and builds package artifacts.

## Tradeoffs and known gaps

The two implementations share a domain but retain separate transport and extraction logic. This makes the skill portable, at the cost of maintenance duplication. Consolidating these layers is planned, not complete.

The base adapters often return an empty list for network failures or malformed responses. Therefore zero returned records do not prove zero scientific matches. Use the extended CLI's diagnostics for coverage-sensitive work.

Ranking is lexical, not embedding-based. Property extraction is heuristic, not a validated measurement dataset. scite classifications are context signals, not an automated scientific verdict. No benchmarked latency, recall, or scientific accuracy is claimed.
