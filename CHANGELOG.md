# Changelog

All notable changes to the Vallydia Ingredient-Evidence Register dataset.
Versioning follows [Semantic Versioning](https://semver.org/): a breaking schema change bumps the major version.

## [Unreleased]

### Changed
- **The graded name is now always a nonproprietary one, and trade names moved to their own
  field.** A grade assesses a *substance*, so it must hang on the substance's nomenclature name —
  the INCI name for a cosmetic ingredient, the INN for a drug — never on a supplier's trademark.
  Previously `name` led with the trade name (`Matrixyl (Palmitoyl Pentapeptide-4)`), and that
  string was denormalized next to `grade` in `grades.csv`, `citations.csv`, `legal_status.csv`,
  `cosmetic_claims.csv` and `corpus.jsonl`.

  **Why this could not wait.** The dataset is CC-BY-4.0 and mirrored to Zenodo (DOI, permanent by
  design), Hugging Face, Kaggle, PyPI, npm and GitHub, and the licence invites redistribution. A
  grade published against someone's trademark can be corrected on our own site in minutes, but it
  cannot be recalled from a DOI-pinned archive or a third-party fork. The exposure is not the
  assessment — the grades are our own and they stand — it is the inability to *execute* a
  correction once the string is out. So the split had to land before the next published version.

  New fields on `compounds`: `inci_name`, `inn`, `trade_names` (array; pipe-joined in CSV). The
  graded name resolves as `inci_name ?? inn ?? name`. Ten records changed: `matrixyl`,
  `argireline`, `snap-8`, `syn-ake`, `ahk-cu`, `palmitoyl-tripeptide-1-5` (INCI), and
  `afamelanotide`, `pramlintide`, `ss-31`, `oxytocin` (INN).

  **Do not "simplify" this back.** `build/validate_dataset.py` now fails the build if a name in
  `trade_names` reappears in the graded `name`, and `--selftest` proves that check fires. The
  invariant is mechanical precisely because a convention would be quietly undone.

  Notes on specific records:
  - `SNAP-8` is kept in `trade_names` as Lipotec's trade designation, but it is **not a registered
    mark** — no EUIPO or USPTO registration was found. Recorded in case the distinction matters.
  - `Elamipretide` is an INN, not a trademark, so it is the graded name for `ss-31` and is **not**
    in `trade_names`. That record's real marks are `Forzinity` and `Bendavia` — which a "whatever
    is in the parentheses" rule would have missed while wrongly capturing the INN.
  - `oxytocin` carries two marks (`Pitocin`, `Syntocinon`), not one.
  - Slugs are unchanged and will not be renamed: they are the dataset's primary key, the API key
    and the graph node for `related`. The exposure is in the published claim, not the URL.
  - `title` still carries the referential display form, because it is the site page title and
    referential use is legitimate. The *graded* field is what had to be neutral.

## [1.0.0] — 2026-07-14

Initial public release: 85 compounds, evidence-graded, and published as a machine-linkable,
continuously-validated asset. None of the tooling below changes the 85 compounds or their grades.

### Added
- **Canonical data** — `data/compounds.jsonl` and `.json`: full nested records, lossless, including the parsed (`body_sections`) and raw (`body_markdown`) Markdown body.
- **Flat table** — `data/compounds.csv`, one row per compound with computed `best_outcome_grade` / `worst_outcome_grade` (nulls ignored, never coerced to `F`).
- **Tidy tables** — `data/grades.csv` (456 outcome rows, 97 deliberately ungraded), `data/legal_status.csv` (132 rows), `data/citations.csv` (117 DOI-verified citations across 50 compounds), `data/cosmetic_claims.csv` (246 allowed/forbidden claim rows across 21 cosmetic ingredients).
- **Chemical identifiers** — `data/identifiers.csv`: CAS, PubChem CID, InChIKey, InChI, SMILES, UNII, ChEMBL and DrugBank ids, each with `identifier_source` and `identifier_confidence`. 64 of 85 resolved at high confidence; 21 left blank on purpose (blends, stacks and multi-component biologics have no single structure).
- **Parquet mirrors** — `data/parquet/*.parquet` for all seven tables (Hugging Face auto-generates Croissant JSON-LD from these).
- **Retrieval corpus** — `data/corpus.jsonl`: one natural-language record per compound, each carrying its `vallydia.com` URL so a retrieved passage always resolves back to an attributable source.
- **Image layer** — 42 RDKit-rendered 2D structures and 22 factual data cards for molecules too large for an honest 2D depiction, with mandatory `alt_text` in `images/MANIFEST.csv`.
- **Evidence-grade cards** (§12.2) — `images/grade-cards/<slug>.svg`, one per compound: a
  per-outcome A–F strip, the overall-grade badge and a "based on N sources, M DOI-verified"
  line, rendered deterministically from the grades. Null grades show as a neutral dash, never
  an F. `grade_card_image` path joined into `compounds.jsonl/.json/.csv`.
- **Scholarly cross-links** (§10.3) — `data/citations_enriched.csv` (+ parquet): every DOI
  enriched against OpenAlex and Semantic Scholar (openalex_id, semantic_scholar_id,
  citation_count, oa_url). All 117 carry an OpenAlex id + citation count; open-access URLs on
  74; Semantic Scholar where its rate limit allowed. Missing cross-links are blank + logged,
  never guessed.
- **Read-only API** (§10.1) — `api/`: OpenAPI 3.1 spec + a FastAPI reference implementation
  (serves the generated data from memory, no database), Dockerfile, and tests. Every response
  carries `attribution` + `source_url`; CORS open for read. Deploy is a manual operator step.
- **Loader packages** (§10.2) — `packages/python` (`vallydia-register`, pandas DataFrames) and
  `packages/npm` (`@vallydia-data/ingredient-register`, typed objects). Both pull from the published
  data with a local-checkout offline mode, attribute Vallydia, and ship tests.
- **Reproducible build** — `build/generate_dataset.py`, `build/enrich_identifiers.py`, `build/generate_images.py`, with pinned dependencies. Deterministic: two runs on the same source produce byte-identical output.
- **Integrity validation suite** — `build/validate_dataset.py`: referential integrity across
  the six configs, grade-scale and overall/outcome consistency, DOI well-formedness, the
  no-fabricated-identifier rule, and a firewall lint (no commerce or dosing-instruction text).
  `--selftest` proves it catches seeded bad rows. Wired into CI.
- **GitHub Actions** — `.github/workflows/validate.yml` (integrity + all package/API tests on
  every push/PR) and `rebuild.yml` (weekly + manual: refresh scholarly links, checksums and
  Croissant, then open a PR — never auto-merges). Images are rendered locally, not in the
  rebuild: they derive from inputs the job does not touch, and RDKit's 2D coordinates are not
  byte-identical across platforms, so re-rendering there is pure diff noise.
- `build/generate_dataset.py --checksums-only` for CI checksum refresh without the private source.
- **Croissant metadata** — `croissant.json` (MLCommons Croissant 1.0 JSON-LD) describing the eight
  published CSV tables: per-column descriptions, dataTypes, the A–F grade scale (with null handling,
  no invented E), and per-file sha256 checksums. Generated deterministically by
  `build/generate_croissant.py` from the committed data + `checksums.sha256`, reconciled with
  CITATION.cff. Complements Hugging Face's auto-generated Croissant for the GitHub/Zenodo copies.
  CI validates it with `mlcroissant` and enforces that the committed file stays in step (`--check`).
- **Documentation** — README (doubling as the Hugging Face dataset card), `datasheet.md` (Datasheets for Datasets), `DATA_DICTIONARY.md`, `METHODOLOGY.md`, `PUBLISHING.md`, `CITATION.cff`, `.zenodo.json`, `dataset-metadata.json`, `checksums.sha256`.

### Notes
- The register's MDX source stays private and unvendored; the auto-rebuild refreshes only the
  layers derivable from committed data. Full MDX regeneration remains a documented local step.

### Known gaps (reported, not hidden)
- 35 compounds carry no DOI-verified citation yet; they have free-text sources. Listed by slug in the build report. Closing this gap is the priority for the next version.
- 21 compounds have no chemical identifiers, by design.
- `entity_note` flags one live entity mismatch (`ghk-cu`: PubChem's record is the free tripeptide ligand, not the copper(II) complex). The image `alt_text` states this rather than mislabelling the structure.

[1.0.0]: https://github.com/yamius/ingredient-evidence-register/releases/tag/v1.0.0
