#!/usr/bin/env python3
"""
Vallydia Ingredient-Evidence Register — Croissant metadata generator.

Emits `croissant.json` at the repo root: an MLCommons Croissant 1.0 JSON-LD
description of the published tables, so the dataset is machine-discoverable and
loadable by Croissant-aware ML tooling (and by Google Dataset Search, which reads
the schema.org/Dataset that Croissant extends).

Hugging Face auto-generates an equivalent Croissant from the Parquet mirrors; this
committed file serves the GitHub and Zenodo copies (which are not on HF) and pins
the field descriptions and the A–F grade scale so they cannot drift.

Deterministic: field descriptions are embedded here, the per-file sha256 checksums
are read from `checksums.sha256` (produced by generate_dataset.py), and no
timestamps are written into the artifact. Running it twice on the same data yields
byte-identical output, so `rebuild.yml` can regenerate it. Dataset-level facts
(version, license, DOI, dates) are reconciled with CITATION.cff and .zenodo.json.

Usage:
    python build/generate_croissant.py            # writes ./croissant.json
    python build/generate_croissant.py --check     # verify the committed file is current
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- dataset-level facts (kept in step with CITATION.cff / .zenodo.json) ----------
NAME = "ingredient-evidence-register"
TITLE = "Vallydia Ingredient-Evidence Register"
VERSION = "1.2.0"
DATE_PUBLISHED = "2026-07-14"
DATE_MODIFIED = "2026-07-21"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DOI = "10.5281/zenodo.21364453"
DOI_URL = f"https://doi.org/{DOI}"
# /data is live; use it as the dataset landing page (matches CITATION.cff and the
# site's schema.org/Dataset).
DATASET_URL = "https://vallydia.com/data"
RAW_BASE = "https://raw.githubusercontent.com/yamius/ingredient-evidence-register/main"
ORCID = "https://orcid.org/0009-0009-1636-8487"

DESCRIPTION = (
    "An open, evidence-graded reference dataset of 85 cosmetic and research "
    "ingredients (peptides, small molecules, proteins, blends). Each compound carries "
    "per-outcome A–F evidence grades (475 graded outcome rows; a compound can be B for "
    "one outcome and F for another, and grades left null are deliberate non-claims such "
    "as safety or skin penetration, never coerced to F), DOI-verified citations joined "
    "back to the source text, legal status by region (INT/EU/US/UK) and WADA status, "
    "machine-readable cosmetic-claims maps (permitted and forbidden claim wordings), and "
    "chemical identifiers (CAS, PubChem CID, InChIKey, SMILES) with explicit confidence "
    "and provenance. Scope is appearance and evidence only: no dosing, administration or "
    "commerce information, by design. Grades are Vallydia's own evidence assessment, not "
    "third-party certification. Published as CSV and Parquet; this Croissant describes the "
    "CSV tables."
)

CITE_AS = (
    "Bilenko, J. (2026). Vallydia Ingredient-Evidence Register (v1.2.0) "
    f"[Data set]. Vallydia. https://doi.org/{DOI}"
)

KEYWORDS = [
    "skincare ingredients",
    "cosmetic ingredients",
    "evidence grading",
    "dermatology",
    "open data",
    "evidence-based skincare",
]

GRADE_SCALE = (
    "Evidence grade on the register's A–F scale: A, B, C, D or F, or empty/null. "
    "There is no E. Empty means the row is a deliberate non-claim (e.g. safety, skin "
    "penetration) — it must not be read or coerced as F."
)

# --- table schema -----------------------------------------------------------------
# Each entry: (record_set_id, repo-relative CSV path, table description, fields).
# Each field: (column, dataType, description). dataType is a schema.org term.
# Descriptions are the canonical column definitions (kept in step with the Kaggle
# resource schema in dataset-metadata.json).
TABLES = [
    (
        "compounds", "data/compounds.csv",
        "One row per compound (85): scalar core plus pipe-joined list columns.",
        [
            ("slug", "sc:Text", "Unique id and join key (e.g. ghk-cu). Stable: slugs are never renamed."),
            ("name", "sc:Text",
             "The graded name, always a nonproprietary one: the INCI name for a cosmetic "
             "ingredient, the INN for a drug, otherwise the register's own name. A grade "
             "assesses a substance, so it never hangs on a supplier's trademark — those are "
             "in trade_names."),
            ("inci_name", "sc:Text", "INCI name (EU/US cosmetic ingredient glossary); blank where the compound is not a cosmetic ingredient."),
            ("inn", "sc:Text", "International Nonproprietary Name (WHO) for drug substances; blank where none exists."),
            ("trade_names", "sc:Text",
             "Pipe-joined trademarked/supplier names for the same substance (e.g. Matrixyl for "
             "Palmitoyl Pentapeptide-4). Reference only; blank where the substance has none."),
            ("compound_class", "sc:Text", "peptide | small_molecule | protein | blend | polysaccharide."),
            ("overall_grade", "sc:Text", "A–F summary of the leading application; empty if unassigned. No E."),
            ("is_cosmetic", "sc:Boolean", "Lawful cosmetic ingredient in at least one form."),
            ("wada_prohibited", "sc:Boolean", "On the WADA prohibited list."),
            ("n_outcomes", "sc:Integer", "Number of graded outcome rows."),
            ("best_outcome_grade", "sc:Text", "Best non-null outcome grade; nulls ignored."),
            ("worst_outcome_grade", "sc:Text", "Worst non-null outcome grade; nulls ignored, never treated as F."),
            ("synonyms", "sc:Text", "Pipe-joined alternative names, including INCI names."),
            ("function_tags", "sc:Text", "Pipe-joined functional tags."),
            ("related", "sc:Text", "Pipe-joined slugs of related compounds."),
            ("regions", "sc:Text", "Pipe-joined regions present in legal_status."),
            ("n_sources", "sc:Integer", "Count of cited sources."),
            ("n_doi_verified", "sc:Integer", "Count of citations with a verified DOI; 0 = a reported gap, not an error."),
            ("last_updated", "sc:Date", "YYYY-MM-DD the register entry was last revised."),
            ("in_brief", "sc:Text", "Plain-language summary."),
            ("url", "sc:URL", "Canonical source page on vallydia.com."),
            ("structure_image", "sc:Text", "Path to the structure image, or empty."),
            ("grade_card_image", "sc:Text", "Path to the evidence-grade card image, or empty."),
        ],
    ),
    (
        "grades", "data/grades.csv",
        "One row per compound × outcome (475). The analytical heart of the dataset. 19 rows grade a marketed claim rather than an effect; their `outcome` opens with the claim in quotes.",
        [
            ("slug", "sc:Text", "Join key."),
            ("name", "sc:Text", "The graded name, denormalized: nonproprietary (INCI/INN), never a trademark — see compounds.trade_names."),
            ("compound_class", "sc:Text", "Compound class (denormalized)."),
            ("outcome", "sc:Text", "The specific claim being graded."),
            ("grade", "sc:Text", GRADE_SCALE),
            ("base", "sc:Text", "The evidence base the grade rests on."),
            ("effect", "sc:Text", "What the evidence reports."),
            ("caveat", "sc:Text", "Why the grade is not higher."),
        ],
    ),
    (
        "legal_status", "data/legal_status.csv",
        "One row per compound × region (132).",
        [
            ("slug", "sc:Text", "Join key."),
            ("name", "sc:Text", "The graded name, denormalized: nonproprietary (INCI/INN), never a trademark — see compounds.trade_names."),
            ("region", "sc:Text", "INT | EU | US | UK."),
            ("status", "sc:Text", "Short status label."),
            ("note", "sc:Text", "Long-form regulatory detail. Ages; check last_updated."),
        ],
    ),
    (
        "citations", "data/citations.csv",
        "DOI provenance table (125 rows across 51 compounds).",
        [
            ("slug", "sc:Text", "Join key."),
            ("name", "sc:Text", "The graded name, denormalized: nonproprietary (INCI/INN), never a trademark — see compounds.trade_names."),
            ("source_index", "sc:Integer", "0-based index into that compound's sources list."),
            ("source_text", "sc:Text", "The free-text citation, resolved from sources[source_index]."),
            ("doi", "sc:Text", "DOI of the cited work."),
            ("resolved", "sc:Text", "Resolution confidence, e.g. high."),
            ("verified_title", "sc:Text", "Title as returned by the resolver."),
        ],
    ),
    (
        "citations_enriched", "data/citations_enriched.csv",
        "The citations table enriched with scholarly cross-links (125 rows).",
        [
            ("slug", "sc:Text", "Join key."),
            ("name", "sc:Text", "The graded name, denormalized: nonproprietary (INCI/INN), never a trademark — see compounds.trade_names."),
            ("source_index", "sc:Integer", "0-based index into that compound's sources list."),
            ("source_text", "sc:Text", "The free-text citation, resolved from sources[source_index]."),
            ("doi", "sc:Text", "DOI of the cited work."),
            ("resolved", "sc:Text", "Resolution confidence, e.g. high."),
            ("verified_title", "sc:Text", "Title as returned by the resolver."),
            ("openalex_id", "sc:Text", "OpenAlex work id; blank where unresolved, never guessed."),
            ("semantic_scholar_id", "sc:Text", "Semantic Scholar paper id; blank where the rate limit blocked lookup."),
            ("citation_count", "sc:Integer", "Citation count reported by OpenAlex; blank if unresolved."),
            ("oa_url", "sc:URL", "Open-access URL for the work, where one exists; blank otherwise."),
            ("enrichment_source", "sc:Text", "Which resolver(s) supplied the cross-links for this row."),
        ],
    ),
    (
        "cosmetic_claims", "data/cosmetic_claims.csv",
        "Permitted and forbidden claim wordings per cosmetic ingredient (246 rows across 21 compounds).",
        [
            ("slug", "sc:Text", "Join key; only is_cosmetic compounds appear."),
            ("name", "sc:Text", "The graded name, denormalized: nonproprietary (INCI/INN), never a trademark — see compounds.trade_names."),
            ("claim_type", "sc:Text", "allowed | forbidden."),
            ("claim_text", "sc:Text", "The claim wording. forbidden = asserts a physiological/therapeutic action and must not be used."),
        ],
    ),
    (
        "identifiers", "data/identifiers.csv",
        "Chemical identifiers with confidence and provenance (85 rows; 64 confident, 21 intentionally blank).",
        [
            ("slug", "sc:Text", "Join key."),
            ("name", "sc:Text", "The graded name, denormalized: nonproprietary (INCI/INN), never a trademark."),
            ("compound_class", "sc:Text", "Compound class."),
            ("cas", "sc:Text", "CAS registry number; blank where depositors disagree, never guessed."),
            ("pubchem_cid", "sc:Text", "PubChem Compound ID."),
            ("inchikey", "sc:Text", "InChIKey — the best cross-database join key."),
            ("inchi", "sc:Text", "Full InChI string."),
            ("smiles", "sc:Text", "Canonical SMILES; only high-confidence SMILES are rendered as images."),
            ("unii", "sc:Text", "FDA UNII; blank if ambiguous."),
            ("chembl_id", "sc:Text", "ChEMBL id where available."),
            ("drugbank_id", "sc:Text", "DrugBank id where available."),
            ("identifier_source", "sc:Text", "Provenance of the identifier match."),
            ("identifier_confidence", "sc:Text", "high | medium | low | none."),
            ("entity_note", "sc:Text", "Set when the resolved record is a real but distinct entity from the register compound."),
        ],
    ),
    (
        "images", "images/MANIFEST.csv",
        "Manifest of the published image layer: 2D structures and factual data cards, with mandatory alt text.",
        [
            ("slug", "sc:Text", "Join key to the compound."),
            ("image_type", "sc:Text", "structure | data_card | grade_card."),
            ("path", "sc:Text", "Repo-relative path to the image file."),
            ("format", "sc:Text", "Image encoding, e.g. png or svg."),
            ("alt_text", "sc:Text", "Mandatory alternative text describing the image."),
            ("license", "sc:Text", "Image license."),
            ("source", "sc:Text", "How the image was produced or where it came from."),
            ("note", "sc:Text", "Caveats, e.g. an entity mismatch stated honestly rather than mislabelled."),
        ],
    ),
]


def load_checksums(path: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        h, rel = line.split(None, 1)
        sums[rel.strip()] = h
    return sums


def build(sums: dict[str, str]) -> dict:
    distribution = []
    record_sets = []
    for rs_id, rel_path, table_desc, fields in TABLES:
        if rel_path not in sums:
            raise SystemExit(f"ERROR: {rel_path} missing from checksums.sha256 — run generate_dataset.py --checksums-only first")
        file_id = f"{rs_id}.csv"
        distribution.append({
            "@type": "cr:FileObject",
            "@id": file_id,
            "name": file_id,
            "description": table_desc,
            "contentUrl": f"{RAW_BASE}/{rel_path}",
            "encodingFormat": "text/csv",
            "sha256": sums[rel_path],
        })
        record_sets.append({
            "@type": "cr:RecordSet",
            "@id": rs_id,
            "name": rs_id,
            "description": table_desc,
            "field": [
                {
                    "@type": "cr:Field",
                    "@id": f"{rs_id}/{col}",
                    "name": col,
                    "description": desc,
                    "dataType": dtype,
                    "source": {
                        "fileObject": {"@id": file_id},
                        "extract": {"column": col},
                    },
                }
                for col, dtype, desc in fields
            ],
        })

    return {
        "@context": {
            "@language": "en",
            "@vocab": "https://schema.org/",
            "citeAs": "cr:citeAs",
            "column": "cr:column",
            "conformsTo": "dct:conformsTo",
            "cr": "http://mlcommons.org/croissant/",
            "data": {"@id": "cr:data", "@type": "@json"},
            "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
            "dct": "http://purl.org/dc/terms/",
            "equivalentProperty": "cr:equivalentProperty",
            "examples": {"@id": "cr:examples", "@type": "@json"},
            "extract": "cr:extract",
            "field": "cr:field",
            "fileObject": "cr:fileObject",
            "fileProperty": "cr:fileProperty",
            "fileSet": "cr:fileSet",
            "format": "cr:format",
            "includes": "cr:includes",
            "isLiveDataset": "cr:isLiveDataset",
            "jsonPath": "cr:jsonPath",
            "key": "cr:key",
            "md5": "cr:md5",
            "parentField": "cr:parentField",
            "path": "cr:path",
            "rai": "http://mlcommons.org/croissant/RAI/",
            "recordSet": "cr:recordSet",
            "references": "cr:references",
            "regex": "cr:regex",
            "repeated": "cr:repeated",
            "replace": "cr:replace",
            "samplingRate": "cr:samplingRate",
            "sc": "https://schema.org/",
            "separator": "cr:separator",
            "source": "cr:source",
            "subField": "cr:subField",
            "transform": "cr:transform",
        },
        "@type": "sc:Dataset",
        "conformsTo": "http://mlcommons.org/croissant/1.0",
        "name": NAME,
        "alternateName": TITLE,
        "description": DESCRIPTION,
        "creator": {
            "@type": "sc:Person",
            "name": "Jacob Bilenko",
            "affiliation": {"@type": "sc:Organization", "name": "Vallydia"},
            "sameAs": ORCID,
        },
        "publisher": {
            "@type": "sc:Organization",
            "name": "Vallydia",
            "url": "https://vallydia.com",
        },
        "url": DATASET_URL,
        "sameAs": "https://vallydia.com",
        "license": LICENSE_URL,
        "version": VERSION,
        "datePublished": DATE_PUBLISHED,
        "dateModified": DATE_MODIFIED,
        "keywords": KEYWORDS,
        "citeAs": CITE_AS,
        "identifier": DOI_URL,
        "isLiveDataset": False,
        "distribution": distribution,
        "recordSet": record_sets,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate croissant.json for the dataset.")
    ap.add_argument("--out", default=str(ROOT / "croissant.json"), help="output path")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the committed file is out of date (for CI)")
    args = ap.parse_args()

    sums = load_checksums(ROOT / "checksums.sha256")
    doc = build(sums)
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"

    out = Path(args.out)
    if args.check:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current != text:
            print("croissant.json is out of date — run: python build/generate_croissant.py", file=sys.stderr)
            return 1
        print("croissant.json is up to date")
        return 0

    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(ROOT).as_posix()} — {len(doc['distribution'])} files, {len(doc['recordSet'])} record sets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
