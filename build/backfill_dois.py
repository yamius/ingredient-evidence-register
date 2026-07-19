#!/usr/bin/env python3
"""
DOI backfill — propose DOIs for the register's citations that don't have one yet.

This is a SEARCH tool, not a writer. It proposes; a human accepts. Nothing here touches
the dataset or the register: the output is a review file. Confident hits are transcribed
into the private MDX register by hand (or a later pass), and the dataset regenerates from
there.

Why Crossref: OpenAlex and Semantic Scholar are excellent at *enriching a known DOI*
(that is what enrich_citations.py does). Going the other way — free-text reference to DOI —
is Crossref's speciality, because its `query.bibliographic` endpoint is built for exactly
this and it indexes the publisher metadata of record.

Matching discipline (the whole point — a wrong DOI is worse than no DOI):
  * Title alone is never enough. Preprints, namesakes, corrections, and near-identical
    titles from different years all collide. A hit must agree on TITLE + AUTHOR + YEAR.
  * Every proposal carries a confidence level and the source that produced it, exactly as
    the chemical identifiers do.
  * Anything below `high` is not written anywhere — it goes to the review list, blank.
  * Citations that cannot have a DOI (EU regulations, FDA dockets) and citations too vague
    to identify (no author, no title) are classified out rather than force-matched.

Usage:
    python build/backfill_dois.py --group-a          # the 50 prioritised citations
    python build/backfill_dois.py --slugs ghk-cu,retinol
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "vallydia-ingredient-evidence-register/1.1 (dataset build; +https://vallydia.com)"
CROSSREF = "https://api.crossref.org/works"

TOP6 = ["niacinamide", "retinol", "vitamin-c", "ceramides", "ghk-cu", "hyaluronic-acid"]

# Citations that cannot carry a DOI: statute, regulator dockets, agency notices.
REGULATORY_RE = re.compile(
    r"\b(commission regulation|official journal|regulation \(ec\)|directive \d|"
    r"fda\b|docket|advisory committee|federal register|annex [ivx]+|"
    r"sccs\b|european commission|cosing|wada\b|code of federal regulations)\b",
    re.I,
)
# Descriptions rather than references: no author, no locatable title.
VAGUE_RE = re.compile(
    r"^(qualitative review|multicenter study|meta-analysis|pooled analysis|review of \d+|"
    r"summary of|manufacturer|in-house|internal|various|multiple studies|industry)",
    re.I,
)
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")


def norm(s: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def first_author_surname(text: str) -> str:
    """Leading surname of a reference like 'Kimball AB, et al. Title...'."""
    m = re.match(r"\s*([A-Z][a-zA-Z\-']+)\s*(?:[A-Z]{1,3}\b|,)", text.strip())
    return m.group(1) if m else ""


def cited_year(text: str) -> int | None:
    years = [int(y) for y in YEAR_RE.findall(text)]
    return years[0] if years else None


def classify(text: str) -> str:
    if REGULATORY_RE.search(text):
        return "regulatory"          # no DOI exists for this kind of document
    if VAGUE_RE.match(text.strip()):
        return "insufficient"        # not a locatable reference
    if not first_author_surname(text) and not cited_year(text):
        return "insufficient"
    return "searchable"


def crossref(query: str, rows: int = 8) -> list[dict]:
    url = f"{CROSSREF}?" + urllib.parse.urlencode(
        {"query.bibliographic": query, "rows": rows, "select": "DOI,title,author,issued,container-title,type"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            time.sleep(0.3)                       # be polite to the public pool
            return data.get("message", {}).get("items", []) or []
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            return []
        except Exception:
            if attempt == 2:
                return []
            time.sleep(1 + attempt)
    return []


TAG_RE = re.compile(r"<[^>]+>")


def title_agreement(c_norm: str, title: str) -> float:
    """How well a Crossref title agrees with the free-text citation.

    Two real-world wrinkles this has to survive, both observed in this register:
      * the citation routinely drops the subtitle ("...glucosamine." vs the full
        "...glucosamine: results of a randomized, double-blind, vehicle-controlled trial"),
        so the main title before the colon is scored as well as the whole thing;
      * Crossref titles carry markup ("<i>N</i>-acetyl"), which would otherwise inject
        junk tokens and score the CORRECT paper below a reprint of it.
    """
    plain = TAG_RE.sub("", title or "")
    variants = [plain] + ([plain.split(":", 1)[0]] if ":" in plain else [])
    c_toks = set(c_norm.split())
    best = 0.0
    for v in variants:
        t_norm = norm(v)
        if not t_norm:
            continue
        if t_norm in c_norm:
            return 1.0
        t_toks = t_norm.split()
        # Token containment only for titles long enough to be distinctive; a two-word
        # title matching by bag-of-words means nothing.
        if len(t_toks) >= 4:
            best = max(best, sum(1 for w in t_toks if w in c_toks) / len(t_toks))
        best = max(best, SequenceMatcher(None, t_norm, c_norm).ratio())
    return best


def score(citation: str, item: dict) -> dict:
    """Agreement of a Crossref candidate with the free-text citation, field by field."""
    c_norm = norm(citation)
    title = (item.get("title") or [""])[0]
    title_score = title_agreement(c_norm, title)

    surnames = [norm(a.get("family", "")) for a in (item.get("author") or []) if a.get("family")]
    cited_surname = norm(first_author_surname(citation))
    # Agreement on any listed author, and (the stronger test) on the first author.
    author_ok = bool(cited_surname) and any(cited_surname == s for s in surnames)
    first_author_ok = bool(cited_surname) and bool(surnames) and surnames[0] == cited_surname

    parts = (item.get("issued") or {}).get("date-parts") or [[]]
    cand_year = parts[0][0] if parts and parts[0] else None
    cy = cited_year(citation)
    year_ok = bool(cy and cand_year and abs(int(cand_year) - cy) <= 1)
    year_exact = bool(cy and cand_year and int(cand_year) == cy)

    return {
        "doi": (item.get("DOI") or "").lower(),
        "cand_title": TAG_RE.sub("", title),
        "cand_year": cand_year,
        "cand_journal": (item.get("container-title") or [""])[0],
        "cand_type": item.get("type", ""),
        "title_score": round(title_score, 3),
        "author_ok": author_ok or first_author_ok,
        "first_author_ok": first_author_ok,
        "year_ok": year_ok,
        "year_exact": year_exact,
    }


def confidence(s: dict) -> str:
    """high = title AND author AND year agree. Anything less is not written anywhere."""
    strong_title = s["title_score"] >= 0.90
    good_title = s["title_score"] >= 0.75
    if strong_title and s["author_ok"] and s["year_ok"]:
        return "high"
    if strong_title and (s["author_ok"] or s["year_ok"]):
        return "medium"
    if good_title and s["author_ok"] and s["year_ok"]:
        return "medium"
    return "low"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compounds", default=str(ROOT / "data" / "compounds.jsonl"))
    ap.add_argument("--group-a", action="store_true", help="cosmetic + editorially linked (the 50)")
    ap.add_argument("--slugs", default="", help="comma-separated slugs instead")
    ap.add_argument("--out", default=str(ROOT / "build" / ".cache" / "doi_backfill_proposals.json"))
    args = ap.parse_args()

    recs = [json.loads(l) for l in Path(args.compounds).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.slugs:
        wanted = {s.strip() for s in args.slugs.split(",") if s.strip()}
        recs = [r for r in recs if r["slug"] in wanted]
    elif args.group_a:
        recs = [r for r in recs if r.get("is_cosmetic")]

    # top-6 by editorial weight first, then the rest
    recs.sort(key=lambda r: (TOP6.index(r["slug"]) if r["slug"] in TOP6 else 99, r["slug"]))

    proposals = []
    for r in recs:
        have = {c["source"] for c in (r.get("citation_ids") or [])}
        for i, text in enumerate(r.get("sources") or []):
            if i in have:
                continue
            kind = classify(text)
            row = {
                "slug": r["slug"], "name": r["name"], "overall_grade": r.get("overall_grade"),
                "source_index": i, "source_text": text, "kind": kind,
                "doi": "", "confidence": "", "source_api": "", "candidates": [],
            }
            if kind == "searchable":
                cands = [score(text, it) for it in crossref(text)]
                # Rank by AGREEMENT, not by title alone. Ranking on title score put a Year
                # Book reprint (same title, different DOI, different authors) above the
                # paper of record — exactly the failure the title+author+year rule exists
                # to prevent.
                rank = {"high": 3, "medium": 2, "low": 1}
                for c in cands:
                    c["confidence"] = confidence(c)
                cands.sort(key=lambda c: (rank[c["confidence"]], c["title_score"],
                                          c["first_author_ok"], c["year_exact"]), reverse=True)
                row["candidates"] = cands[:3]
                if cands:
                    best = cands[0]
                    row["confidence"] = best["confidence"]
                    row["source_api"] = "Crossref"
                    # Only a high-confidence hit gets a DOI written into the proposal.
                    row["doi"] = best["doi"] if best["confidence"] == "high" else ""
                    # A second candidate that ALSO clears `high` on a different DOI is a
                    # real ambiguity — the rules did not resolve it, so a human must.
                    if any(c["confidence"] == "high" and c["doi"] != best["doi"] for c in cands[1:]):
                        row["ambiguous"] = True
                        row["doi"] = ""
                print(f"  [{row['confidence'] or kind:>6}] {r['slug']}[{i}] {text[:64]}")
            else:
                print(f"  [{kind:>6}] {r['slug']}[{i}] {text[:64]}")
            proposals.append(row)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"\nwrote {out} — {len(proposals)} citations examined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
