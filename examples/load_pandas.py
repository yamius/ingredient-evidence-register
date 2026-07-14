"""Load the register with pandas and ask it something useful.

    python examples/load_pandas.py

Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0.
"""

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data" / "parquet"

compounds = pd.read_parquet(DATA / "compounds.parquet")
grades = pd.read_parquet(DATA / "grades.parquet")
claims = pd.read_parquet(DATA / "cosmetic_claims.parquet")
citations = pd.read_parquet(DATA / "citations.parquet")

print(f"{len(compounds)} compounds, {len(grades)} graded outcomes\n")

# Cosmetic ingredients ranked by their best-supported outcome.
# Note the `.dropna()`: an ungraded outcome is NOT an F — it is a row that isn't an
# efficacy claim at all (safety, skin penetration). Treating null as F would libel
# every compound that honestly reported a safety row.
rank = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
cosmetic = compounds[compounds.is_cosmetic].copy()
cosmetic["rank"] = cosmetic.best_outcome_grade.map(rank)
print("Cosmetic ingredients, best-supported outcome first:")
print(
    cosmetic.sort_values(["rank", "name"], ascending=[False, True])
    [["name", "best_outcome_grade", "worst_outcome_grade", "n_doi_verified"]]
    .head(12)
    .to_string(index=False)
)

# The honest part: what does the evidence say NOT to claim?
print("\nForbidden claim wordings for GHK-Cu (these must not appear in cosmetic copy):")
for text in claims[(claims.slug == "ghk-cu") & (claims.claim_type == "forbidden")].claim_text:
    print(f"  - {text}")

# Where the evidence base is thinnest.
ungraded = grades[grades.grade.isna() | (grades.grade == "")]
print(f"\n{len(ungraded)} outcome rows carry no grade by design (safety / penetration rows).")
print(f"{(compounds.n_doi_verified == 0).sum()} compounds have no DOI-verified citation yet.")
print(f"{citations.doi.nunique()} distinct DOIs back the graded claims.")
