---
name: chem-mat-hub
description: Search chemistry, materials, ionic-liquid and literature databases with the local Chem-Mat-Hub Python engine and existing API credentials. Use for compound properties, crystal/DFT records, polymer specifications, thermophysical calculations, ionogel literature, citation graphs and reference exports.
---

# Chem-Mat-Hub for Codex

Use the bundled engine directly through local Python. No hosted service or OpenAI API key is needed. Existing database APIs and curated data remain available. Resolve script paths relative to this skill directory; use absolute paths in commands when working elsewhere.

## Run

Requires Python 3.10 or newer. Install dependencies from `requirements.txt`; use your configured Python interpreter.

```powershell
python "<skill-directory>\scripts\codex_hub.py" --doctor
python "<skill-directory>\scripts\codex_hub.py" --literature "PBO ionogel ionic conductivity" --synonyms "PBO|Zylon|polybenzoxazole" --year-from 2020 --max-results 60 --per-source 40 --output "<output-directory>\literature.json"
python "<skill-directory>\scripts\codex_hub.py" --database pubchem --query ethanol
python "<skill-directory>\scripts\codex_hub.py" --database materials-project --query SiO2
python "<skill-directory>\scripts\codex_hub.py" --polymer-spec zylon
python "<skill-directory>\scripts\codex_hub.py" --coolprop Water --temp 298.15 --pressure 101325
python "<skill-directory>\scripts\codex_hub.py" --walden --conductivity 9.1 --viscosity 32 --density 1.52 --mw 391.31
python "<skill-directory>\scripts\codex_hub.py" --compound "zylon ionogel" --output "<output-directory>\report.json" --export-bibtex "<output-directory>\papers.bib"
python "<skill-directory>\scripts\codex_hub.py" --seed-doi "10.1038/s41586-021-03819-2" --graph-mode forward
python "<skill-directory>\scripts\codex_hub.py" --deep-read "<paper.pdf>" --ocr --output "<output-directory>\paper-evidence.json"
python "<skill-directory>\scripts\codex_hub.py" --sync-check
```

Use focused `--database` calls for specific properties; `--literature` avoids irrelevant compound/crystal lookups for research questions. `--compound` is the broad report. Source names and configured-key presence are available from `--doctor`; this never prints keys. Run `--probe --output ...` when a full connectivity audit is requested or setup changes, not before every search.

Search controls: `--max-results` (default 50 returned), `--per-source` (30 per source per query variant), `--page-size` (20; maximum 100), `--max-pages` (10), `--sources openalex,crossref,...`, `--year-from`, `--year-to`, repeatable `--phrase`, repeatable `--exclude`, repeatable `--synonyms "PBO|Zylon|polybenzoxazole"`. Synonyms expand into bounded separate searches (maximum 16 variants); duplicate records merge database provenance and retain richer abstracts. Phrase, exclusion and year filters operate on retrieved metadata, not unexamined full text. Unknown years are excluded when dates are filtered. A per-source budget applies before metadata filtering, so refine the query or raise budgets if filtering leaves too few hits.

Use `--require-all` for focused multi-term searches: every query keyword group must appear in title/abstract, with configured synonyms accepted. Missing abstracts can exclude relevant full-text-only matches, so use a broader pass when needed. `--min-relevance 0..100` controls a lexical threshold (default 1 excludes zero-match records); never describe its number as scientific or semantic confidence. Inspect titles and abstracts before presenting results as relevant.

Pagination records expose page count and stop reasons. `--enrich` controls how many ranked papers receive Unpaywall/scite enrichment (default 8; 0 disables it). All selected articles can be exported with `--export-bibtex` and `--export-ris`, including when using `--literature`. Exports prefer publisher metadata; fallback records do not fabricate publication years or convert non-DOI URLs into DOIs.

Transient HTTP failures retry twice with backoff; authentication errors do not retry. Successful GET responses cache for 24 hours, partitioned by hashed credential context. Raw keys are not written into cache metadata. Cache defaults to `work/chem-mat-hub-cache` under the current workspace; set `CHEM_MAT_HUB_CACHE_DIR` for a shared location. Controls: `--no-cache`, `--cache-ttl <seconds>`, `--retries 0..5`. Cache hits remain visible in source diagnostics.

