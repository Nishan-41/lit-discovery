# Chem-Mat-Hub Codex skill

Portable command-line chemistry/materials research skill. See [SKILL.md](SKILL.md) for database coverage, evidence rules, CLI options and full-text access limits.

## Install

Copy this directory to your Codex skills directory as `chem-mat-hub`, then install dependencies:

```sh
python -m pip install -r requirements.txt
python scripts/codex_hub.py --doctor
```

Set database credentials through environment variables or a private `CHEM_MAT_HUB_ENV_FILE`. No credentials, local upstream manifest or local library configuration are distributed. Optional Unpaywall access requires an explicitly authorized `CHEM_MAT_HUB_UNPAYWALL_EMAIL`.

## Persistent research

```sh
python scripts/codex_hub.py --literature "ionogel ionic conductivity" --library-dir /path/to/research-library
python scripts/codex_hub.py --deep-read /path/to/paper.pdf --paper-doi 10.1234/example --library-dir /path/to/research-library
python scripts/codex_hub.py --library-graph --library-dir /path/to/research-library
```

Use `CHEM_MAT_HUB_LIBRARY_DIR` to share a library across working directories. Without configuration, storage defaults to `./research-library`. Searches save metadata and run history, attempt five main PDFs by default, and refresh an offline graph. Citation edges require source records. Extraction does not establish scientific review. Institutional access depends on publisher and current network/browser session.

Keep library data, subscription PDFs, evidence, notes and credentials outside Git. The repository ignore rules protect common generated files; review staged files before each publication.

## Verify

```sh
python -m pytest --rootdir . --confcutdir tests tests -q
```

Tests use local fixtures and mocked network calls. Bundled English OCR model is distributed under Apache 2.0; see `assets/tessdata/LICENSE` and pinned source/checksum in `assets/tessdata/source.json`. Skill source follows repository license.
