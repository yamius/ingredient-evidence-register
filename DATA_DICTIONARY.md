# Data dictionary

Every file, every field, its type, its nullability and what it means.
The join key everywhere is **`slug`** (lowercase, hyphenated, unique, stable — e.g. `ghk-cu`).

Grades are `A` | `B` | `C` | `D` | `F` | **null**. Null is not missing data: it means the row is not an
efficacy claim (a safety or skin-penetration row, for instance). See [METHODOLOGY.md](METHODOLOGY.md).

---

## `data/compounds.jsonl` / `data/compounds.json` — canonical, lossless

> **Naming.** A grade is an assessment of a *substance*, so the graded `name` is always a
> nonproprietary one — the INCI name for a cosmetic ingredient, the INN for a drug. Trademarks
> live in `trade_names` and carry no grade. The register's own display form (e.g.
> `Matrixyl (Palmitoyl Pentapeptide-4)`, which titles the site page) is referential and is not
> what the dataset leads with. `build/validate_dataset.py` fails the build if a trade name
> reappears in `name`.

One JSON object per compound. 85 records.

| Field | Type | Null? | Meaning |
|---|---|---|---|
| `slug` | string | no | Unique id and join key. Matches the filename and the site URL. |
| `name` | string | no | The graded name — always nonproprietary: the INCI name for a cosmetic ingredient, the INN for a drug. Never a trademark; see `trade_names`. |
| `inci_name` | string | yes | INCI name (cosmetic ingredient glossary). Null where the compound is not a cosmetic ingredient. |
| `inn` | string | yes | International Nonproprietary Name (WHO), for drug substances. Null where none exists. |
| `trade_names` | string[] | no | Trademarked/supplier names for the same substance, e.g. `["Matrixyl"]`. Empty where the substance has none. Reference only — no grade is ever attached to these. |
| `title` | string | no | Page title from the register. |
| `url` | string | no | Canonical source page: `https://vallydia.com/compound/<slug>`. |
| `synonyms` | list[string] | no (may be empty) | Alternative names, including INCI names (prefixed `INCI:`). |
| `compound_class` | string | no | One of the classes present in the register: `peptide`, `small_molecule`, `protein`, `blend`, `polysaccharide`. Collected at build time, not hardcoded — new classes flow through. |
| `overall_grade` | string | yes | A–F summary of the **leading** application. Never rounded up. |
| `grades_by_outcome` | list[object] | no (may be empty) | The real grading data — see `grades.csv` below for the object fields. |
| `legal_status` | list[object] | no (may be empty) | `{region, status, note}` — see `legal_status.csv`. |
| `wada` | object | no | `{prohibited: bool, note: string\|null}` — WADA prohibited-list status. |
| `function_tags` | list[string] | no (may be empty) | Free-text functional tags, e.g. `antioxidant`, `skin appearance (cosmetic)`. |
| `related` | list[string] | no (may be empty) | Slugs of related compounds (join back to `slug`). |
| `reviewer_status` | string | no | Currently `unassigned` on every compound — no external reviewer has signed off. Carried as-is. |
| `sources` | list[string] | no (may be empty) | Free-text citations. **`citation_ids[].source` is an index into this list.** |
| `citation_ids` | list[object] | no (may be empty) | DOI-verified provenance — see `citations.csv`. |
| `cosmetic_claims` | object | yes | `{allowed: list[string], forbidden: list[string]}`. Present when `is_cosmetic` is true. |
| `is_cosmetic` | bool | no | Whether the compound is a lawful cosmetic ingredient in at least one form. |
| `sale_note` | string | yes | The register's note on commercial form and framing. Carried verbatim. |
| `status_note` | string | yes | Note on a regulatory status in flux. |
| `honest_note` | string | yes | The register's explicit caveat where the honest answer is uncomfortable. Present on 9 compounds. |
| `last_updated` | string (`YYYY-MM-DD`) | yes | When the register entry was last revised. Regulatory fields age — check this. |
| `in_brief` | string | yes | Long-form plain-language summary. |
| `body_sections` | object | no | The Markdown body split by H2 heading: `{heading: text}`. Common keys: `Identity`, `Development & history`, `Mechanism (as proposed)`, `Related reading`. Internal site links are flattened to plain text. |
| `body_markdown` | string | no | The raw Markdown body, unmodified. Nothing is lost. |
| `structure_image` | string | yes | Path to the structure image, or null where none was rendered. Joins to `images/MANIFEST.csv`. |
| `grade_card_image` | string | yes | Path to the evidence-grade card. Null in v1.0.0 (grade cards ship in a later version). |

Unrecognized frontmatter fields are **carried through** into the record and reported by the build, never silently dropped.