PDF reading accepts a DOI, direct URL or local path and reads every page by default. `--max-pdf-pages` explicitly limits it and marks truncation. Native tables retain page numbers and bounding boxes. `--ocr` reads pages with little native text using bundled English Tesseract data; `TESSDATA_PREFIX` overrides its location. OCR and table output need visual checking, especially symbols, exponents and merged cells.

Codex enhancements live in `scripts/research.py`, independently of the upstream engine. `--sync-check` detects upstream drift and local engine edits when a local `references/upstream.json` manifest is configured. Machine-specific manifests are excluded from this distribution; without one, the command reports `manifest_missing`. `--sync-upstream` explicitly refreshes the original Gemini engine, preserves the overlay, checks callable interfaces and local Walden/Zylon invariants, and saves a backup. It refuses conflicting local edits or incompatible upstream changes. `CHEM_MAT_HUB_UPSTREAM` can point to another source engine. This does not synchronize unrelated project/package files.

Read [database and engineering reference](references/original-skill.md) for detailed source coverage, polymer names and original engine flags. The implemented citation graph uses OpenAlex; it is not a Connected Papers account integration. Polymer and Kamlet-Taft tables are bundled curated data, not live measurements.

## Credentials and runtime

The engine loads process environment first, then optional `CHEM_MAT_HUB_ENV_FILE`, then existing `~/.env`. Do not copy or print secret values. Key variables: `MP_API_KEY`, `RSC_API_KEY`, `SCOPUS_API_KEY` / `ELSEVIER_API_KEY`, `CTX_API_KEY` / `EPA_API_KEY`, `S2_API_KEY` / `SEMANTIC_SCHOLAR_API_KEY`, `CORE_API_KEY`. A configured key is not proof of valid authentication or entitlement. Missing Materials Project key uses its OPTIMADE fallback.

Dependencies: requests, beautifulsoup4, python-dotenv, pymupdf, CoolProp. This distribution provides command-line tools only. Preserve the original Gemini skill and research repository unless edits there are explicitly requested.

## Interpret results

### Identity-checked thermophysical data

`--database ilthermo --query "EMIM TFSI"` retrieves complete numeric tables for up to 50 exact-identity single-component datasets by default. Use `--ilthermo-max-sets 0` for all returned matching sets, or a positive limit for a bounded selection. Limits produce `partial` and `truncated`, never an apparently complete five-record preview. Records preserve raw values, uncertainty fields, temperature, pressure, phase, method, sample notes, reference and reference-state footnotes. ILThermo runs persist in the project library.

Name matching must resolve uniquely. EMIM TFSI/NTf2/Tf2N and EMIM DCA aliases and CAS numbers are recognized. Other compounds require exact normalized names or an explicit `--ilthermo-compound-id`; `--ilthermo-formula` supplies an additional formula check. Every downloaded dataset is checked again for component ID, name and formula. Mixtures and substring-only hits are excluded. Identity resolution failure is not evidence of scientific absence.

Quality flags never silently repair source data. Checks identify malformed/nonfinite/nonpositive physical quantities, differences above 10% across sources at matching recorded conditions, and an approximately 1000-fold mismatch between enthalpy slope and same-reference molar heat capacity. These are screening flags, not scientific validation or statistical significance. Conflicts require sample/method/uncertainty review. Unmatched temperatures, pressures or units are not directly compared.

Evidence types distinguish `database_value`, `metadata_candidate`, `pdf_extraction_candidate`, `verified_paper_table`, `calculation` and `unresolved_conflict`. Downloading or extracting never promotes a record to scientific verification. Explicit verified-table records require source, page, locator and verification note; calculations require method and source inputs. Unresolved conflicts remain attached to raw source records.

