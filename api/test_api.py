"""Smoke tests for the read-only API (§10.1). Run: pytest api/test_api.py"""

import re

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
    # 22 since syn-ake was corrected: it carries an INCI name and its own entry calls it a
    # lawful cosmetic ingredient, so the flag contradicted the record.
    assert cos["total"] == 22
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


# Firewall regression guard. The dataset deliberately publishes NO reader-directed dosing /
# administration instructions and NO commerce. Crucially, it DOES carry — legitimately — the
# `sale_note` firewall disclaimers ("...No dosing, reconstitution, or administration is
# published (intentional)..."), neutral reference science that reports trial doses ("oral
# 500 mg bid reduced ..."), the words "injectable"/"injected", corporate M&A figures
# ("$1.9B buyout"), and educational text ("how to use sunscreen"). Those are the firewall
# working, not a leak, so a bare-substring ban on stems like "reconstitut" or " mg " is wrong
# — it trips on the very disclaimer that promises the data is clean. Instead we match on
# instructional / commerce *patterns* (an imperative plus a dose amount, "reconstitute with",
# an explicit "dosage", a retail price, a cart/checkout string) that do not occur in neutral
# reference prose. Calibrated to zero matches on the current corpus; see the teeth test below
# for the positive side.
_DOSING_COMMERCE = [
    r"\bdosage\b",                                              # explicit dosage label
    r"\b(?:recommended|suggested)\s+dos(?:e|age|ing)\b",        # prescriptive dose (not "maintenance dose")
    r"\bdos(?:e|age|ing)\s*[:=]",                              # "dose: 250" / "dosing ="
    r"\b(?:take|apply|administer|inject|use)\s+\d+(?:\.\d+)?\s?(?:mg|mcg|µg|ug|iu|ml)\b",  # imperative + amount
    r"\binject\s+\d",                                           # "inject 0.25 mg" (not the debunk quote "inject this vial")
    r"\breconstitute\s+(?:with|in|using|to)\b",               # reconstitution instruction (not the noun "reconstitution")
    r"\bhow to (?:dose|inject|administer|reconstitute)\b",      # how-to instructions (not "how to use")
    r"\bbuy now\b", r"\badd to (?:cart|bag)\b", r"\bcheckout\b",
    r"\bsku\b", r"\bin stock\b", r"\border now\b",
    r"(?<!not )\bfor sale\b",                                   # commerce, but not the "not for sale" disclaimer
    r"[$€£]\s?\d+[.,]\d{2}\b",                                 # a retail price (not the M&A "$1.9B" figures)
]
_DOSING_COMMERCE_RE = [re.compile(p) for p in _DOSING_COMMERCE]


def test_firewall_no_dosing_or_commerce_in_payloads():
    import json as _json
    for path in ["/compounds", "/grades", "/citations", "/cosmetic-claims", "/identifiers"]:
        blob = _json.dumps(client.get(path).json()).lower()
        for rx in _DOSING_COMMERCE_RE:
            m = rx.search(blob)
            assert m is None, (
                f"{rx.pattern!r} matched {blob[max(0, m.start() - 40):m.end() + 20]!r} in {path}"
            )


def test_firewall_patterns_have_teeth():
    # Guard against the guard rotting into a no-op: genuine dosing/commerce text MUST match,
    # so a future change that neuters the patterns fails here.
    leaks = [
        "Reconstitute with 2 mL bacteriostatic water.",
        "Take 250 mcg subcutaneously twice weekly.",
        "Recommended dosage: 5 mg.",
        "Buy now — $49.99, add to cart (SKU 12345), in stock.",
    ]
    for leak in leaks:
        assert any(rx.search(leak.lower()) for rx in _DOSING_COMMERCE_RE), f"not caught: {leak!r}"
    # ...and the intentional firewall disclaimer must stay clean.
    disclaimer = ("not for sale. no dosing, reconstitution, or administration is "
                  "published (intentional). neutral scientific reference only.")
    assert not any(rx.search(disclaimer) for rx in _DOSING_COMMERCE_RE)
