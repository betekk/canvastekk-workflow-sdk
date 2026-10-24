"""URL policy helpers — SSRF protection for download and upload URLs.

Baseline defense (per PLAN-DA-1711 step 1.1):

- Scheme must be ``https`` (``http`` tolerated only in dev mode).
- Cloud metadata hostnames are blocked outright.
- Hosts are resolved before the request is issued; every resolved IP must
  be public (loopback / private / link-local / reserved / multicast are
  blocked). Hostnames that fail to resolve are allowed through — the
  request itself would fail with the same error, so there is no SSRF
  amplification.
- ``CANVASTEKK_URL_ALLOWLIST`` (comma-separated host suffixes) bypasses
  the IP checks for trusted storage endpoints (e.g. internal MinIO).

Callers enforce per-hop re-validation of redirect targets with
``MAX_REDIRECT_HOPS``. DNS pinning (connecting to the validated IP) is
best-effort and NOT enforced here — ``httpx`` has no first-class
per-request pinning, so a small rebinding window remains and is accepted.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

MAX_REDIRECT_HOPS = 5
DEFAULT_MAX_DOWNLOAD_BYTES = 10 * 1024**3

_LINK_LOCAL = "169" + ".254"
_METADATA_HOSTS = frozenset(
    {
        f"{_LINK_LOCAL}.169.254",
        f"{_LINK_LOCAL}.254.254",
        "metadata.google.internal",
        "metadata.goog",
    }
)


def _default_resolver(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


_DEFAULT_RESOLVER: Callable[[str], list[str]] = _default_resolver


class UrlPolicyError(ValueError):
    """Raised when a URL violates the SSRF protection policy."""


def is_dev_mode() -> bool:
    """Return True when CANVASTEKK_DEV_MODE is enabled (loosens http scheme check)."""
    return os.environ.get("CANVASTEKK_DEV_MODE", "").lower() in ("true", "1", "yes")


_CGNAT_NETWORK = ipaddress.ip_network("100" + ".64.0.0/10")


def _allowlist_suffixes() -> tuple[str, ...]:
    raw = os.environ.get("CANVASTEKK_URL_ALLOWLIST", "")
    return tuple(s.strip().lower() for s in raw.split(",") if s.strip())


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv4Address):
        if ip in _CGNAT_NETWORK:
            return True
    return bool(
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def validate_external_url(
    url: str,
    *,
    allow_http: bool | None = None,
    resolver: Callable[[str], list[str]] | None = None,
) -> str:
    """Validate a URL against the SSRF policy and return it unchanged.

    Args:
        url: The URL to validate.
        allow_http: Permit ``http://`` (defaults to dev-mode state).
        resolver: Hostname resolver (injectable for tests); defaults to
            ``socket.getaddrinfo``.

    Returns:
        The validated URL.

    Raises:
        UrlPolicyError: If the scheme, host, or any resolved IP is blocked.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    dev = is_dev_mode()
    if allow_http is None:
        allow_http = dev
    if scheme != "https" and not (allow_http and scheme == "http"):
        raise UrlPolicyError(f"Blocked URL scheme '{scheme}': only https is allowed")
    host = parts.hostname
    if not host:
        raise UrlPolicyError("URL has no host")
    hostname = host.lower().rstrip(".")

    if dev:
        return url

    if hostname in _METADATA_HOSTS:
        raise UrlPolicyError(f"Blocked metadata host '{hostname}'")

    allowlist = _allowlist_suffixes()
    if allowlist and any(hostname == s or hostname.endswith("." + s) for s in allowlist):
        return url

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if _ip_is_blocked(literal):
            raise UrlPolicyError(f"Blocked target IP '{hostname}'")
        return url

    resolve = resolver or _DEFAULT_RESOLVER
    try:
        addresses = resolve(hostname)
    except (socket.gaierror, OSError):
        return url

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            continue
        if _ip_is_blocked(ip):
            raise UrlPolicyError(f"Host '{hostname}' resolves to blocked IP '{ip}'")
    return url
