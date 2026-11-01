"""Unit tests for the CLI entry point."""
import subprocess
import sys


def test_cli_version():
    cmd = [sys.executable, "-m", "lit_discovery.cli", "--version"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert "lit-discovery 1.0.0" in res.stdout or "lit-discovery 1.0.0" in res.stderr


def test_cli_help():
    cmd = [sys.executable, "-m", "lit_discovery.cli", "--help"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert "search" in res.stdout
    assert "graph" in res.stdout
    assert "read" in res.stdout
    assert "materials" in res.stdout
    assert "{search,graph,read,materials}" in res.stdout


def test_cli_rejects_removed_ui_command():
    res = subprocess.run(
        [sys.executable, "-m", "lit_discovery.cli", "ui"],
        capture_output=True, text=True,
    )
    assert res.returncode == 2
    assert "invalid choice" in res.stderr


def test_json_search_also_exports_references(monkeypatch, capsys, tmp_path):
    import json
    from lit_discovery import cli
    monkeypatch.setattr(cli, "search_literature", lambda **kwargs: {"articles": [{"title": "Synthetic fixture"}]})
    bib = tmp_path / "refs.bib"
    monkeypatch.setattr(sys, "argv", ["lit-discovery", "search", "polymer", "--json", "--bib", str(bib)])
    cli.main()
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["zotero_export"]["bibtex_count"] == 1
    assert bib.is_file()
    assert "Querying" in captured.err


def test_nonpositive_budget_rejected():
    result = subprocess.run([sys.executable, "-m", "lit_discovery.cli", "search", "polymer", "--top", "0"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "positive integer" in result.stderr
