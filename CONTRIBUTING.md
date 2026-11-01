# Contributing

Contributions should improve a reproducible command-line research workflow: source adapters, metadata quality, citation exports, PDF evidence, or materials queries.

## Set up

```bash
git clone https://github.com/rehan-hasnain/lit-discovery.git
cd lit-discovery
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install -e ".[dev]"
python -m pytest tests -q
python examples/offline_demo.py
```

For the optional research bundle, install `codex/chem-mat-hub/requirements.txt` and run its tests as described in the [README](README.md#development).

## Before opening a pull request

- Explain the concrete trigger and resulting behavior.
- Add regression coverage for behavior changes. Use controlled provider responses and temporary storage; unit tests must not require credentials or network access.
- Preserve DOI/source provenance and avoid inventing missing scientific or citation metadata.
- Put CLI progress on stderr and machine-readable results on stdout.
- Use timeouts for provider requests. Distinguish unavailable sources from valid empty responses wherever the interface permits.
- Update CLI help and examples when options change.
- Keep credentials, private research libraries, papers, and local environment paths out of commits.
- Keep user-facing prose factual. Do not present heuristic matches, extraction candidates, or citation tallies as scientific validation.

Run `git diff --check` and the relevant test suites. CI also builds the distribution. This repository accepts CLI and Python-library improvements; there is no web frontend or hosted API.
