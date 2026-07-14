#!/usr/bin/env python3
"""
Vallydia Ingredient-Evidence Register — dataset generator.

Reads the register's MDX source (YAML frontmatter + Markdown body) and emits the
full multi-representation dataset described in the build spec: lossless JSONL/JSON,
a flat CSV, tidy long tables, Parquet mirrors, a RAG text corpus, and checksums.

Deterministic and idempotent: everything is sorted by slug, JSON keys are emitted in
a fixed order, and no timestamps are written into the artifacts. Running it twice on
the same source yields byte-identical output.

Usage:
    python build/generate_dataset.py --source register-source/compounds --out data
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import frontmatter
import pandas as pd

SITE = "https://vallydia.com"

# Frontmatter fields we know about. Anything outside this set is reported (never
# silently dropped) so schema drift in the register surfaces at build time.
KNOWN_FIELDS = {
    "slug", "name", "title", "synonyms", "compound_class", "overall_grade",
    "grades_by_outcome", "legal_status", "wada", "function_tags", "related",
    "reviewer_status", "sources", "last_updated", "in_brief", "is_cosmetic",
    "sale_note", "cosmetic_claims", "citation_ids", "status_note", "honest_note",
    "identifiers",
}
REQUIRED_FIELDS = ["slug", "name", "title", "compound_class"]
VALID_GRADES = {"A", "B", "C", "D", "F", None}

# Field order for the canonical JSON records (stable diffs across versions).
RECORD_ORDER = [
    "slug", "name", "title", "url", "synonyms", "compound_class", "overall_grade",
    "grades_by_outcome", "legal_status", "wada", "function_tags", "related",
    "reviewer_status", "sources", "citation_ids", "cosmetic_claims", "is_cosmetic",
    "sale_note", "status_note", "honest_note", "last_updated", "in_brief", "body_sections",
    "body_markdown", "structure_image", "grade_card_image",
]

GRADE_RANK = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
H2_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)
# Internal site links: [text](/learn/x) -> text. The raw markdown copy keeps them.
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((/[^)]*)\)")


class BuildError(Exception):
    pass


# ---------------------------------------------------------------------------
# Export-time firewall (§6): internal product-planning language must never reach
# the public dataset.
#
# The register's `sale_note` legitimately carries Vallydia's internal commercial
# framing ("Wave 1 flagship", "candidate for a Wave 2 SKU (2027)"). That is fine in
# the private register and useless-to-harmful in a CC-BY dataset that gets mirrored
# to Hugging Face, Kaggle and Zenodo and ingested by LLMs — mirrors make it
# effectively permanent. The spec is explicit: no commerce/SKU mechanics in the
# dataset, and if such content exists in source, drop it from the export.
#
# So we redact at export time, sentence by sentence, and never mutate the source.
# The build then re-scans everything it is about to emit and FAILS if any planning
# language survived — so a future register edit cannot quietly leak the roadmap.
# ---------------------------------------------------------------------------
# Two tiers, because the give-away words differ in how specific they are.
#   Unambiguous: a Vallydia release wave, an SKU, a price point — these are planning,
#   full stop, wherever they appear.
#   Context-dependent: "flagship" and "launch" are ordinary words that show up in the
#   history of OTHER companies' products (naringenin's entry describes a third party
#   launching it as the flagship active of their own brand — legitimate, factual, and
#   nothing to do with Vallydia's roadmap). Those only count as planning when they sit
#   next to Vallydia or a Wave in the same sentence.
PLANNING_RE = re.compile(
    r"\bwave\s*\d+\b"          # any release wave, not just 1 and 2 — 'Wave 3 (2028+)' is roadmap too
    r"|\bSKU\b"
    r"|\bprice point\b"
    r"|\bCOGS\b"
    r"|\bcandidate for Vallydia\b"
    r"|\bVallydia is not (currently )?formulating\b"
    r"|(?:Vallydia|Wave)[^.]{0,80}?\b(?:flagship|launch(?:ing|es)?)\b"
    r"|\b(?:flagship|launch(?:ing|es)?)\b[^.]{0,80}?(?:Vallydia|Wave)",
    re.I,
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")

# Fields whose free text is exported and therefore must be swept.
REDACTABLE_FIELDS = ("sale_note", "status_note", "honest_note", "in_brief")


def redact_planning(text: str | None, slug: str, field: str, log: list[str]) -> str | None:
    """Drop sentences carrying internal product-planning language. Keep the rest."""
    if not text or not PLANNING_RE.search(text):
        return text
    kept, dropped = [], []
    for sentence in SENTENCE_SPLIT_RE.split(text.strip()):
        (dropped if PLANNING_RE.search(sentence) else kept).append(sentence.strip())
    for d in dropped:
        log.append(f"{slug}.{field}: redacted internal planning language -> {d!r}")
    result = " ".join(s for s in kept if s).strip()
    return result or None          # field was nothing but planning -> omit it entirely


def strip_internal_links(text: str) -> str:
    """Replace [label](/internal/path) with label; leave external links intact."""
    return MD_LINK_RE.sub(r"\1", text)


def clean_text(text: str) -> str:
    """Markdown -> plain-ish text for the retrieval corpus."""
    text = strip_internal_links(text)
    text = re.sub(r"\*\*|\*|`", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_body(body: str) -> dict[str, str]:
    """Split the Markdown body into a {H2 heading: text} map, in document order."""
    sections: dict[str, str] = {}
    matches = list(H2_RE.finditer(body))
    if not matches:
        lead = body.strip()
        return {"_intro": strip_internal_links(lead)} if lead else {}
    lead = body[: matches[0].start()].strip()
    if lead:
        sections["_intro"] = strip_internal_links(lead)
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[m.group(1).strip()] = strip_internal_links(body[m.end():end].strip())
    return sections


def norm_grade(value, ctx: str) -> str | None:
    """Grades are A-F or genuinely null (safety/penetration rows). Never coerce."""
    if value is None or value == "" or value == "null":
        return None
    g = str(value).strip().upper()
    if g not in VALID_GRADES:
        raise BuildError(f"{ctx}: invalid grade {value!r} (allowed: A-F or null)")
    return g


def as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def parse_file(path: Path, warnings: list[str]) -> dict:
    post = frontmatter.load(path, encoding="utf-8")
    fm = dict(post.metadata)
    slug = fm.get("slug") or path.stem

    for field in REQUIRED_FIELDS:
        if not fm.get(field):
            raise BuildError(f"{path.name}: missing required field {field!r}")
    if slug != path.stem:
        warnings.append(f"{path.name}: slug {slug!r} does not match filename")

    unknown = set(fm) - KNOWN_FIELDS
    if unknown:
        warnings.append(f"{slug}: unknown frontmatter fields carried through: {sorted(unknown)}")

    grades = []
    for i, row in enumerate(as_list(fm.get("grades_by_outcome"))):
        grades.append({
            "outcome": row.get("outcome"),
            "grade": norm_grade(row.get("grade"), f"{slug} grades_by_outcome[{i}]"),
            "base": row.get("base"),
            "effect": row.get("effect"),
            "caveat": row.get("caveat"),
        })

    sources = [str(s) for s in as_list(fm.get("sources"))]
    citations = []
    for i, c in enumerate(as_list(fm.get("citation_ids"))):
        idx = c.get("source")
        if idx is None or not isinstance(idx, int) or not (0 <= idx < len(sources)):
            raise BuildError(
                f"{slug} citation_ids[{i}]: source index {idx!r} does not join to sources[] "
                f"(len={len(sources)})"
            )
        citations.append({
            "source": idx,
            "doi": c.get("doi"),
            "resolved": c.get("resolved"),
            "verified_title": c.get("verified_title"),
        })

    claims = fm.get("cosmetic_claims") or None
    if claims is not None:
        claims = {
            "allowed": [str(x) for x in as_list(claims.get("allowed"))],
            "forbidden": [str(x) for x in as_list(claims.get("forbidden"))],
        }
    if claims and not fm.get("is_cosmetic"):
        warnings.append(f"{slug}: cosmetic_claims present but is_cosmetic is not true")

    wada = fm.get("wada") or {}
    record = {
        "slug": slug,
        "name": fm.get("name"),
        "title": fm.get("title"),
        "url": f"{SITE}/compound/{slug}",
        "synonyms": [str(s) for s in as_list(fm.get("synonyms"))],
        "compound_class": fm.get("compound_class"),
        "overall_grade": norm_grade(fm.get("overall_grade"), f"{slug} overall_grade"),
        "grades_by_outcome": grades,
        "legal_status": [
            {"region": r.get("region"), "status": r.get("status"), "note": r.get("note")}
            for r in as_list(fm.get("legal_status"))
        ],
        "wada": {"prohibited": bool(wada.get("prohibited")), "note": wada.get("note")},
        "function_tags": [str(t) for t in as_list(fm.get("function_tags"))],
        "related": [str(r) for r in as_list(fm.get("related"))],
        "reviewer_status": fm.get("reviewer_status"),
        "sources": sources,
        "citation_ids": citations,
        "cosmetic_claims": claims,
        "is_cosmetic": bool(fm.get("is_cosmetic")),
        "sale_note": fm.get("sale_note"),
        "status_note": fm.get("status_note"),
        "honest_note": fm.get("honest_note"),
        "last_updated": str(fm.get("last_updated")) if fm.get("last_updated") else None,
        "in_brief": fm.get("in_brief"),
        "body_sections": split_body(post.content),
        "body_markdown": post.content.strip(),
        "structure_image": None,   # filled from images/MANIFEST.csv when present
        "grade_card_image": None,
    }
    # Carry any unknown field through rather than dropping it.
    for key in sorted(unknown):
        record[key] = fm[key]
    return record


def attach_images(records: list[dict], manifest_path: Path) -> None:
    if not manifest_path.exists():
        return
    by_slug: dict[str, dict[str, str]] = {}
    with manifest_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            by_slug.setdefault(row["slug"], {})[row["image_type"]] = row["path"]
    for rec in records:
        imgs = by_slug.get(rec["slug"], {})
        rec["structure_image"] = imgs.get("structure") or imgs.get("sequence_card")
        rec["grade_card_image"] = imgs.get("grade_card")


def corpus_text(rec: dict) -> str:
    """Natural-language rendering for RAG retrieval.

    Scope firewall: identity, evidence grades, legal status and caveats only. No
    dosing, no administration, no commerce language is introduced here — every
    sentence is assembled from fields that already exist in the register.
    """
    parts = [f"{rec['name']} — {rec['compound_class']}."]
    if rec["synonyms"]:
        parts.append("Also known as: " + ", ".join(rec["synonyms"]) + ".")
    if rec["in_brief"]:
        parts.append(clean_text(rec["in_brief"]))

    if rec["overall_grade"]:
        parts.append(
            f"Overall evidence grade: {rec['overall_grade']} (A = strong and consistent "
            f"human evidence, F = unproven or tested and failed; the grade reflects the "
            f"leading application)."
        )
    else:
        parts.append("Overall evidence grade: not assigned.")

    if rec["grades_by_outcome"]:
        parts.append("Evidence by outcome:")
        for g in rec["grades_by_outcome"]:
            grade = g["grade"] or "not graded"
            line = f"- {g['outcome']}: grade {grade}."
            if g["base"]:
                line += f" Evidence base: {clean_text(str(g['base']))}."
            if g["effect"]:
                line += f" Reported effect: {clean_text(str(g['effect']))}."
            if g["caveat"]:
                line += f" Caveat: {clean_text(str(g['caveat']))}."
            parts.append(line)

    for ls in rec["legal_status"]:
        line = f"Legal status ({ls['region']}): {ls['status']}."
        if ls["note"]:
            line += " " + clean_text(str(ls["note"]))
        parts.append(line)

    if rec["wada"]["prohibited"]:
        note = f" {clean_text(str(rec['wada']['note']))}" if rec["wada"].get("note") else ""
        parts.append("WADA: prohibited in sport." + note)

    if rec["cosmetic_claims"]:
        allowed = rec["cosmetic_claims"]["allowed"]
        forbidden = rec["cosmetic_claims"]["forbidden"]
        if allowed:
            parts.append("Permissible cosmetic claims (appearance wording): " + "; ".join(allowed) + ".")
        if forbidden:
            parts.append("Claims that must NOT be made for this cosmetic ingredient: " + "; ".join(forbidden) + ".")

    if rec["sale_note"]:
        parts.append(clean_text(str(rec["sale_note"])))
    if rec["status_note"]:
        parts.append("Status note: " + clean_text(str(rec["status_note"])))
    if rec.get("honest_note"):
        parts.append("Honest note: " + clean_text(str(rec["honest_note"])))

    identity = rec["body_sections"].get("Identity")
    if identity:
        parts.append("Identity: " + clean_text(identity))
    mech = rec["body_sections"].get("Mechanism (as proposed)")
    if mech:
        parts.append("Mechanism (as proposed): " + clean_text(mech))

    n_doi = len([c for c in rec["citation_ids"] if c.get("doi")])
    parts.append(
        f"Evidence provenance: {len(rec['sources'])} cited sources, {n_doi} with a verified DOI."
    )
    parts.append(
        f"Reviewer status: {rec['reviewer_status']}. Grades are Vallydia's own evidence "
        f"assessment, not third-party certification."
    )
    parts.append(
        f"Source: Vallydia Ingredient-Evidence Register, {rec['url']} (CC-BY-4.0). "
        f"Reference information about appearance and evidence only; not medical advice."
    )
    return "\n".join(parts)


def flat_row(rec: dict) -> dict:
    graded = [g["grade"] for g in rec["grades_by_outcome"] if g["grade"]]
    best = max(graded, key=lambda g: GRADE_RANK[g]) if graded else None
    worst = min(graded, key=lambda g: GRADE_RANK[g]) if graded else None
    return {
        "slug": rec["slug"],
        "name": rec["name"],
        "compound_class": rec["compound_class"],
        "overall_grade": rec["overall_grade"],
        "is_cosmetic": rec["is_cosmetic"],
        "wada_prohibited": rec["wada"]["prohibited"],
        "n_outcomes": len(rec["grades_by_outcome"]),
        "best_outcome_grade": best,
        "worst_outcome_grade": worst,
        "synonyms": "|".join(rec["synonyms"]),
        "function_tags": "|".join(rec["function_tags"]),
        "related": "|".join(rec["related"]),
        "regions": "|".join([str(ls["region"]) for ls in rec["legal_status"] if ls["region"]]),
        "n_sources": len(rec["sources"]),
        "n_doi_verified": len([c for c in rec["citation_ids"] if c.get("doi")]),
        "last_updated": rec["last_updated"],
        "in_brief": rec["in_brief"],
        "url": rec["url"],
        "structure_image": rec["structure_image"],
        "grade_card_image": rec["grade_card_image"],
    }


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in columns})


def write_parquet(path: Path, rows: list[dict], columns: list[str]) -> None:
    df = pd.DataFrame(rows, columns=columns)
    df.to_parquet(path, index=False)


def ordered(rec: dict) -> dict:
    keys = [k for k in RECORD_ORDER if k in rec] + [k for k in rec if k not in RECORD_ORDER]
    return {k: rec[k] for k in keys}


def checksums(root: Path, dirs: list[Path], out: Path) -> int:
    lines = []
    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.rglob("*")):
            if not f.is_file():
                continue
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            lines.append(f"{h}  {f.relative_to(root).as_posix()}")
    out.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
    return len(lines)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Build the Vallydia Ingredient-Evidence Register dataset.")
    ap.add_argument("--source", default=str(root / "register-source" / "compounds"),
                    help="directory of compound .mdx files (the register export)")
    ap.add_argument("--out", default=str(root / "data"), help="output data directory")
    args = ap.parse_args()

    src = Path(args.source)
    out = Path(args.out)
    if not src.is_dir():
        print(f"ERROR: source directory not found: {src}", file=sys.stderr)
        return 2
    (out / "parquet").mkdir(parents=True, exist_ok=True)

    files = sorted(src.glob("*.mdx"))
    if not files:
        print(f"ERROR: no .mdx files in {src}", file=sys.stderr)
        return 2

    warnings: list[str] = []
    records = [parse_file(f, warnings) for f in files]
    records.sort(key=lambda r: r["slug"])

    dupes = {r["slug"] for r in records if [x["slug"] for x in records].count(r["slug"]) > 1}
    if dupes:
        raise BuildError(f"duplicate slugs: {sorted(dupes)}")

    redactions: list[str] = []
    for rec in records:
        for field in REDACTABLE_FIELDS:
            rec[field] = redact_planning(rec.get(field), rec["slug"], field, redactions)

    attach_images(records, root / "images" / "MANIFEST.csv")

    # 2.1 canonical, lossless
    with (out / "compounds.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(ordered(rec), ensure_ascii=False, sort_keys=False) + "\n")
    (out / "compounds.json").write_text(
        json.dumps([ordered(r) for r in records], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )

    # 2.2 flat table
    flat = [flat_row(r) for r in records]
    flat_cols = list(flat[0].keys())
    write_csv(out / "compounds.csv", flat, flat_cols)

    # 2.3 long / tidy tables
    grades = [
        {"slug": r["slug"], "name": r["name"], "compound_class": r["compound_class"],
         "outcome": g["outcome"], "grade": g["grade"], "base": g["base"],
         "effect": g["effect"], "caveat": g["caveat"]}
        for r in records for g in r["grades_by_outcome"]
    ]
    grade_cols = ["slug", "name", "compound_class", "outcome", "grade", "base", "effect", "caveat"]

    legal = [
        {"slug": r["slug"], "name": r["name"], "region": ls["region"],
         "status": ls["status"], "note": ls["note"]}
        for r in records for ls in r["legal_status"]
    ]
    legal_cols = ["slug", "name", "region", "status", "note"]

    cites = [
        {"slug": r["slug"], "name": r["name"], "source_index": c["source"],
         "source_text": r["sources"][c["source"]], "doi": c["doi"],
         "resolved": c["resolved"], "verified_title": c["verified_title"]}
        for r in records for c in r["citation_ids"]
    ]
    cite_cols = ["slug", "name", "source_index", "source_text", "doi", "resolved", "verified_title"]

    claims = [
        {"slug": r["slug"], "name": r["name"], "claim_type": kind, "claim_text": text}
        for r in records if r["cosmetic_claims"]
        for kind in ("allowed", "forbidden")
        for text in r["cosmetic_claims"][kind]
    ]
    claim_cols = ["slug", "name", "claim_type", "claim_text"]

    write_csv(out / "grades.csv", grades, grade_cols)
    write_csv(out / "legal_status.csv", legal, legal_cols)
    write_csv(out / "citations.csv", cites, cite_cols)
    write_csv(out / "cosmetic_claims.csv", claims, claim_cols)

    # 2.4 parquet mirrors
    write_parquet(out / "parquet" / "compounds.parquet", flat, flat_cols)
    write_parquet(out / "parquet" / "grades.parquet", grades, grade_cols)
    write_parquet(out / "parquet" / "legal_status.parquet", legal, legal_cols)
    write_parquet(out / "parquet" / "citations.parquet", cites, cite_cols)
    write_parquet(out / "parquet" / "cosmetic_claims.parquet", claims, claim_cols)

    # identifiers.csv is produced by enrich_identifiers.py; mirror it to parquet if present
    ident_csv = out / "identifiers.csv"
    if ident_csv.exists():
        pd.read_csv(ident_csv, dtype=str).fillna("").to_parquet(
            out / "parquet" / "identifiers.parquet", index=False
        )

    # 2.5 RAG corpus
    with (out / "corpus.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps({
                "slug": rec["slug"], "name": rec["name"], "title": rec["title"],
                "url": rec["url"], "text": corpus_text(rec),
            }, ensure_ascii=False) + "\n")

    # Firewall guard: re-scan everything we are about to ship. `body_markdown` is the raw
    # register body and is swept too — nothing gets a pass. A hit here is a hard failure,
    # not a warning: the whole point is that a future register edit cannot leak the roadmap
    # into a public, mirrored, CC-BY artifact by accident.
    leaks: list[str] = []
    for rec in records:
        for field in REDACTABLE_FIELDS + ("body_markdown",):
            value = rec.get(field)
            if isinstance(value, str) and (m := PLANNING_RE.search(value)):
                leaks.append(f"{rec['slug']}.{field}: {m.group(0)!r}")
    for rec in records:
        if m := PLANNING_RE.search(corpus_text(rec)):
            leaks.append(f"{rec['slug']}.corpus_text: {m.group(0)!r}")
    if leaks:
        raise BuildError(
            "internal product-planning language would have been published:\n  "
            + "\n  ".join(leaks)
            + "\nExtend redact_planning() or fix the register entry before releasing."
        )

    n_files = checksums(root, [out, root / "images"], root / "checksums.sha256")

    # ---- build report -------------------------------------------------------
    classes: dict[str, int] = {}
    for r in records:
        classes[r["compound_class"]] = classes.get(r["compound_class"], 0) + 1
    no_cites = [r["slug"] for r in records if not r["citation_ids"]]
    no_overall = [r["slug"] for r in records if r["overall_grade"] is None]
    null_grades = sum(1 for g in grades if g["grade"] is None)

    print("=" * 68)
    print("BUILD REPORT — Vallydia Ingredient-Evidence Register")
    print("=" * 68)
    print(f"source                : {src}")
    print(f"compounds parsed      : {len(records)} (from {len(files)} .mdx files)")
    print(f"class distribution    : " + ", ".join(f"{k}={v}" for k, v in sorted(classes.items())))
    print(f"cosmetic compounds    : {sum(1 for r in records if r['is_cosmetic'])}")
    print(f"WADA-prohibited       : {sum(1 for r in records if r['wada']['prohibited'])}")
    print(f"grade rows            : {len(grades)} ({null_grades} with null grade — by design)")
    print(f"legal-status rows     : {len(legal)}")
    print(f"citation rows (DOI)   : {len(cites)}  across {len({c['slug'] for c in cites})} compounds")
    print(f"cosmetic-claim rows   : {len(claims)} across {len({c['slug'] for c in claims})} compounds")
    print(f"total source refs     : {sum(len(r['sources']) for r in records)}")
    print(f"no citation_ids       : {len(no_cites)} -> {', '.join(no_cites) if no_cites else '-'}")
    print(f"null overall_grade    : {len(no_overall)} -> {', '.join(no_overall) if no_overall else '-'}")
    print(f"checksummed files     : {n_files}")
    print(f"firewall redactions   : {len(redactions)} (internal planning language kept out of the export)")
    for r in redactions:
        print(f"  - {r}")
    if warnings:
        print("\nwarnings:")
        for w in warnings:
            print(f"  ! {w}")
    else:
        print("\nwarnings              : none")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as e:
        print(f"BUILD FAILED: {e}", file=sys.stderr)
        sys.exit(1)
