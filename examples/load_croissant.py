"""Load the register as an ML Croissant dataset.

    pip install mlcroissant
    python examples/load_croissant.py

Hugging Face auto-generates Croissant JSON-LD from the Parquet files, so the dataset is
consumable by any Croissant-aware pipeline without a bespoke loader.

Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0.
"""

import mlcroissant as mlc

REPO = "vallydia/ingredient-evidence-register"
CROISSANT_URL = f"https://huggingface.co/api/datasets/{REPO}/croissant"

dataset = mlc.Dataset(CROISSANT_URL)

print(dataset.metadata.name)
print(dataset.metadata.description[:200], "…")
print(f"license: {dataset.metadata.license}")

print("\nrecord sets:")
for rs in dataset.metadata.record_sets:
    print(f"  - {rs.uuid}")

for i, record in enumerate(dataset.records(record_set="grades")):
    print(record)
    if i >= 2:
        break
