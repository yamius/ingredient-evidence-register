# Publishing checklist

Status of each step is marked below. Order matters only in the Zenodo DOI loop.

---

## 1. GitHub — DONE

Published at **https://github.com/yamius/ingredient-evidence-register** (public, `main`, v1.0.0).

`register-source/` (the MDX input from the private site repo) is gitignored and was **not** pushed. Only the derived dataset and the generator are public.

## 2. ORCID — DONE

Jacob Bilenko, [0009-0009-1636-8487](https://orcid.org/0009-0009-1636-8487), recorded in `CITATION.cff` and `.zenodo.json`. Zenodo will forward the DOI to the ORCID record automatically once it is minted.

## 3. Hugging Face — mirror to `vallydia`

The dataset repo is `huggingface.co/datasets/vallydia/ingredient-evidence-register`.

```bash
pip install huggingface_hub
huggingface-cli login          # paste a write token from huggingface.co/settings/tokens
huggingface-cli upload vallydia/ingredient-evidence-register . . --repo-type=dataset
```

The YAML frontmatter at the top of `README.md` is what makes HF render this as a proper dataset card with a data viewer; Croissant JSON-LD is auto-generated from the Parquet files. Nothing else to configure.

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
