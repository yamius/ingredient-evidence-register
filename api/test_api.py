"""Smoke tests for the read-only API (§10.1). Run: pytest api/test_api.py"""

from fastapi.testclient import TestClient

from api.app import app, ATTRIBUTION

client = TestClient(app)


def _has_attribution(body):
    assert body["attribution"] == ATTRIBUTION
    assert body["source_url"] == "https://vallydia.com"


def test_root_lists_endpoints():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    _has_attribution(body)
    assert body["data"]["compounds"] == 85


def test_every_endpoint_carries_attribution():
    for path in ["/", "/compounds", "/grades", "/citations", "/cosmetic-claims",
                 "/identifiers", "/search?q=copper"]:
        _has_attribution(client.get(path).json())


def test_list_and_filter_compounds():
    assert client.get("/compounds").json()["total"] == 85
    cos = client.get("/compounds", params={"is_cosmetic": True}).json()
    assert cos["total"] == 21
    pep = client.get("/compounds", params={"class": "peptide"}).json()
    assert pep["total"] == 53


def test_get_compound_and_404():
    r = client.get("/compounds/ghk-cu")
    assert r.status_code == 200
    assert r.json()["data"]["name"].startswith("GHK-Cu")
    assert client.get("/compounds/does-not-exist").status_code == 404


def test_grades_filter():
    a = client.get("/grades", params={"grade": "A"}).json()
    assert a["count"] > 0
    assert all(row["grade"] == "A" for row in a["data"])
    ghk = client.get("/grades", params={"slug": "ghk-cu"}).json()
    assert all(row["slug"] == "ghk-cu" for row in ghk["data"])


def test_search_finds_copper_peptides():
    hits = client.get("/search", params={"q": "copper"}).json()
    slugs = {h["slug"] for h in hits["data"]}
    assert "ghk-cu" in slugs


def test_cosmetic_claims_have_both_types():
    claims = client.get("/cosmetic-claims", params={"slug": "ghk-cu"}).json()["data"]
    kinds = {c["claim_type"] for c in claims}
    assert kinds == {"allowed", "forbidden"}


def test_firewall_no_dosing_or_commerce_in_payloads():
    import json as _json
    banned = ["dosage", "reconstitut", " mg ", "buy now", "add to cart", "sku"]
    for path in ["/compounds", "/grades", "/citations", "/cosmetic-claims", "/identifiers"]:
        blob = _json.dumps(client.get(path).json()).lower()
        for term in banned:
            assert term not in blob, f"{term!r} leaked into {path}"
