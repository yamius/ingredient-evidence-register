---
license: cc-by-4.0
language:
  - en
pretty_name: "Vallydia Ingredient-Evidence Register"
tags:
  - cosmetics
  - skincare
  - ingredients
  - evidence
  - peptides
  - dermatology
  - tabular
task_categories:
  - text-classification
  - question-answering
size_categories:
  - n<1K
configs:
  - config_name: compounds
    data_files: data/parquet/compounds.parquet
  - config_name: grades
    data_files: data/parquet/grades.parquet
  - config_name: legal_status
    data_files: data/parquet/legal_status.parquet
  - config_name: citations
    data_files: data/parquet/citations.parquet
  - config_name: cosmetic_claims
    data_files: data/parquet/cosmetic_claims.parquet
  - config_name: identifiers
    data_files: data/parquet/identifiers.parquet
---

# Vallydia Ingredient-Evidence Register

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21364453.svg)](https://doi.org/10.5281/zenodo.21364453)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-blue.svg)](https://creativecommons.org/licenses/by/4.0/)

An open, evidence-graded reference dataset of **85 cosmetic and research ingredients** — peptides, small molecules, proteins and blends — published by [Vallydia](https://vallydia.com) under CC-BY-4.0.

Most ingredient databases tell you what a compound *is*. This one tells you **how good the evidence actually is**, outcome by outcome, and says so honestly when the answer is "we don't know" or "it was tested and it failed".

- **Per-outcome A–F evidence grades** — a compound can be `B` for one outcome and `F` for another. 456 graded outcome rows.
- **DOI-verified citations** — 117 citations resolved to a DOI with a verified title. This is the credibility spine of the dataset.
- **Machine-readable cosmetic-claims maps** — for each cosmetic ingredient, the claims that *may* be made and the claims that **must not** be. 246 claim rows.
- **Legal status by region** (INT / EU / US / UK) and WADA prohibited status.
- **Chemical identifiers** — CAS, PubChem CID, InChIKey, SMILES — each with an explicit confidence level and provenance. Where no confident match exists, the field is **blank on purpose**.
- **Molecular structure images** rendered from those identifiers, correct by construction.

## Scope, and what is deliberately absent

This is an **appearance-and-evidence reference**. It contains **no dosing, no administration or reconstitution information, and no commerce data** — not in any field, and none is introduced by the generator. Research and injectable compounds (GLP-1 analogs, BPC-157, melanotan, and so on) are included as **reference entries with their honest grades and legal status**, never framed as usable or obtainable.

**This is not medical advice.** The grades are Vallydia's own evidence assessment, not third-party certification or peer review (`reviewer_status` is `unassigned` on every row, and we say so rather than implying a review that did not happen).

## Dataset summary

| | |
|---|---|
| Compounds | 85 |
| Classes | peptide (53), small_molecule (23), blend (5), protein (3), polysaccharide (1) |
| Graded outcome rows | 456 (97 intentionally ungraded — see below) |
| Cosmetic ingredients | 21, with 246 permitted/forbidden claim rows |
| Legal-status rows | 132 |
| Cited sources | 373, of which 117 are DOI-verified across 50 compounds |
| WADA-prohibited | 19 |
| Confident chemical identifiers | 64 of 85 (21 honestly blank) |
| Structure images | 42 2D structures + 22 large-molecule data cards |

## Supported tasks

Evidence-grade classification, evidence-grounded question answering, regulatory-claim checking (which claims are permissible for a given cosmetic ingredient), and retrieval-augmented generation over `data/corpus.jsonl`.

## Languages

English (`en`).

## Dataset structure

**Canonical, lossless**
- `data/compounds.jsonl` — one JSON object per compound with the full nested structure, including the parsed Markdown body (`body_sections`) and a raw copy (`body_markdown`). This is the master file and the primary RAG-ingestion format.
- `data/compounds.json` — the same content as a single JSON array.

**Flat table**
- `data/compounds.csv` — one row per compound: scalar core plus `|`-joined lists, and `best_outcome_grade` / `worst_outcome_grade` computed over the non-null grades.

**Long / tidy tables** (the analytical heart)
- `data/grades.csv` — one row per compound × outcome.
- `data/legal_status.csv` — one row per compound × region.
- `data/citations.csv` — the DOI provenance table, joined back to the source text.
- `data/cosmetic_claims.csv` — permitted and forbidden claim wordings per cosmetic ingredient.
- `data/identifiers.csv` — chemical identifiers with confidence and provenance.

**Parquet mirrors** — `data/parquet/*.parquet` for all of the above (Hugging Face auto-generates Croissant JSON-LD from these).

**Retrieval corpus**
- `data/corpus.jsonl` — one record per compound: `{slug, name, title, url, text}`, where `text` is a natural-language rendering of the identity, the per-outcome grades, the legal status and the caveats. Every record carries its `https://vallydia.com/compound/<slug>` URL so a citation resolves back to the source.

**Images** — `images/structures/<slug>.svg` (+ `.png`) and `images/MANIFEST.csv`, which carries mandatory factual `alt_text` for every image.

Full field-by-field documentation: [DATA_DICTIONARY.md](DATA_DICTIONARY.md).

## The grading scale

Two axes: **consistency of evidence × magnitude/quality of effect**.

| Grade | Meaning |
|---|---|
| **A** | Strong, consistent human evidence |
| **B** | Good human evidence, smaller or formulation-dependent effect |
| **C** | Mixed or limited human evidence |
| **D** | Weak — mechanistic or very small studies only |
| **F** | Either **untested/unproven**, or **tested and failed** — two different meanings that share a letter |
| `null` | The row is not an efficacy claim at all (safety and skin-penetration rows, for instance). Carried as null; never coerced into a letter. |

Grades are assigned **per outcome, not per compound**. `overall_grade` reflects the leading, best-supported application, graded honestly downward and never up. See [METHODOLOGY.md](METHODOLOGY.md) and [vallydia.com/methodology](https://vallydia.com/methodology).

## Chemical identifiers, and why some are blank

Identifiers are resolved against PubChem by exact name/synonym match. **A wrong identifier is worse than a blank one in an evidence dataset**, so the rule is: no confident, unambiguous match → blank field and `identifier_confidence: none`. The 21 blanks are blends, stacks, multi-component biologics and proprietary analogs that have no single structure to point at. Where an ambiguity is real, it is recorded rather than resolved by guesswork — see `entity_note` in `identifiers.csv` (GHK-Cu is the live example: PubChem's record is the free tripeptide ligand, not the copper(II) complex, and the dataset and the image alt-text both say so).

Structure images are rendered **only** from high-confidence SMILES. Molecules too large for an honest 2D depiction (large peptides, GLP-1-class analogs) get a factual data card instead of an unreadable hairball.

## Dataset creation

**Curation rationale.** Vallydia maintains an evidence-graded ingredient register because the cosmetic and research-compound market is dominated by claims that outrun their evidence. Publishing the register as open data is the most direct way to say: here is our evidence assessment — audit it.

**Source data.** Published literature synthesized by Vallydia into the compound register at [vallydia.com](https://vallydia.com). The dataset is generated from that register by [`build/generate_dataset.py`](build/generate_dataset.py) — it is not hand-written, and re-running the generator on the same source reproduces it byte-for-byte.

**Annotations.** The A–F grades and the cosmetic-claims maps are produced by Vallydia. `reviewer_status` is `unassigned` throughout: no external reviewer has signed off, and the dataset does not pretend otherwise.

## Considerations for using the data

- **Not medical advice, and not a dosing reference.** Appearance and evidence context only.
- **Grades are an assessment, not a measurement.** They encode a judgment about a literature base; reasonable experts may grade differently. The `base`, `effect` and `caveat` fields exist so you can check the reasoning rather than take the letter on faith.
- **Coverage bias.** The register covers compounds Vallydia's audience actually asks about — cosmetic actives and popular research peptides. It is not a systematic sample of chemical space.
- **Literature bias.** Grades inherit the biases of the published literature: small samples, industry-funded cosmetic trials, and publication bias toward positive findings. The `caveat` field records these where they are known.
- **Regulatory data ages.** `legal_status` and `status_note` reflect the date in `last_updated`. Verify anything regulatory against the primary source before relying on it.

## Usage

```python
import pandas as pd

compounds = pd.read_parquet("data/parquet/compounds.parquet")
grades    = pd.read_parquet("data/parquet/grades.parquet")

# Cosmetic ingredients with at least one A-graded outcome
best = grades[grades.grade == "A"].merge(
    compounds[compounds.is_cosmetic][["slug", "name"]], on="slug"
)
```

```python
from datasets import load_dataset
ds = load_dataset("vallydia/ingredient-evidence-register", "grades")
```

More in [`examples/`](examples/).

## License and attribution

**CC-BY-4.0.** You may use, remix and redistribute this data, including commercially, provided you give attribution.

> Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0.

## Citation

Cite the **concept DOI** — it always resolves to the latest version:

> Bilenko, J. (2026). *Vallydia Ingredient-Evidence Register* (Version 1.0.0) [Data set]. Vallydia. https://doi.org/10.5281/zenodo.21364453

```bibtex
@dataset{vallydia_ingredient_evidence_register,
  title     = {Vallydia Ingredient-Evidence Register},
  author    = {Bilenko, Jacob},
  year      = {2026},
  publisher = {Vallydia},
  version   = {1.0.0},
  doi       = {10.5281/zenodo.21364453},
  url       = {https://vallydia.com},
  note      = {CC-BY-4.0}
}
```

---

Maintained by [Vallydia](https://vallydia.com) · [Methodology](https://vallydia.com/methodology) · [Datasheet](datasheet.md) · [Data dictionary](DATA_DICTIONARY.md)
