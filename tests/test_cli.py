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
    assert "ui" in res.stdout
