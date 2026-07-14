"""Load the register with the Hugging Face `datasets` library.

    pip install datasets
    python examples/load_hf_datasets.py

Each config in the README's YAML frontmatter maps to one Parquet table.

Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0.
"""

from datasets import load_dataset

REPO = "<hf-username>/ingredient-evidence-register"   # set after publishing (PUBLISHING.md step 3)

# One config per table: compounds | grades | legal_status | citations | cosmetic_claims | identifiers
grades = load_dataset(REPO, "grades", split="train")
print(grades)

# Every A-graded outcome in the register, with the caveat that qualifies it.
for row in grades.filter(lambda r: r["grade"] == "A"):
    print(f"\n{row['name']} — {row['outcome']}")
    print(f"  evidence: {row['base']}")
    print(f"  caveat  : {row['caveat']}")

# The retrieval corpus, for RAG. Every record carries the source URL, so a retrieved
# passage can always be cited back to vallydia.com — which CC-BY-4.0 requires anyway.
corpus = load_dataset(
    "json",
    data_files="https://huggingface.co/datasets/" + REPO + "/resolve/main/data/corpus.jsonl",
    split="train",
)
print(f"\ncorpus: {len(corpus)} passages")
print(corpus[0]["url"])
print(corpus[0]["text"][:400], "…")
