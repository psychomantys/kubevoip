import socket

import pytest

from kubevoip.dnsutil import AddressResolutionError, resolve_ipv4_addresses


def test_resolve_ipv4_literal_passthrough():
    assert resolve_ipv4_addresses("198.51.100.10") == ["198.51.100.10"]


def test_resolve_ipv4_rejects_ipv6_literal():
    with pytest.raises(AddressResolutionError, match="not an IPv4"):
        resolve_ipv4_addresses("2001:db8::1")


def test_resolve_hostname_returns_sorted_unique_ips(monkeypatch):
    def fake_getaddrinfo(host, port, family, type):
        assert host == "sip.example.com"
        assert family == socket.AF_INET
        return [
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("203.0.113.20", 0)),
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("198.51.100.10", 0)),
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("203.0.113.20", 0)),
        ]

    monkeypatch.setattr("kubevoip.dnsutil.socket.getaddrinfo", fake_getaddrinfo)
    assert resolve_ipv4_addresses("sip.example.com") == ["198.51.100.10", "203.0.113.20"]


def test_resolve_hostname_failure(monkeypatch):
    def fake_getaddrinfo(*_args, **_kwargs):
        raise socket.gaierror("name or service not known")

    monkeypatch.setattr("kubevoip.dnsutil.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(AddressResolutionError, match="failed to resolve"):
        resolve_ipv4_addresses("missing.example.com")


def test_resolve_hostname_empty(monkeypatch):
    monkeypatch.setattr("kubevoip.dnsutil.socket.getaddrinfo", lambda *_args, **_kwargs: [])
    with pytest.raises(AddressResolutionError, match="no IPv4 addresses"):
        resolve_ipv4_addresses("empty.example.com")
