"""IPv4 address resolution for advertised LoadBalancer hostnames."""

from __future__ import annotations

import ipaddress
import socket


class AddressResolutionError(Exception):
    """Raised when a hostname cannot be resolved to IPv4 addresses."""


def resolve_ipv4_addresses(host: str) -> list[str]:
    """Return sorted unique IPv4 addresses for ``host``.

    IPv4 literals are returned as a one-element list. Hostnames are resolved with
    ``AF_INET`` only. Raises ``AddressResolutionError`` when resolution fails or
    yields no addresses.
    """
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.version != 4:
            raise AddressResolutionError(f"address {host!r} is not an IPv4 address")
        return [str(parsed)]

    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM)
    except socket.gaierror as error:
        raise AddressResolutionError(f"failed to resolve IPv4 addresses for {host!r}") from error

    addresses = sorted({info[4][0] for info in infos if info[4]})
    if not addresses:
        raise AddressResolutionError(f"no IPv4 addresses resolved for {host!r}")
    return addresses
