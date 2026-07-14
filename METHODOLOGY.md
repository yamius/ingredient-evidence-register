# Methodology

How the Vallydia Ingredient-Evidence Register is graded, sourced and generated.
Canonical narrative version: [vallydia.com/methodology](https://vallydia.com/methodology).

## 1. The grading scale

Every grade in this dataset answers one question: **how good is the evidence that this compound does this specific thing?**

It is scored on two axes:

1. **Consistency of evidence** — do independent studies agree? Are there human trials, or only cell cultures and animals?
2. **Magnitude and quality of the effect** — is the effect measurable and meaningful, or statistically real but cosmetically trivial? Were the trials controlled, blinded, adequately powered?

| Grade | Consistency × magnitude |
|---|---|
| **A** | Strong, consistent human evidence for a meaningful effect. |
| **B** | Good human evidence, but the effect is smaller, formulation-dependent, or shown in small trials. |
| **C** | Mixed or limited human evidence. Plausible, not established. |
| **D** | Weak. Mechanistic reasoning, in-vitro work, or very small/uncontrolled studies. |
| **F** | Not supported. |
| `null` | Not an efficacy claim — the row records something else (safety profile, skin penetration). Deliberately ungraded. |

### F has two meanings

This matters and is easy to misread:

- **F = untested / unproven.** Nobody has run the study. The claim floats on mechanism and marketing.
- **F = tested and failed.** The study was run and the compound did not do the thing.

Both are `F`, because from the buyer's standpoint both mean "the evidence does not support this". The `base`, `effect` and `caveat` fields on each row tell you **which** F you are looking at. Read them.

### Grades are per outcome, not per compound

A compound can be `B` for the appearance of photoaged skin and `F` for systemic anti-aging. That is not a contradiction — it is the whole point. `grades_by_outcome` is the real data; `overall_grade` is a convenience summary of the **leading, best-supported application**, graded honestly downward and never rounded up.

`null` grades are carried through as null everywhere. `best_outcome_grade` and `worst_outcome_grade` in the flat table are computed over the non-null grades only.

## 2. Evidence provenance

Each compound carries a free-text `sources` list. Where a source has been resolved to a **DOI with a verified title**, it also appears in `citation_ids` (and in `data/citations.csv`), joined back to the source text by index.

- 373 cited sources across 85 compounds.
- 117 of them are DOI-verified, across 50 compounds.
- 35 compounds carry no DOI-verified citation yet. That gap is **reported, not hidden** — the build report lists them by slug, and `n_doi_verified` is a column you can filter on.

`resolved: high` on a citation means the DOI and the title were checked against the resolver and matched.

## 3. Reviewer status

`reviewer_status` is `unassigned` on every compound, and the dataset says so rather than quietly omitting the field. **No external expert has signed off on these grades.** They are Vallydia's own evidence assessment. Treat them as a well-documented, auditable opinion — which is precisely why `base`, `effect` and `caveat` are published alongside every grade.

## 4. Scope firewall

The register — and therefore this dataset — is an **appearance-and-evidence reference**. The following are absent by design, and the generator introduces none of them into any derived text field:

- No dosing, no reconstitution, no administration or injection protocols.
- No commerce mechanics: no prices, SKUs, offers or purchase language.
- No before/after or outcome imagery.

Research and injectable compounds (GLP-1 analogs, BPC-157, TB-500, melanotan and others) **are** included, as reference entries, with their honest grades and their `legal_status` and `sale_note` text carried through verbatim from the register. Including a compound is not endorsing it; several of them grade `F`.

The generated `corpus.jsonl` text is assembled only from fields that already exist in the register — identity, grades, legal status, claims, caveats — so the firewall holds through the derived layer, not just the source.

## 5. Cosmetic-claims maps

For each cosmetic ingredient the register records two lists:

- `allowed` — claim wordings that are permissible for a cosmetic product (appearance and feel).
- `forbidden` — wordings that are **not** permissible, because they assert a physiological or therapeutic action (e.g. "stimulates collagen synthesis", "heals", "reverses aging").

The `forbidden` list is published deliberately. It is the most useful part of the map: it shows exactly where a marketing claim crosses out of cosmetic regulation, and it is what makes this dataset directly usable for automated claim checking.

## 6. Chemical identifiers

Identifiers (`data/identifiers.csv`) are resolved against **PubChem PUG-REST** by exact name/synonym lookup.

The governing rule is **never fabricate an identifier**. A blank is honest; a wrong CAS or SMILES silently corrupts an evidence dataset and would propagate into the rendered structure images as a false statement of fact. In practice:

- A match is accepted only when an exact-name lookup returns **exactly one** CID. Ambiguous lookups are not resolved by picking one.
- `identifier_confidence: high` requires a single unambiguous CID **and** a canonical SMILES.
- Blends, stacks, multi-component biologics and proprietary analogs resolve to `none` **by design** — they have no single structure to identify.
- CAS and UNII come from PubChem's curated PUG-View headings, not from the synonym list (which mixes in registry numbers for salts, isomers and mixtures). Where depositors disagree without a clear consensus value, the field is left **blank** rather than guessed.
- `entity_note` records the case where the resolved record is a **real but distinct** entity from the register's compound. The live example is **GHK-Cu**: PubChem's record is the free tripeptide ligand (GHK), with no copper in the structure. The dataset states this, and the structure image's `alt_text` states it too, rather than labelling a metal-free peptide as the copper complex.

Every non-blank identifier carries `identifier_source` and `identifier_confidence`.

## 7. Images

Images are **generated from data and correct by construction** — never decorative, never AI-"beautified", never claims-adjacent.

- **2D structures** (`images/structures/<slug>.svg`) are rendered by RDKit from a high-confidence SMILES. A compound whose identifier confidence is below `high` gets **no image**.
- **Large molecules** (> 70 heavy atoms — large peptides, GLP-1-class analogs) are **not** drawn in 2D. At that size a 2D depiction is an unreadable hairball that misinforms. They get a factual data card: class, molecular formula, heavy-atom count, molecular weight, InChIKey, and an explicit "2D structure not shown" note.
- Every image has mandatory factual `alt_text` in `images/MANIFEST.csv`.

## 8. Reproducibility

The dataset is generated, not hand-maintained:

```bash
python -m pip install -r build/requirements.txt
python build/enrich_identifiers.py    # PubChem identifiers (cached; --offline to skip the network)
python build/generate_images.py       # RDKit structures + data cards + MANIFEST
python build/generate_dataset.py      # all data artifacts + checksums.sha256
```

The build is **deterministic and idempotent**: records are sorted by slug, JSON key order is fixed, and no timestamps are written into the artifacts. Running it twice yields byte-identical files and a clean `git diff`. The generator **fails loudly** on malformed grades or a citation index that does not join to a real source, and reports (never silently drops) any frontmatter field it does not recognize.

`checksums.sha256` covers every file in `data/` and `images/`.

## 9. Source provenance and the private-repo boundary

The generator's **input** is the register's MDX export (`content/compounds/*.mdx`) from Vallydia's site repository, which is private. That source is **not vendored into this public repo** (it is gitignored under `register-source/`); the public artifact is the derived dataset plus the generator that produced it. No private code, credentials or internal URLs are exposed.

Point the generator at your own export with `--source`.
