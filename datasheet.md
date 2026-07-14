# Datasheet — Vallydia Ingredient-Evidence Register

Following *Datasheets for Datasets* (Gebru et al., 2021). Answers are specific and honest,
including where the honest answer is unflattering.

---

## Motivation

**For what purpose was the dataset created?**
To publish, as open and machine-readable data, Vallydia's evidence assessment of the cosmetic and research ingredients its audience actually asks about. The cosmetic and research-compound market runs on claims that consistently outrun their evidence; the register exists to grade those claims honestly, outcome by outcome, and this dataset exists so that the grading can be audited, reused and cited rather than merely read.

A secondary and explicit purpose: making the evidence data ingestible by LLM and RAG pipelines, so that machine-generated answers about these ingredients can be grounded in a sourced, graded, attributable reference instead of marketing copy.

**Who created the dataset and who funded it?**
Vallydia (Yakiv Bilenko). Self-funded. No external sponsor, and no ingredient supplier or brand paid for, reviewed, or influenced any grade.

---

## Composition

**What do the instances represent?**
Chemical compounds and ingredient blends — 85 of them: 53 peptides, 23 small molecules, 5 blends, 3 proteins, 1 polysaccharide. Each instance is a compound with its evidence grades, citations, legal status, cosmetic-claims map and chemical identifiers.

**How many instances are there?**
85 compounds; 456 graded outcome rows; 132 legal-status rows; 373 cited sources of which 117 are DOI-verified; 246 cosmetic-claim rows across 21 cosmetic ingredients; 85 identifier rows (64 confidently resolved); 64 images.

**Is it a sample or the complete set?**
It is the **complete** Vallydia register as of the release date — but the register itself is not a systematic sample of chemical space. It is a demand-driven selection: compounds people search for and ask about. Cosmetic actives and popular "research peptides" are over-represented relative to their scientific importance. Do not treat it as an unbiased sample of the ingredient universe.

**What data does each instance consist of?**
Structured frontmatter fields (see [DATA_DICTIONARY.md](DATA_DICTIONARY.md)) plus the parsed and raw Markdown body text of the register entry.

**Is there a label or target?**
Yes — the A–F evidence grade, per outcome. This is the dataset's central annotation. `overall_grade` is a derived summary.

**Is any information missing?**
Yes, and deliberately:
- **97 of 456 grade rows are null.** These are not missing values: the rows are not efficacy claims (safety, skin-penetration). They are carried as null and must not be coerced to `F`.
- **35 of 85 compounds have no DOI-verified citation** yet. They have free-text sources; DOI backfill is incomplete. The build reports these by slug.
- **21 of 85 compounds have no chemical identifiers.** Blends, stacks, multi-component biologics and proprietary analogs have no single structure. Blank is the honest answer; a guessed CAS or SMILES would be worse than nothing.
- **Grade cards** (`grade_card_image`) are not populated in v1.0.0.

**Are relationships between instances made explicit?**
Yes — the `related` field lists slugs of related compounds, forming a navigable graph.

