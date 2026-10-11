"""These tests have no credentials and forbid network connection attempts."""

import os
import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    # CLI fixtures must not inherit local role selections or credentials.
    for name in os.environ:
        if name.startswith("SADAF_") or name.endswith("API_KEY") or name.endswith("API_KEYS"):
            monkeypatch.delenv(name)

    def blocked(*args, **kwargs):
        raise AssertionError("Offline tests attempted network access")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
