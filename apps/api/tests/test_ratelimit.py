"""Rate-limit identity: forged forwarding headers must not buy a fresh bucket."""
import pytest
from pydantic import SecretStr
from starlette.requests import Request

from app.core.config import get_settings
from app.core.ratelimit import client_ip, ip_bucket

LOGIN = "/api/v1/auth/login"
BODY = {"email": "nobody@example.com", "password": "wrong-password"}


def make_request(headers: dict[str, str], peer: str = "10.0.0.5") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw, "client": (peer, 1234)})


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "proxy_shared_secret", SecretStr("proxy-secret"))
    monkeypatch.setattr(s, "trusted_proxy_count", 0)
    return s


def test_client_ip_ignores_forwarded_headers_by_default(settings):
    assert client_ip(make_request({"x-forwarded-for": "9.9.9.9", "x-client-ip": "8.8.8.8"})) == "10.0.0.5"


def test_client_ip_trusts_x_client_ip_only_with_secret(settings):
    assert client_ip(make_request({"x-client-ip": "8.8.8.8", "x-proxy-secret": "proxy-secret"})) == "8.8.8.8"
    assert client_ip(make_request({"x-client-ip": "8.8.8.8", "x-proxy-secret": "guess"})) == "10.0.0.5"
    assert client_ip(make_request({"x-client-ip": "not-an-ip", "x-proxy-secret": "proxy-secret"})) == "10.0.0.5"


def test_client_ip_counts_trusted_hops_from_the_right(settings, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    assert client_ip(make_request({"x-forwarded-for": "6.6.6.6, 203.0.113.7"})) == "203.0.113.7"


def test_ip_bucket_groups_ipv6_by_64():
    assert ip_bucket("2001:db8:1:2:aaaa::1") == ip_bucket("2001:db8:1:2:bbbb::2") == "2001:db8:1:2::/64"
    assert ip_bucket("2001:db8:1:3::1") != ip_bucket("2001:db8:1:2::1")
    assert ip_bucket("::ffff:203.0.113.7") == "203.0.113.7"
    assert ip_bucket("203.0.113.7") == "203.0.113.7"


async def test_spoofed_forwarded_for_does_not_bypass_auth_limit(client, settings):
    limit = 8  # RATE_LIMIT_AUTH in conftest
    codes = [(await client.post(LOGIN, json=BODY, headers={"x-forwarded-for": f"9.9.9.{i}"})).status_code
             for i in range(limit + 1)]
    assert codes[-1] == 429


async def test_signed_client_ip_gives_each_visitor_their_own_bucket(client, settings):
    limit = 8
    for i in range(limit + 1):
        r = await client.post(LOGIN, json=BODY, headers={"x-client-ip": f"198.51.100.{i}",
                                                         "x-proxy-secret": "proxy-secret"})
        assert r.status_code != 429
