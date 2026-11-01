"""Keep package unit tests independent of provider availability and credentials."""
import pytest
import requests


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Unit tests must mock provider requests")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    yield
    assert not attempts, "Unexpected live request; add a controlled provider fixture"
