"""Opt-in checks against an isolated, running Compose gateway, never the live app."""
from concurrent.futures import ThreadPoolExecutor
import os
import time
from urllib.parse import urlsplit

import httpx
import pytest

BASE = os.environ.get("INGRESS_TEST_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="Set INGRESS_TEST_URL for an isolated Compose gateway")


@pytest.fixture(scope="module")
def ingress():
    assert urlsplit(BASE).hostname in ("127.0.0.1", "localhost", "::1")
    with httpx.Client(base_url=BASE, trust_env=False, timeout=5) as client:
        yield client


def test_management_routes_are_not_public(ingress):
    for path in ("/status", "/dashboard", "/docs", "/openapi.json", "/%73tatus"):
        assert ingress.get(path).status_code == 404


def test_search_limit_cannot_be_bypassed_with_forwarded_headers(ingress):
    responses = [ingress.get("/search", params={"q": "no-such-player"},
                             headers={"X-Forwarded-For": f"198.51.100.{i}", "X-Real-IP": f"198.51.100.{i}"})
                 for i in range(12)]
    assert any(response.status_code == 200 for response in responses)
    assert all(response.status_code == 429 for response in responses[-5:])
    for response in responses:
        if response.status_code == 429:
            assert response.headers["Retry-After"] == "1"
            assert response.headers["Cache-Control"] == "no-store"
            assert response.json() == {"detail": "Too many requests"}


def test_general_burst_limit_and_recovery(ingress):
    with ThreadPoolExecutor(max_workers=16) as workers:
        responses = list(workers.map(lambda _: ingress.get("/health"), range(60)))
    assert any(response.status_code == 429 for response in responses)
    assert all(response.status_code in (200, 429) for response in responses)
    time.sleep(1.2)
    assert ingress.get("/health").status_code == 200
