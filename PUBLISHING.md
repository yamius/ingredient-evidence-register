# Publishing checklist

The build is done and committed. These steps need accounts and toggles, so they are yours.
Order matters only in step 5 (the Zenodo DOI loop) — the rest are independent.

Throughout, `<org>` is the GitHub owner you publish under (`yamius`, or a Vallydia org).

---

## 1. GitHub

Create an **empty public** repo named `ingredient-evidence-register`, then push:

```bash
git init
git add .
git commit -m "v1.0.0 — initial dataset release"
git branch -M main
git remote add origin https://github.com/<org>/ingredient-evidence-register.git
git push -u origin main
```

**A repo under a Vallydia org reads as more credible than one under a personal account** — and it is easier to hand over later. Worth the two minutes if you plan to keep this alive.

Note: `register-source/` (the MDX input pulled from the private site repo) is gitignored and is **not** pushed. Only the derived dataset and the generator go public.

## 2. ORCID (recommended, ~5 minutes)

Register at [orcid.org](https://orcid.org/register). Then add your iD to:
- `CITATION.cff` → uncomment the `orcid:` line under `authors`.
- `.zenodo.json` → add `"orcid": "0000-0000-0000-0000"` to the creator object.

Why bother: it makes the authorship citable and machine-resolvable, and Zenodo will auto-forward the DOI to your ORCID record. It is the difference between a dataset by "someone" and a dataset by a specific, verifiable person.

## 3. Hugging Face

Create an account, then a **dataset** repo:

```bash
pip install huggingface_hub
huggingface-cli login
huggingface-cli upload <hf-username>/ingredient-evidence-register . . --repo-type=dataset
```

The YAML frontmatter at the top of `README.md` is what makes HF render this as a proper dataset card with a data viewer; Croissant JSON-LD is auto-generated from the Parquet files. Nothing else to configure.

Afterwards, replace `<hf-username>` in the README usage example with the real one.

## 4. Kaggle

Create an account and an API token (`~/.kaggle/kaggle.json`), then:

```bash
pip install kaggle
# edit dataset-metadata.json: replace <kaggle-username> in the "id" field
kaggle datasets create -p . -r zip
```

The schemas in `dataset-metadata.json` already list every field in order, which is what Kaggle requires.

## 5. Zenodo — the DOI loop

**Order matters here.** The repo must be toggled on in Zenodo *before* you cut the release, or the release will not be archived.

1. Sign in to [zenodo.org](https://zenodo.org) with GitHub and authorize it.
2. Go to **Settings → GitHub**, find `ingredient-evidence-register`, and flip the toggle **ON**.
3. Only now, cut the release on GitHub:
   ```bash
   git tag -a v1.0.0 -m "Vallydia Ingredient-Evidence Register v1.0.0"
   git push origin v1.0.0
   ```
   Then publish it as a **Release** in the GitHub UI (a tag alone does not trigger Zenodo).
4. Zenodo archives the release and mints two DOIs: a **concept DOI** (always resolves to the latest version — this is the one to cite in general) and a **version DOI** (this exact release).
5. Write the DOI back into the repo:
   - `CITATION.cff` → uncomment the `identifiers:` block and fill in the concept DOI.
   - `README.md` → the Citation section, and add a DOI badge if you want one.
   Commit. (This commit is not part of the archived release — that is fine and normal.)

Unsure about any of it? Rehearse on [sandbox.zenodo.org](https://sandbox.zenodo.org) first; it is the same flow with throwaway DOIs.

`.zenodo.json` drives the record metadata. Deliberately, it contains **no `license` field** — Zenodo reads the license from the `LICENSE` file, and specifying it in both places is how records end up mislabelled. Both `.zenodo.json` and `CITATION.cff` are kept: Zenodo prefers `.zenodo.json` for the record, while `CITATION.cff` powers GitHub's "Cite this repository" button.

---

## After publishing

- Add the Zenodo DOI badge to the README.
- The CC-BY-4.0 attribution requirement is the backlink mechanism: every downstream use owes a credit line pointing at vallydia.com. That is the whole point of the license choice — do not switch it to CC0 later.

## Not yet built (second pass)

The extended targets from the spec — the read-only API, the PyPI and npm loader packages, OpenAlex/Semantic Scholar citation enrichment, the auto-rebuild GitHub Action, and evidence-grade cards — are **not** in v1.0.0. None of them blocks the core dataset or the DOI. They ship in the next pass.