Scopus natural-language queries quote chemical punctuation and join terms with AND. HTTP 400 gets one punctuation-normalized fallback; effective query and fallback remain visible in pagination/diagnostics. This can broaden chemistry matching, so inspect returned relevance. Authentication and entitlement failures do not trigger query rewriting; arbitrary server messages are not logged because they can echo credentials.

- Check source diagnostics: HTTP errors, timeouts, missing keys and empty/unparsed responses must not be reported as searches with zero scientific matches. Return useful sources and identify unavailable ones. Use HTTP status and host only in diagnostics; never expose credentials or credential-bearing URLs.
- Literature returns a configurable number of deduplicated articles from bounded paginated retrieval, not an exhaustive review. Relevance is a transparent title/abstract keyword-group score, not semantic confidence. Report database provenance, DOI/title, evidence type, temperature, composition and units. Cite actual records and papers. Do not treat placeholder abstracts, scite tallies or extraction candidates as verified full-text evidence. Verify critical extracted values in the paper before comparing them.
- Evidence candidates retain property label, exact value/unit text, page (for PDFs), source, contextual quote and sample-context snippet. Tensile strength is separate from modulus. Temperatures lacking a nearby explicit Tg/Tm/degradation label remain unclassified; do not convert measurement or processing temperatures into stability claims. Labels remain candidates: extraction does not reliably resolve every composition, specimen or characterization method.
- Walden inputs are mS/cm, mPa.s, g/cm3, g/mol and K. For a neat liquid, Lambda (S cm2/mol) = conductivity_mS_cm * molar_mass / (1000 * density). Viscosity in poise = viscosity_mPa_s / 100. The reported index assumes an intercept-zero ideal line; it is not measured dissociation fraction. For mixtures and ionogels, require electrolyte concentration and appropriate reference calibration instead of applying neat-liquid density/MW blindly.
- Curated polymer values depend on grade, direction, processing and test conditions. Distinguish them from sample-specific measurements and check primary manufacturer/paper evidence for engineering decisions.
- Save outputs in the user's requested destination or the current workspace deliverable directory. Use `--help` for additional flags; never assume an advertised endpoint succeeded without checking its actual response.

## Full-text access

Each full-text retrieval includes `access_summary` plus per-route reasons: HTTP 401 authentication, HTTP 403 refusal, human-verification page, purchase-access page, rate limit, connection failure, timeout, TLS error, missing PDF link, invalid/encrypted/oversized PDF, or request-budget exhaustion. HTTP status and requested/final hosts are preserved; raw error messages, credential-bearing query strings, cookies and response headers are not copied into diagnostics. A metadata API failure is separate from a publisher refusal. Neither a sign-in/purchase page nor HTTP 403 establishes whether the user's subscription is valid.

Failed OA and subsequent DOI routes remain in `collection_routes` even when a later download succeeds. Only validated readable PDFs count as retrieval success. A successful download may still report earlier route failures; `institutional_entitlement` stays `not_verified`. The summary suggests the next step without implementing login, CAPTCHA completion or paywall workarounds.

### Per-run diagnostic summary

Structured CLI results, literature searches, PDF reads and citation/broad queries expose `diagnostic_summary`. Each registered source is reported as successful, partial, failed, truncated, unavailable or untested, with original detail statuses, returned-record counts when known, cache state, request counts, stop reasons and recovered-query errors. Untested sources are never assumed healthy; configured credentials alone do not count as network verification. Cache hits are distinguished from live tests. Missing keys, opt-in skips, ambiguous identities and unparsed responses are distinct from verified zero matches.

Retrieval caps and result selection limits are explicit. Provider page/budget limits mean bounded coverage, not proof that science matches are exhausted. Full-text access outcomes and library-save status appear alongside source diagnostics. `--doctor` is a local configuration check; `--probe` attempts provider checks and uses one ILThermo dataset so health checks do not download an entire property archive. A summary covers the current operation only and makes no universal database-health or institutional-access claim.

