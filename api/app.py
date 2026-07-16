#!/usr/bin/env python3
"""
Read-only reference API over the Vallydia Ingredient-Evidence Register — §10.1.

Serves the generated dataset (data/*.jsonl + *.csv) straight from memory. No database, no
writes, no auth. Every response carries an `attribution` string and a `source_url` pointing
back to vallydia.com, because CC-BY-4.0 requires attribution and this is the mechanism.

Firewall: the API exposes only what is in the dataset — appearance/evidence fields and
neutral chemical identifiers. It introduces no dosing, administration or commerce data.

Run locally:
    pip install -r api/requirements.txt
    uvicorn api.app:app --reload
    # docs at http://127.0.0.1:8000/docs

Deploy: see PUBLISHING.md (Vercel / Fly / Render) — that step is manual (Yakiv's).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

ATTRIBUTION = "Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0."
SOURCE_URL = "https://vallydia.com"
DATA = Path(__file__).resolve().parent.parent / "data"


def _load() -> dict[str, Any]:
    def jsonl(name: str) -> list[dict]:
        p = DATA / name
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []

    def table(name: str) -> list[dict]:
        p = DATA / name
        if not p.exists():
            return []
        with p.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    compounds = jsonl("compounds.jsonl")
    # citations_enriched is preferred when present; fall back to the base citations table
    citations = table("citations_enriched.csv") or table("citations.csv")
    return {
        "compounds": compounds,
        "by_slug": {c["slug"]: c for c in compounds},
        "grades": table("grades.csv"),
        "citations": citations,
        "cosmetic_claims": table("cosmetic_claims.csv"),
        "identifiers": table("identifiers.csv"),
        "legal_status": table("legal_status.csv"),
    }


DB = _load()

app = FastAPI(
    title="Vallydia Ingredient-Evidence Register API",
    version="1.1.0",
    description=(
        "Read-only API over an evidence-graded open dataset of cosmetic and research "
        "ingredients. Appearance/evidence reference only — no dosing, administration or "
        "commerce data. CC-BY-4.0; attribution to vallydia.com required."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
)


def envelope(data: Any, **extra: Any) -> JSONResponse:
    body = {"attribution": ATTRIBUTION, "source_url": SOURCE_URL, **extra, "data": data}
    return JSONResponse(body)


@app.get("/")
def root() -> JSONResponse:
    return envelope(
        {
            "name": "Vallydia Ingredient-Evidence Register API",
            "version": "1.1.0",
            "license": "CC-BY-4.0",
            "compounds": len(DB["compounds"]),
            "endpoints": [
                "/compounds", "/compounds/{slug}", "/grades", "/citations",
                "/cosmetic-claims", "/identifiers", "/search", "/docs",
            ],
        }
    )


@app.get("/compounds")
def list_compounds(
    compound_class: str | None = Query(None, alias="class"),
    is_cosmetic: bool | None = None,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    rows = DB["compounds"]
    if compound_class:
        rows = [r for r in rows if r["compound_class"] == compound_class]
    if is_cosmetic is not None:
        rows = [r for r in rows if bool(r["is_cosmetic"]) == is_cosmetic]
    page = rows[offset: offset + limit]
    return envelope(page, count=len(page), total=len(rows), offset=offset, limit=limit)


@app.get("/compounds/{slug}")
def get_compound(slug: str) -> JSONResponse:
    rec = DB["by_slug"].get(slug)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"no compound with slug {slug!r}")
    return envelope(rec)


@app.get("/grades")
def get_grades(
    slug: str | None = None,
    grade: str | None = Query(None, description="A|B|C|D|F"),
) -> JSONResponse:
    rows = DB["grades"]
    if slug:
        rows = [r for r in rows if r["slug"] == slug]
    if grade:
        rows = [r for r in rows if r["grade"] == grade]
    return envelope(rows, count=len(rows))


@app.get("/citations")
def get_citations(slug: str | None = None) -> JSONResponse:
    rows = DB["citations"]
    if slug:
        rows = [r for r in rows if r["slug"] == slug]
    return envelope(rows, count=len(rows))


@app.get("/cosmetic-claims")
def get_claims(
    slug: str | None = None,
    claim_type: str | None = Query(None, description="allowed|forbidden"),
) -> JSONResponse:
    rows = DB["cosmetic_claims"]
    if slug:
        rows = [r for r in rows if r["slug"] == slug]
    if claim_type:
        rows = [r for r in rows if r["claim_type"] == claim_type]
    return envelope(rows, count=len(rows))


@app.get("/identifiers")
def get_identifiers(slug: str | None = None) -> JSONResponse:
    rows = DB["identifiers"]
    if slug:
        rows = [r for r in rows if r["slug"] == slug]
    return envelope(rows, count=len(rows))


@app.get("/search")
def search(q: str = Query(..., min_length=1)) -> JSONResponse:
    needle = q.lower()
    hits = []
    for c in DB["compounds"]:
        hay = " ".join([
            c["name"], c["slug"], c["compound_class"],
            " ".join(c.get("synonyms", [])), " ".join(c.get("function_tags", [])),
        ]).lower()
        if needle in hay:
            hits.append({
                "slug": c["slug"], "name": c["name"], "compound_class": c["compound_class"],
                "overall_grade": c["overall_grade"], "url": c["url"],
            })
    return envelope(hits, count=len(hits), query=q)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