**Example record** (abridged):

```json
{
  "slug": "ghk-cu",
  "name": "GHK-Cu (Copper Tripeptide-1)",
  "url": "https://vallydia.com/compound/ghk-cu",
  "compound_class": "peptide",
  "overall_grade": "B",
  "grades_by_outcome": [
    {
      "outcome": "Topical: appearance of photoaged skin (fine lines, firmness, density)",
      "grade": "B",
      "base": "Small human RCTs — Leyden 2002 (n=71), eye-cream (n=41), Badenhorst 2016",
      "effect": "Measurable improvement",
      "caveat": "Small samples; effect generally smaller than prescription retinoids; highly formulation-dependent"
    },
    {
      "outcome": "Skin penetration of intact-skin serums",
      "grade": null,
      "base": "Permeation study (Li 2015)",
      "effect": "Near-zero through intact stratum corneum",
      "caveat": "Key limitation; most benefit shown with enhanced delivery"
    }
  ],
  "wada": { "prohibited": false, "note": null },
  "is_cosmetic": true,
  "reviewer_status": "unassigned"
}
```

---

## `data/compounds.csv` — flat table

One row per compound (85). List fields are `|`-joined.

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `slug` | string | no | Join key. |
| `name` | string | no | The graded name — always nonproprietary: the INCI name for a cosmetic ingredient, the INN for a drug. Never a trademark; see `trade_names`. |
| `inci_name` | string | no | INCI name, or empty. |
| `inn` | string | no | INN, or empty. |
| `trade_names` | string | no | Pipe-joined trade names, or empty. |
| `compound_class` | string | no | See above. |
| `overall_grade` | string | yes | Empty cell = no overall grade. |
| `is_cosmetic` | bool | no | `True` / `False`. |
| `wada_prohibited` | bool | no | `True` / `False`. |
| `n_outcomes` | int | no | Number of `grades_by_outcome` rows. |
| `best_outcome_grade` | string | yes | Best non-null outcome grade (A > B > C > D > F). Empty if every outcome is null. |
| `worst_outcome_grade` | string | yes | Worst non-null outcome grade. **Nulls are ignored, not treated as F.** |
| `synonyms` | string | no | `\|`-joined. |
| `function_tags` | string | no | `\|`-joined. |
| `related` | string | no | `\|`-joined slugs. |
| `regions` | string | no | `\|`-joined regions from `legal_status`. |
| `n_sources` | int | no | Count of cited sources. |
| `n_doi_verified` | int | no | Count of `citation_ids` carrying a DOI. `0` means no DOI-verified citation **yet** — a known, reported gap, not an error. |
| `last_updated` | string | yes | `YYYY-MM-DD`. |
| `in_brief` | string | yes | Summary text. |
| `url` | string | no | Canonical vallydia.com page. |
| `structure_image` | string | yes | Path, or empty. |
| `grade_card_image` | string | yes | Empty in v1.0.0. |

---

## `data/grades.csv` — one row per compound × outcome (456 rows)

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `slug` | string | no | Join key. |
| `name` | string | no | Denormalized. Nonproprietary (INCI/INN) — never a trademark. |
| `compound_class` | string | no | Denormalized for convenience. |
| `outcome` | string | no | The specific claim being graded, e.g. *"Hair growth / density"*. |
| `grade` | string | **yes** | A–F, or **empty** for the 97 rows that are not efficacy claims (safety, penetration). Do not coerce empty to `F`. |
| `base` | string | yes | The evidence base the grade rests on (study types, sample sizes, names). |
| `effect` | string | yes | What the evidence reports. |
| `caveat` | string | yes | Why the grade is not higher. **The most load-bearing text field in the dataset.** |

---

## `data/legal_status.csv` — one row per compound × region (132 rows)

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `slug` | string | no | Join key. |
| `name` | string | no | Denormalized. Nonproprietary (INCI/INN) — never a trademark. |
| `region` | string | no | `INT`, `EU`, `US`, `UK`. |
| `status` | string | yes | Short status, e.g. *"See note"*, *"Not approved"*. |
| `note` | string | yes | The detail — often the substance of the entry. Long free text. |

Regulatory status ages. Always read `last_updated` and `status_note` from `compounds.csv` alongside this table.

---

## `data/citations.csv` — DOI provenance (117 rows across 50 compounds)

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `slug` | string | no | Join key. |
| `name` | string | no | Denormalized. Nonproprietary (INCI/INN) — never a trademark. |
| `source_index` | int | no | **Index into that compound's `sources[]` list** (0-based). The build fails if it does not join. |
| `source_text` | string | no | The free-text citation from `sources[source_index]`, resolved for you. |
| `doi` | string | no | The DOI, e.g. `10.3390/ijms19071987`. |
| `resolved` | string | yes | Resolution confidence, e.g. `high` — the DOI and title were checked and matched. |
| `verified_title` | string | yes | The title as returned by the resolver, not as typed by us. |

