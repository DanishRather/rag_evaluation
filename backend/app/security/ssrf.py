import ipaddress
import os
import socket
from urllib.parse import urlparse

from app.domain.errors import DomainError


def _allow_loopback() -> bool:
    return os.environ.get("EVAL_ALLOW_LOOPBACK") == "1"


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if _allow_loopback() and ip.is_loopback:
        return False
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or str(ip) == "169.254.169.254"
    )


def assert_public_http(url: str, resolver=None) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise DomainError("adapter_rejected", "Only http and https URLs are allowed", {"url": url})
    host = parsed.hostname
    if not host:
        raise DomainError("adapter_rejected", "URL has no host", {"url": url})
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        lookup = resolver or socket.getaddrinfo
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = lookup(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise DomainError("adapter_rejected", "URL host did not resolve", {"url": url}) from exc
        addresses = []
        for info in infos:
            try:
                addresses.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
    if not addresses:
        raise DomainError("adapter_rejected", "URL host did not resolve", {"url": url})
    for ip in addresses:
        if _blocked(ip):
            raise DomainError("adapter_rejected", "URL resolves to a blocked address", {"url": url})
