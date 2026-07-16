# vallydia-register

A thin Python loader for the [Vallydia Ingredient-Evidence Register](https://vallydia.com) —
an evidence-graded open dataset of cosmetic and research ingredients. Every table comes back
as a pandas DataFrame.

```bash
pip install vallydia-register
```

```python
from vallydia_register import load_compounds, load_grades, load_citations

compounds = load_compounds()          # 85 rows
grades    = load_grades()             # 456 per-outcome rows

# every A-graded outcome, with the compound it belongs to
best = grades[grades.grade == "A"].merge(compounds[["slug", "name"]], on="slug")

# citations with scholarly cross-links (OpenAlex / Semantic Scholar)
cites = load_citations(enriched=True)
```

## Loaders

| Function | Rows | Notes |
|---|---|---|
| `load_compounds()` | 85 | flat core + pipe-joined lists |
| `load_grades()` | 456 | per outcome; `grade` may be null (safety/penetration rows) |
| `load_legal_status()` | 132 | per region |
| `load_citations(enriched=False)` | 117 | DOI provenance; `enriched=True` adds OpenAlex/S2 cross-links |
| `load_cosmetic_claims()` | 246 | permitted / forbidden wordings |
| `load_identifiers()` | 85 | CAS/CID/InChIKey/SMILES with confidence; blanks are honest |

## Where the data comes from

By default the loader fetches the published parquet from GitHub raw and caches it under your
user cache dir. Options:

```python
load_compounds(source="hf")                       # Hugging Face mirror instead of GitHub
load_compounds(source="/path/to/checkout/data")   # a local checkout, fully offline
load_compounds(use_cache=False)                    # always re-fetch
```

or set `VALLYDIA_REGISTER_DATA=/path/to/data` in the environment.

## Attribution

Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0. Any use — including
in derived datasets or model training — must attribute Vallydia. Appearance/evidence reference
only; not medical advice.