---

## `data/cosmetic_claims.csv` — claim map (246 rows across 21 cosmetic compounds)

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `slug` | string | no | Join key. Only `is_cosmetic` compounds appear. |
| `name` | string | no | Denormalized. Nonproprietary (INCI/INN) — never a trademark. |
| `claim_type` | string | no | `allowed` or `forbidden`. |
| `claim_text` | string | no | The claim wording. `allowed` = permissible cosmetic (appearance/feel) wording. `forbidden` = wording that asserts a physiological/therapeutic action and must **not** be used. |

---

## `data/identifiers.csv` — chemical identifiers (85 rows; 64 confident, 21 intentionally blank)

| Column | Type | Null? | Meaning |
|---|---|---|---|
| `slug` | string | no | Join key. |
| `name` | string | no | Display name. |
| `compound_class` | string | no | See above. |
| `cas` | string | yes | CAS registry number, from PubChem's curated CAS heading by depositor consensus. **Blank where depositors disagree without a clear consensus** — never guessed. |
| `pubchem_cid` | string | yes | PubChem Compound ID. |
| `inchikey` | string | yes | InChIKey — the best cross-database join key (PubChem, ChEMBL, Wikidata). |
| `inchi` | string | yes | Full InChI string. |
| `smiles` | string | yes | Canonical SMILES. **Only `high`-confidence SMILES are rendered as structure images.** |
| `unii` | string | yes | FDA UNII, from PubChem's UNII heading; blank if ambiguous. |
| `chembl_id` | string | yes | ChEMBL id where PubChem carries one. |
| `drugbank_id` | string | yes | DrugBank id where PubChem carries one. |
| `identifier_source` | string | yes | Provenance, e.g. `PubChem exact-name match (niacinamide)`, `MDX-provided`, `not-a-single-entity`, `unresolved`. |
| `identifier_confidence` | enum | no | `high` \| `medium` \| `low` \| `none`. `high` = one unambiguous CID **and** a canonical SMILES. |
| `entity_note` | string | yes | **Read this before trusting a structure.** Set when the resolved PubChem record is a real but *distinct* entity from the register's compound. Live example: `ghk-cu` — PubChem's record is the free tripeptide ligand, with no copper in the structure, while the register compound is the copper(II) complex. |

**Why 21 rows are blank:** blends, stacks, multi-component biologics and proprietary analogs have no single chemical structure to identify. A blank is honest; a fabricated CAS or SMILES would corrupt the dataset and propagate into the images. See METHODOLOGY.md §6.

---

## `data/corpus.jsonl` — retrieval / RAG text layer (85 records)

| Field | Type | Meaning |
|---|---|---|
| `slug` | string | Join key. |
| `name` | string | Display name. |
| `title` | string | Page title. |
| `url` | string | `https://vallydia.com/compound/<slug>` — present on **every** record so a retrieved passage always resolves back to an attributable source. |
| `text` | string | A natural-language rendering of identity, `in_brief`, the per-outcome grades in prose, legal status, WADA status, cosmetic-claims, caveats and the provenance count. Assembled only from fields that exist in the register — no dosing or commerce language is introduced. |

---

## `images/MANIFEST.csv` — image layer (85 rows: 42 structures, 22 data cards, 21 no-image)

| Column | Type | Meaning |
|---|---|---|
| `slug` | string | Join key. |
| `image_type` | enum | `structure` (2D depiction) \| `sequence_card` (large molecule — data card, not a 2D drawing) \| `none` (no confident structure; no image emitted). |
| `path` | string | Repo-relative path, or empty for `none`. |
| `format` | string | `svg` (a matching `.png` accompanies each 2D structure). |
| `alt_text` | string | **Mandatory, factual** description of what the image actually depicts — including the `entity_note` caveat where one applies. |
| `license` | string | `CC-BY-4.0`. |
| `source` | string | Attribution and rendering provenance. |
| `note` | string | Why a card was used instead of a structure, or why no image exists. |

---

## `data/parquet/*.parquet`

Parquet mirrors of `compounds`, `grades`, `legal_status`, `citations`, `cosmetic_claims` and `identifiers`, with the same columns as the CSVs above. Load with `pandas.read_parquet` or the Hugging Face `datasets` library; Hugging Face auto-generates Croissant JSON-LD from them.

## `checksums.sha256`

SHA-256 of every file under `data/` and `images/`. Regenerated by `build/generate_dataset.py`. Verify with `sha256sum -c checksums.sha256`.
