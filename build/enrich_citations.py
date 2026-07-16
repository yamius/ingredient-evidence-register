#!/usr/bin/env python3
"""
Scholarly cross-links for the Vallydia Ingredient-Evidence Register — §10.3.

Takes the DOI-verified citations (data/citations.csv) and enriches each DOI against two
free scholarly graphs, turning the citation spine into linked, machine-cross-referenceable
nodes:

  * OpenAlex        — openalex_id, cited_by_count, open-access URL
  * Semantic Scholar — semantic_scholar_id (paperId), citationCount, open-access PDF

Output: data/citations_enriched.csv (+ parquet) = every column of citations.csv plus
openalex_id, semantic_scholar_id, citation_count, oa_url, enrichment_source.

Design rules (same discipline as the rest of the build):
  * Degrade gracefully. If an API is down, rate-limits us, or has no record, the field is
    left BLANK and the reason is logged — never guessed. A missing cross-link is honest.
  * Cache every response under build/.cache/scholar/ so re-runs are offline and the emitted
    files are deterministic (no timestamps, stable input order).
  * Be polite: one request at a time with a small delay; back off on HTTP 429.
  * No personal data in outbound URLs (no mailto) — we use the common API pools.

Usage:
    python build/enrich_citations.py [--offline]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "vallydia-ingredient-evidence-register/1.1 (dataset build; +https://vallydia.com)"
OPENALEX = "https://api.openalex.org/works/doi:"
SEMANTIC = "https://api.semanticscholar.org/graph/v1/paper/DOI:"
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

OUT_FIELDS = [
    "slug", "name", "source_index", "source_text", "doi", "resolved", "verified_title",
    "openalex_id", "semantic_scholar_id", "citation_count", "oa_url", "enrichment_source",
]


def cache_path(root: Path, api: str, doi: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", doi)[:120]
    return root / "build" / ".cache" / "scholar" / f"{api}_{safe}.json"


def fetch(url: str, cp: Path, offline: bool, log: list[str], label: str) -> dict | None:
    if cp.exists():
        raw = cp.read_text(encoding="utf-8")
        return json.loads(raw) if raw.strip() else None
    if offline:
        return None
    cp.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cp.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(0.2)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:                       # no record — a real, cacheable answer
                cp.write_text("", encoding="utf-8")
                return None
            if e.code == 429:                       # rate-limited — back off, then degrade
                time.sleep(2 * (attempt + 1))
                continue
            log.append(f"{label}: HTTP {e.code} — left blank")
            return None
        except Exception as e:
            if attempt == 2:
                log.append(f"{label}: {type(e).__name__} — left blank")
                return None
            time.sleep(1 + attempt)
    log.append(f"{label}: rate-limited after retries — left blank")
    return None


def from_openalex(doi: str, root: Path, offline: bool, log: list[str]) -> dict:
    url = OPENALEX + urllib.parse.quote(doi, safe="")
    data = fetch(url, cache_path(root, "openalex", doi), offline, log, f"OpenAlex {doi}")
    if not data:
        return {}
    oa = data.get("open_access") or {}
    best = data.get("best_oa_location") or {}
    return {
        "openalex_id": (data.get("id") or "").rsplit("/", 1)[-1],
        "citation_count": data.get("cited_by_count"),
        "oa_url": oa.get("oa_url") or best.get("landing_page_url") or "",
    }


def from_semantic(doi: str, root: Path, offline: bool, log: list[str]) -> dict:
    fields = "externalIds,citationCount,openAccessPdf"
    url = SEMANTIC + urllib.parse.quote(doi, safe="") + "?fields=" + fields
    data = fetch(url, cache_path(root, "s2", doi), offline, log, f"SemanticScholar {doi}")
    if not data:
        return {}
    pdf = data.get("openAccessPdf") or {}
    return {
        "semantic_scholar_id": data.get("paperId") or "",
        "citation_count": data.get("citationCount"),
        "oa_url": pdf.get("url") or "",
    }


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--citations", default=str(root / "data" / "citations.csv"))
    ap.add_argument("--out", default=str(root / "data" / "citations_enriched.csv"))
    ap.add_argument("--offline", action="store_true", help="use only the local cache")
    args = ap.parse_args()

    src = Path(args.citations)
    if not src.exists():
        print(f"ERROR: {src} not found — run generate_dataset.py first", file=sys.stderr)
        return 2

    with src.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    log: list[str] = []
    resolved_by_doi: dict[str, dict] = {}      # dedupe API work across shared DOIs

    def resolve(doi: str) -> dict:
        if doi in resolved_by_doi:
            return resolved_by_doi[doi]
        if not DOI_RE.match(doi):
            log.append(f"{doi!r}: not a well-formed DOI — skipped")
            out = {"enrichment_source": "invalid-doi"}
            resolved_by_doi[doi] = out
            return out
        oa = from_openalex(doi, root, args.offline, log)
        s2 = from_semantic(doi, root, args.offline, log)
        srcs = []
        if oa:
            srcs.append("OpenAlex")
        if s2:
            srcs.append("SemanticScholar")
        # citation_count: prefer OpenAlex; fall back to S2. oa_url: prefer whichever is present.
        count = oa.get("citation_count")
        if count is None:
            count = s2.get("citation_count")
        out = {
            "openalex_id": oa.get("openalex_id", ""),
            "semantic_scholar_id": s2.get("semantic_scholar_id", ""),
            "citation_count": "" if count is None else count,
            "oa_url": oa.get("oa_url") or s2.get("oa_url") or "",
            "enrichment_source": "+".join(srcs) if srcs else "none",
        }
        resolved_by_doi[doi] = out
        return out

    out_rows = []
    for r in rows:
        enr = resolve(r["doi"].strip())
        out_rows.append({**r, **enr})

    out = Path(args.out)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_FIELDS, lineterminator="\n")
        w.writeheader()
        for row in out_rows:
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in OUT_FIELDS})

    try:
        import pandas as pd
        pd.read_csv(out, dtype=str).fillna("").to_parquet(
            root / "data" / "parquet" / "citations_enriched.parquet", index=False)
    except Exception as e:
        log.append(f"parquet mirror skipped: {e}")

    n = len(out_rows)
    both = sum(1 for r in out_rows if r["enrichment_source"] == "OpenAlex+SemanticScholar")
    oa_only = sum(1 for r in out_rows if r["enrichment_source"] == "OpenAlex")
    s2_only = sum(1 for r in out_rows if r["enrichment_source"] == "SemanticScholar")
    none = sum(1 for r in out_rows if r["enrichment_source"] in ("none", "invalid-doi"))
    with_oa = sum(1 for r in out_rows if r["oa_url"])
    uniq = len(resolved_by_doi)

    print("=" * 68)
    print("CITATION ENRICHMENT REPORT — §10.3")
    print("=" * 68)
    print(f"citation rows           : {n}  ({uniq} unique DOIs queried)")
    print(f"both graphs             : {both}")
    print(f"OpenAlex only           : {oa_only}")
    print(f"Semantic Scholar only   : {s2_only}")
    print(f"neither (blank, logged) : {none}")
    print(f"with open-access URL     : {with_oa}")
    if log:
        print(f"\ndegraded/blank ({len(log)} — honest gaps, not guesses):")
        for m in log[:25]:
            print(f"  · {m}")
        if len(log) > 25:
            print(f"  … and {len(log) - 25} more")
    print("=" * 68)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
