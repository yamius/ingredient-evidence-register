#!/usr/bin/env python3
"""
Integrity validation suite for the Vallydia Ingredient-Evidence Register — Phase-3 Addition B.

Machine-checkable invariants an evidence dataset must never violate. Run in CI on every push
(.github/workflows/validate.yml) so a bad row can't land silently. Exits non-zero on any
failure; `--selftest` proves the suite has teeth by corrupting the data in memory and
asserting each check fires.

Checks:
  1. Referential integrity across the six configs — every child-table slug exists in
     compounds; identifiers are 1:1 with compounds.
  2. Slugs unique; every compound reachable.
  3. Grades in {A,B,C,D,F} or null (the register's actual scale — there is no E). Overall
     grade never better than the best per-outcome grade (graded down, never up).
  4. Every citation DOI well-formed; where enriched, a resolved cross-link is a soft signal
     (never fails the build on API downtime).
  5. Identifiers: any present identifier carries source + confidence; no SMILES on a row
     whose confidence is not 'high' (guards against a fabricated structure slipping in).
  6. Firewall lint: no commerce fields (price/SKU/buy/Offer) and no dosing/administration
     INSTRUCTIONS introduced anywhere in the emitted data. Honest negatives in the source
     ("no dosing is published") are not violations — only actual instructions/commerce are.

Usage:
    python build/validate_dataset.py [--data data] [--selftest]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

VALID_GRADES = {"A", "B", "C", "D", "F", ""}
GRADE_RANK = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

# Commerce / internal-planning tokens that must never appear in a public reference artifact.
# The dollar-amount rule is deliberately narrow: a retail price (cents, or a per-unit/shipping
# amount, or a price/buy context) is commerce; an editorial M&A or market figure like
# "$1.9B buyout" or "$5.3 billion deal" in a development-history narrative is not, and must
# NOT trip the firewall. So we do not match a bare "$1" — only price-shaped amounts.
COMMERCE_RE = re.compile(
    r"\bbuy now\b|\badd to cart\b|\bcheckout\b|\badd_to_cart\b|\bprice\b\s*[:=]|"
    r"\$\d[\d,]*\.\d{2}\b"                                  # retail price with cents
    r"|\$\d[\d,]*\s*(?:/|per)\s*(?:unit|item|bottle|vial|serving|month)\b"  # per-unit price
    r"|\b(?:buy|order|purchase|shop)\b[^.]{0,20}?\$\d"     # dollar amount in a buy context
    r"|\bSKU\b|\bwave\s*\d+\b|\"@type\"\s*:\s*\"Offer\"|\bin stock\b",
    re.I,
)
# Dosing / administration INSTRUCTIONS: a quantity with a dose unit next to an administration
# verb, or explicit reconstitution/injection directions. This deliberately does NOT match the
# bare words "dosing"/"reconstitution" (the register legitimately says these are unknown or
# "not published"); it matches only actual how-to-administer content.
DOSING_RE = re.compile(
    r"\b(inject|administer|reconstitut\w*|dilut\w*)\b[^.]{0,40}?\b\d+\s?(mg|mcg|µg|ug|iu|ml|units?)\b"
    r"|\b\d+\s?(mg|mcg|µg|ug|iu|units?)\b[^.]{0,30}?\b(per|/)\s?(day|week|dose|kg)\b"
    r"|\breconstitute with\b|\bdraw up\b|\brotate injection sites?\b|\bsubcutaneous(ly)?\b[^.]{0,20}?\bdaily\b",
    re.I,
)


class Fail(Exception):
    pass


def _table(data: Path, name: str) -> list[dict]:
    with (data / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load(data: Path) -> dict:
    compounds = [json.loads(l) for l in (data / "compounds.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    d = {
        "compounds": compounds,
        "grades": _table(data, "grades.csv"),
        "legal_status": _table(data, "legal_status.csv"),
        "citations": _table(data, "citations.csv"),
        "cosmetic_claims": _table(data, "cosmetic_claims.csv"),
        "identifiers": _table(data, "identifiers.csv"),
    }
    enr = data / "citations_enriched.csv"
    if enr.exists():
        d["citations_enriched"] = _table(data, "citations_enriched.csv")
    return d


def validate(d: dict) -> list[str]:
    errors: list[str] = []

    def bad(msg: str) -> None:
        errors.append(msg)

    compounds = d["compounds"]
    slugs = [c["slug"] for c in compounds]
    slug_set = set(slugs)

    # 1-2. uniqueness + referential integrity
    if len(slugs) != len(slug_set):
        dupes = sorted({s for s in slugs if slugs.count(s) > 1})
        bad(f"duplicate slugs in compounds: {dupes}")
    for tbl in ("grades", "legal_status", "citations", "cosmetic_claims", "identifiers"):
        stray = sorted({r["slug"] for r in d[tbl]} - slug_set)
        if stray:
            bad(f"{tbl}: {len(stray)} slug(s) not in compounds: {stray[:5]}")
    id_slugs = {r["slug"] for r in d["identifiers"]}
    if id_slugs != slug_set:
        bad(f"identifiers not 1:1 with compounds (missing {sorted(slug_set - id_slugs)[:5]}, "
            f"extra {sorted(id_slugs - slug_set)[:5]})")

    # 3. grade scale + overall-vs-outcome consistency
    for r in d["grades"]:
        if r["grade"] not in VALID_GRADES:
            bad(f"grades: invalid grade {r['grade']!r} for {r['slug']} / {r['outcome'][:40]!r}")
    for c in compounds:
        overall = c.get("overall_grade")
        outcome_ranks = [GRADE_RANK[g["grade"]] for g in c.get("grades_by_outcome", []) if g.get("grade")]
        if overall and outcome_ranks and GRADE_RANK[overall] > max(outcome_ranks):
            bad(f"{c['slug']}: overall grade {overall} is better than its best outcome grade "
                f"(graded up, not down)")

    # 4. DOI well-formedness
    for r in d["citations"]:
        if not DOI_RE.match(r["doi"].strip()):
            bad(f"citations: malformed DOI {r['doi']!r} for {r['slug']}")

    # 5. identifiers — sourced, and no SMILES without high confidence
    for r in d["identifiers"]:
        has_any = any(r.get(k) for k in ("cas", "pubchem_cid", "inchikey", "smiles", "unii"))
        if has_any and not (r.get("identifier_source") and r.get("identifier_confidence")):
            bad(f"identifiers: {r['slug']} has identifiers but no source/confidence")
        if r.get("smiles") and r.get("identifier_confidence") != "high":
            bad(f"identifiers: {r['slug']} carries a SMILES at confidence "
                f"{r.get('identifier_confidence')!r} (only 'high' may) — fabrication guard")

    # 6. firewall lint over every emitted text field
    def scan(label: str, text: str) -> None:
        if not text:
            return
        if m := COMMERCE_RE.search(text):
            bad(f"firewall: commerce/planning token {m.group(0)!r} in {label}")
        if m := DOSING_RE.search(text):
            bad(f"firewall: dosing/administration instruction {m.group(0)!r} in {label}")

    for c in compounds:
        for field in ("in_brief", "sale_note", "status_note", "honest_note", "body_markdown"):
            scan(f"{c['slug']}.{field}", str(c.get(field) or ""))
        for g in c.get("grades_by_outcome", []):
            for k in ("base", "effect", "caveat"):
                scan(f"{c['slug']}.grades.{k}", str(g.get(k) or ""))
    for r in d["cosmetic_claims"]:
        scan(f"{r['slug']}.claim", r["claim_text"])

    # soft signal (never fails the build): enrichment coverage
    if "citations_enriched" in d:
        got = sum(1 for r in d["citations_enriched"] if r.get("openalex_id") or r.get("semantic_scholar_id"))
        print(f"  · soft: {got}/{len(d['citations_enriched'])} citations carry a scholarly cross-link", file=sys.stderr)

    return errors


def selftest(d: dict) -> int:
    """Corrupt a copy six ways and confirm each is caught — proves the suite has teeth."""
    import copy
    cases = {
        "dup slug": lambda x: x["compounds"].append(dict(x["compounds"][0])),
        "stray slug": lambda x: x["grades"].append({**x["grades"][0], "slug": "ghost"}),
        "bad grade": lambda x: x["grades"].__setitem__(0, {**x["grades"][0], "grade": "E"}),
        "graded up": lambda x: x["compounds"][0].update(
            overall_grade="A", grades_by_outcome=[{"outcome": "o", "grade": "F", "base": "", "effect": "", "caveat": ""}]),
        "bad doi": lambda x: x["citations"].__setitem__(0, {**x["citations"][0], "doi": "not-a-doi"}),
        "smiles low conf": lambda x: x["identifiers"].__setitem__(
            0, {**x["identifiers"][0], "smiles": "CCO", "identifier_confidence": "none"}),
        "commerce leak": lambda x: x["compounds"][0].update(sale_note="Buy now for $9.99, SKU-123"),
        "dosing leak": lambda x: x["compounds"][0].update(in_brief="Inject 250 mcg subcutaneously daily."),
    }
    all_ok = True
    for label, mutate in cases.items():
        corrupt = copy.deepcopy(d)
        mutate(corrupt)
        errs = validate(corrupt)
        caught = len(errs) > 0
        print(f"  selftest [{label:15s}] -> {'CAUGHT' if caught else 'MISSED !!'}")
        all_ok &= caught
    return 0 if all_ok else 1


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(root / "data"))
    ap.add_argument("--selftest", action="store_true", help="prove the suite catches seeded bad rows")
    args = ap.parse_args()

    d = load(Path(args.data))

    if args.selftest:
        print("SELF-TEST — every seeded corruption must be caught:")
        rc = selftest(d)
        print("SELF-TEST:", "PASS" if rc == 0 else "FAIL")
        # also confirm the real data is currently clean
        rc |= 1 if validate(d) else 0
        return rc

    errors = validate(d)
    print("=" * 68)
    print("DATASET VALIDATION")
    print("=" * 68)
    if errors:
        for e in errors:
            print(f"  FAIL  {e}")
        print(f"\n{len(errors)} problem(s) found.")
        return 1
    print(f"  OK  referential integrity across 6 configs ({len(d['compounds'])} compounds)")
    print(f"  OK  grade scale + overall/outcome consistency")
    print(f"  OK  {len(d['citations'])} citation DOIs well-formed")
    print(f"  OK  identifiers sourced; no SMILES below high confidence")
    print(f"  OK  firewall lint: no commerce/dosing content in emitted data")
    print("\nALL CHECKS PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
