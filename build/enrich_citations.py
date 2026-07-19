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
  * Never regress. A blank answer means "the call failed", not "the fact is gone", so an
    empty result never overwrites a value an earlier run already established: the previous
    value is kept and the preservation is logged. Semantic Scholar rate-limits hard and
    answers for a different subset of rows on every run, so without this rule a weekly
    rebuild would silently drop cross-links it had already found. (Trade-off, stated
    plainly: if a record genuinely disappears upstream we keep the last known value rather
    than blanking it — the same call we make for chemical identifiers.)
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

# Cross-link fields an empty API answer must never clear (see "Never regress" above).
PRESERVE_FIELDS = ("openalex_id", "semantic_scholar_id", "citation_count", "oa_url")


def load_previous(path: Path) -> dict[tuple[str, str], dict]:
    """Previous enrichment, keyed by (slug, source_index), so a failed call can't erase it."""
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {(r["slug"], r["source_index"]): r for r in csv.DictReader(fh)}


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

    out = Path(args.out)
    prev = load_previous(out)
    preserved: list[str] = []

    out_rows = []
    for r in rows:
        # Copy: resolve() memoises per DOI and several rows can share one, so never mutate it.
        enr = dict(resolve(r["doi"].strip()))
        old = prev.get((r["slug"], r["source_index"]))
        if old:
            for f in PRESERVE_FIELDS:
                if not str(enr.get(f) or "").strip() and (old.get(f) or "").strip():
                    enr[f] = old[f]
                    preserved.append(f"{r['slug']}[{r['source_index']}].{f} kept ({old[f]!r})")
        # Attribute the row to the graphs whose data it actually carries. Derived from the
        # merged values, not from who answered this run, so the column stops flapping with
        # Semantic Scholar's rate-limit luck.
        if enr.get("enrichment_source") != "invalid-doi":
            srcs = []
            if str(enr.get("openalex_id") or "").strip():
                srcs.append("OpenAlex")
            if str(enr.get("semantic_scholar_id") or "").strip():
                srcs.append("SemanticScholar")
            enr["enrichment_source"] = "+".join(srcs) if srcs else "none"
        out_rows.append({**r, **enr})
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
    print(f"preserved from prior run : {len(preserved)}  (empty answer did not overwrite a known value)")
    if preserved:
        for m in preserved[:10]:
            print(f"  · {m}")
        if len(preserved) > 10:
            print(f"  … and {len(preserved) - 10} more")
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
