# Research persistence

For project literature searches, PDF retrieval/reading, citation exploration and paper analysis, preserve research records in the shared project library. Use `CHEM_MAT_HUB_LIBRARY_DIR` or an explicit `--library-dir` when configured; otherwise use `research-library` under the project root. Respect an existing parent-project library instruction.

- Save queries, controls, source diagnostics, metadata and run history. Deduplicate by DOI while retaining provenance; distinct DOIs remain distinct.
- Preserve retrieved PDFs and page evidence. Keep main papers and supporting information under one identity with separate asset roles. Reuse saved assets.
- Save substantive analysis notes with DOI/stable identifier, date, source-page citations and limitations. Separate analysis from extracted evidence.
- Refresh the offline graph after persisted runs. Keep discovery, source-verified directed citations and related-paper edges distinct; shared keywords do not prove citations.
- Track extraction separately from scientific review. Record unavailable full text and partial reads honestly. Import older results idempotently without inventing timestamps.
- Use temporary directories for tests. Disable persistence for research only when the user requests transient work.
- Keep credentials, private library records, PDFs and notes out of Git. Local subscription access does not authorize redistribution.

Prefer `codex/chem-mat-hub/scripts/codex_hub.py` for automatic persistence. Register browser-downloaded PDFs in the configured shared library. Do not infer access from configured credentials or campus Wi-Fi alone.