`--deep-read` now tries open-access resolution, DOI publisher redirects, main-paper PDF links from HTML metadata/anchors, and PDF links deposited with Crossref. Direct publisher landing pages and direct PDF URLs also work. Downloads use the local computer's network and a dedicated HTTP session, so campus IP access can work without a new API key. Only validated, readable PDF bytes count as successful full-text retrieval. Retrieval diagnostics record route, host and status; they do not prove institutional entitlement. HTML landing pages, login screens, abstracts and supporting PDFs do not count as the main paper. Redirects and session cookies stay in memory; full-text responses bypass the shared HTTP cache.

When result is `browser_required` or `fulltext_unavailable`, follow `browser_handoff` using available browser tools in the user's existing browser session. Open publisher page, use institution's proxy/OpenAthens link generator when needed, and download the main paper through the site's normal controls. User completes NetID/MFA when prompted. Do not extract browser cookies or ask for passwords. Browser access is an agent workflow, not a Python login implementation. After download, call `--deep-read` with the actual local PDF path and verify extracted pages. If browser download tools are unavailable, report that specific limitation and request the downloaded PDF. Do not claim reading full text until extraction succeeds. No publisher subscription access has been proven merely by adding this resolver.

Full-text collection: add `--fetch-fulltext 5 --pdf-dir <library-directory>` to `--literature` to fetch a bounded selection serially (maximum 20). Each readable paper gets a PDF, evidence JSON and checksum; `manifest.json` records successes, failures and browser handoffs. Rerunning reuses existing local PDFs. An existing different PDF is never overwritten. Inspect selected paper relevance before a large collection. For one paper use `--deep-read <DOI-or-URL> --save-pdf <paper.pdf>`. These local save options are available through the CLI.

Unpaywall contact transmission is opt-in via `CHEM_MAT_HUB_UNPAYWALL_EMAIL`; no hardcoded personal address is sent by the overlay. Set that value only after user authorizes sending that contact to Unpaywall. Publisher/Crossref retrieval remains available without it. `network_error` means transport failure, not absence of a paper or lack of institutional subscription.

## Persistent project library

Every CLI `--literature`, literature `--database`, `--seed-doi` citation run, and `--deep-read` now saves records automatically in the project library. Default project location is `research-library` under the current working directory; override with `CHEM_MAT_HUB_LIBRARY_DIR` or `--library-dir`. Use `--no-library` only when user explicitly wants a transient run or for isolated tests. Do not write test fixtures into the real research library.

Literature searches preserve every returned paper record and raw search result, and attempt full-text collection for first five selected results by default. `--fetch-fulltext 0` preserves metadata without downloads; increase up to 20 for a reviewed selection. All accessible saved PDFs/evidence remain local. Failed retrieval is recorded, not replaced with invented text. Browser-downloaded main PDFs and supporting information can be registered via `--deep-read <path> --paper-doi <DOI> --asset-role main|supporting` or import existing evidence with `--import-result <JSON> --paper-doi <DOI> --asset-role supporting`.

Project library contains SQLite catalog, JSON paper records, full run history, PDFs, evidence, and `graph/network.html` plus `network.json`. Graph updates after each persisted run. Run `--library-graph` to rebuild without network calls. Import earlier real research searches with `--import-result`; identical file/content imports are idempotent. Imported discovery time is import time, not an invented original search date. Main/supporting PDFs share paper identity but keep separate asset roles. Readable PDF extraction changes status to `text_extracted`, never `scientifically_reviewed`.

Graph edge types: `discovered_in` links saved searches to found papers; `cites` is directed and only created from actual citation-source results; `related_by_openalex` stays distinct from citation. Do not infer citations from shared keywords or co-discovery. Progress slider shows cumulative discovery, while extraction status reflects latest saved record. Counts reflect bounded retrieved papers, not exhaustive knowledge of field. PDFs stored here may be subscription-licensed; user requested local project storage, not public publication.

When producing a substantive paper analysis, save its reusable notes under the project library `notes/` with the paper DOI, source-page citations, limitations and analysis date. Label these as agent analysis, separate from extracted evidence. Do not infer a completed review merely because notes or a PDF exist. Save future analysis artifacts into this project library when user has requested persistent research storage.