**Are there errors, sources of noise, or redundancies?**
- The free-text `sources` entries are human-typed and vary in citation style.
- `legal_status.note` is long-form free text, not a normalized regulatory code.
- Regulatory status **ages**: several entries describe statuses in flux (see `status_note`). `last_updated` is the field to check.
- Where PubChem's record is a related-but-distinct entity from the register's compound, this is flagged in `entity_note` rather than silently accepted — GHK-Cu is the live case (PubChem's record is the free tripeptide ligand, not the copper(II) complex).

**Does the dataset contain confidential, offensive, or sensitive data?**
No. No personal data, no PII, no credentials, no internal URLs. All content is public-facing reference text.

**Does it relate to people?**
No.

---

## Collection process

**How was the data acquired?**
Vallydia's editorial process: reading the published literature for each compound, extracting per-outcome findings, and grading them on consistency of evidence × magnitude/quality of effect. The result is written into a versioned MDX register (`content/compounds/*.mdx`) in Vallydia's site repository.

**Who was involved?**
Vallydia's editorial team. `reviewer_status` is `unassigned` on every compound: **no external expert has reviewed or certified these grades.** The dataset states this in the data itself rather than implying a review that did not happen.

**Over what timeframe was the data collected?**
The register has been built and revised on a rolling basis; each entry carries its own `last_updated` date.

**Were ethical review processes conducted?**
Not applicable — no human subjects, no personal data. The relevant integrity constraint is a scope firewall, not an IRB: see Uses below.

---

## Preprocessing / cleaning / labeling

**Was any preprocessing done?**
Yes, and all of it is reproducible from [`build/`](build/):
1. `enrich_identifiers.py` resolves chemical identifiers against PubChem, recording confidence and provenance and refusing to guess.
2. `generate_images.py` renders 2D structures with RDKit from high-confidence SMILES only, and factual data cards (not 2D hairballs) for molecules too large to depict honestly.
3. `generate_dataset.py` parses the MDX, validates it, and emits every artifact plus `checksums.sha256`.

The Markdown body is split by H2 heading into `body_sections`; internal site links are flattened to plain text for the text layer.

**Was the raw data saved?**
Yes — `body_markdown` preserves the unmodified Markdown body, so the derived text layer is lossless with respect to the source. The MDX source itself lives in Vallydia's private site repository and is not vendored here; the generator reads it from a path you supply.

**Is the preprocessing software available?**
Yes, in this repo, with pinned dependencies. The build is deterministic: running it twice on the same source yields byte-identical output.

---

## Uses

**What has the dataset been used for?**
Powering the compound register at [vallydia.com](https://vallydia.com), and — as of this release — publication as an open dataset for reuse, citation and RAG grounding.

**What other tasks could it be used for?**
Evidence-grade classification; evidence-grounded question answering; **regulatory claim checking** (the `allowed`/`forbidden` claim map is directly usable for automated compliance screening of cosmetic marketing copy); cheminformatics cross-linking via InChIKey/CID; retrieval-augmented generation.

**Is there anything about the composition that could result in unfair treatment or harm?**
Two things a user must understand:

1. **The grades are an assessment, not a measurement.** They encode a defensible judgment about a literature base. Reasonable experts may grade differently. The `base`, `effect` and `caveat` fields are published so the reasoning can be checked rather than trusted on faith. They are **not** third-party certification.
2. **The grades inherit the biases of the literature they summarize** — small samples, industry-funded cosmetic trials, publication bias toward positive results, and thin evidence for compounds that are nonetheless widely sold. A `B` reflects the best available evidence, not proof.

**Are there tasks for which the dataset should NOT be used?**

- **Not for medical, dosing, or administration guidance.** The dataset contains no dosing, reconstitution, or administration information anywhere, by design, and none must be inferred from it.
- **Not as a purchasing or sourcing guide.** Research and injectable compounds (GLP-1 analogs, BPC-157, TB-500, melanotan and others) are included as **reference entries with their honest grades and legal status carried through verbatim**. Their inclusion is not an endorsement and not a signal of availability; several grade `F`, and their `legal_status` says plainly where they are unapproved.
- **Not as a regulatory source of record.** `legal_status` is a summary that ages. Verify against the primary regulator before relying on it.

---

## Distribution

**How is it distributed?**
GitHub (this repo), Hugging Face (dataset card + Parquet + auto-generated Croissant), Kaggle, and Zenodo (archived with a DOI).

**Under what license?**
**CC-BY-4.0.** Free to use, remix and redistribute, including commercially, with attribution:

> Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0.

**Any IP or restrictions?**
No third-party IP restrictions. The cited literature is referenced, never reproduced.

---

## Maintenance

**Who maintains it?**
Vallydia. Contact via [vallydia.com](https://vallydia.com).

**Will it be updated?**
Yes — as the register grows and as evidence, regulatory status and DOI backfill change. Priorities for the next version: closing the DOI gap on the 35 compounds without verified citations, and evidence-grade cards.

**How will updates be communicated?**
Through `CHANGELOG.md`, versioned GitHub releases, and new Zenodo DOI versions (the concept DOI always resolves to the latest).

**Will older versions be supported?**
Yes — every GitHub release is permanently archived on Zenodo with its own version DOI.

**How can others contribute or correct an error?**
Open a GitHub issue. Corrections to grades or citations are welcome and will be evaluated against the sources; the grading rationale is published precisely so that it can be argued with.
