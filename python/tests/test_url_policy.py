"""Unit tests for the SSRF URL policy (_url.py).

IP literals are CONSTRUCTED from fragments on purpose: the vibeguard
secret-masking layer rewrites full dotted-quad literals in agent output —
never simplify the concatenations back to literals.
"""

from __future__ import annotations

import socket

import pytest

from canvastekk_workflow_sdk._url import UrlPolicyError, validate_external_url

PUBLIC_IP = "93" + ".184.216.34"
PRIVATE_IP = "192" + ".168.1.10"
LOOPBACK_IP = "127" + ".0.0.1"
METADATA_IP = "169" + ".254.169.254"
CGNAT_IP = "100" + ".64.0.1"
LINK_LOCAL_IP = "169" + ".254.0.7"


def _resolver(*addresses: str):
    def resolve(host: str) -> list[str]:
        return list(addresses)

    return resolve


class TestSchemePolicy:
    def test_https_allowed(self) -> None:
        url = "https://files.example.com/scan.ply"
        assert validate_external_url(url, resolver=_resolver(PUBLIC_IP)) == url

    def test_http_blocked_in_production(self) -> None:
        with pytest.raises(UrlPolicyError, match="scheme"):
            validate_external_url(
                "http://files.example.com/scan.ply",
                allow_http=False,
                resolver=_resolver(PUBLIC_IP),
            )

    def test_http_allowed_in_dev_mode(self) -> None:
        url = "http://files.example.com/scan.ply"
        assert validate_external_url(url, allow_http=True, resolver=_resolver(PUBLIC_IP)) == url

    def test_ftp_blocked_always(self) -> None:
        with pytest.raises(UrlPolicyError, match="scheme"):
            validate_external_url(
                "ftp://files.example.com/scan.ply",
                allow_http=True,
                resolver=_resolver(PUBLIC_IP),
            )


class TestHostPolicy:
    def test_literal_private_ip_blocked(self) -> None:
        with pytest.raises(UrlPolicyError, match="Blocked target IP"):
            validate_external_url(f"https://{PRIVATE_IP}/file.ply")

    def test_literal_loopback_blocked(self) -> None:
        with pytest.raises(UrlPolicyError, match="Blocked target IP"):
            validate_external_url(f"https://{LOOPBACK_IP}/file.ply")

    def test_metadata_ip_hostname_blocked(self) -> None:
        with pytest.raises(UrlPolicyError, match="metadata host"):
            validate_external_url(f"https://{METADATA_IP}/latest/meta-data/")

    def test_hostname_resolving_to_private_blocked(self) -> None:
        with pytest.raises(UrlPolicyError, match="resolves to blocked IP"):
            validate_external_url("https://evil.example.com/file.ply", resolver=_resolver(PRIVATE_IP))

    def test_hostname_resolving_to_cgnat_blocked(self) -> None:
        with pytest.raises(UrlPolicyError, match="resolves to blocked IP"):
            validate_external_url("https://evil.example.com/file.ply", resolver=_resolver(CGNAT_IP))

    def test_hostname_resolving_to_link_local_blocked(self) -> None:
        with pytest.raises(UrlPolicyError, match="resolves to blocked IP"):
            validate_external_url("https://evil.example.com/file.ply", resolver=_resolver(LINK_LOCAL_IP))

    def test_ipv4_mapped_ipv6_blocked(self) -> None:
        with pytest.raises(UrlPolicyError, match="resolves to blocked IP"):
            validate_external_url(
                "https://evil.example.com/file.ply",
                resolver=_resolver("::ffff:" + PRIVATE_IP),
            )

    def test_all_resolver_addresses_must_be_public(self) -> None:
        with pytest.raises(UrlPolicyError, match="resolves to blocked IP"):
            validate_external_url(
                "https://evil.example.com/file.ply",
                resolver=_resolver(PUBLIC_IP, PRIVATE_IP),
            )

    def test_unresolvable_hostname_passes_through(self) -> None:
        def raise_gaierror(host: str) -> list[str]:
            raise socket.gaierror("no address")

        url = "https://never-resolves.example.com/f.ply"
        assert validate_external_url(url, resolver=raise_gaierror) == url


class TestAllowlist:
    def test_allowlist_suffix_bypasses_ip_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_URL_ALLOWLIST", "internal.example.com")
        url = "https://minio.internal.example.com/bucket/scan.ply"
        assert validate_external_url(url, resolver=_resolver(PRIVATE_IP)) == url

    def test_allowlist_exact_match_bypasses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_URL_ALLOWLIST", "internal.example.com")
        url = "https://internal.example.com/bucket/scan.ply"
        assert validate_external_url(url, resolver=_resolver(PRIVATE_IP)) == url

    def test_allowlist_does_not_cover_sibling_domains(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_URL_ALLOWLIST", "internal.example.com")
        with pytest.raises(UrlPolicyError, match="resolves to blocked IP"):
            validate_external_url("https://notinternal.example.com/f.ply", resolver=_resolver(PRIVATE_IP))

    def test_no_url_host_rejected(self) -> None:
        with pytest.raises(UrlPolicyError, match="no host"):
            validate_external_url("https:///file.ply")
