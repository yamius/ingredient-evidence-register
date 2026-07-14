# Changelog

All notable changes to the Vallydia Ingredient-Evidence Register dataset.
Versioning follows [Semantic Versioning](https://semver.org/): a breaking schema change bumps the major version.

## [1.0.0] — 2026-07-14

Initial public release. 85 compounds.

### Added
- **Canonical data** — `data/compounds.jsonl` and `.json`: full nested records, lossless, including the parsed (`body_sections`) and raw (`body_markdown`) Markdown body.
- **Flat table** — `data/compounds.csv`, one row per compound with computed `best_outcome_grade` / `worst_outcome_grade` (nulls ignored, never coerced to `F`).
- **Tidy tables** — `data/grades.csv` (456 outcome rows, 97 deliberately ungraded), `data/legal_status.csv` (132 rows), `data/citations.csv` (117 DOI-verified citations across 50 compounds), `data/cosmetic_claims.csv` (246 allowed/forbidden claim rows across 21 cosmetic ingredients).
- **Chemical identifiers** — `data/identifiers.csv`: CAS, PubChem CID, InChIKey, InChI, SMILES, UNII, ChEMBL and DrugBank ids, each with `identifier_source` and `identifier_confidence`. 64 of 85 resolved at high confidence; 21 left blank on purpose (blends, stacks and multi-component biologics have no single structure).
- **Parquet mirrors** — `data/parquet/*.parquet` for all six tables (Hugging Face auto-generates Croissant JSON-LD from these).
- **Retrieval corpus** — `data/corpus.jsonl`: one natural-language record per compound, each carrying its `vallydia.com` URL so a retrieved passage always resolves back to an attributable source.
- **Image layer** — 42 RDKit-rendered 2D structures and 22 factual data cards for molecules too large for an honest 2D depiction, with mandatory `alt_text` in `images/MANIFEST.csv`.
- **Reproducible build** — `build/generate_dataset.py`, `build/enrich_identifiers.py`, `build/generate_images.py`, with pinned dependencies. Deterministic: two runs on the same source produce byte-identical output.
- **Documentation** — README (doubling as the Hugging Face dataset card), `datasheet.md` (Datasheets for Datasets), `DATA_DICTIONARY.md`, `METHODOLOGY.md`, `PUBLISHING.md`, `CITATION.cff`, `.zenodo.json`, `dataset-metadata.json`, `checksums.sha256`.

### Known gaps (reported, not hidden)
- 35 compounds carry no DOI-verified citation yet; they have free-text sources. Listed by slug in the build report. Closing this gap is the priority for the next version.
- 21 compounds have no chemical identifiers, by design.
- `grade_card_image` is not populated: evidence-grade cards ship in a later version.
- `entity_note` flags one live entity mismatch (`ghk-cu`: PubChem's record is the free tripeptide ligand, not the copper(II) complex). The image `alt_text` states this rather than mislabelling the structure.

[1.0.0]: https://github.com/yamius/ingredient-evidence-register/releases/tag/v1.0.0
