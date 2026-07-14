#!/usr/bin/env python3
"""
Chemical-identifier enrichment for the Vallydia Ingredient-Evidence Register.

Resolves each compound to public chemical identifiers (CAS, PubChem CID, InChI,
InChIKey, SMILES, UNII) via PubChem PUG-REST, and writes data/identifiers.csv.

The governing rule of this script is: NEVER FABRICATE AN IDENTIFIER.
A blank identifier is honest; a wrong one silently corrupts an evidence dataset and
would propagate into the structure images (a wrong molecule rendered as fact). So:

  * Only exact name/synonym matches against PubChem are accepted.
  * A match is 'high' confidence only when the compound is a plausible single
    chemical entity (not a blend/protein/stack) AND PubChem returned exactly one CID
    for an exact-name lookup AND the returned record carries a canonical SMILES.
  * Blends, stacks, multi-component products, large proteins and proprietary analogs
    resolve to 'none' by design — they have no single structure to point at.
  * Every non-blank row carries identifier_source and identifier_confidence.

Only 'high'-confidence rows are eligible for structure rendering (see generate_images.py).

Results are cached in build/.cache/pubchem/ so re-runs are offline and deterministic.

Usage:
    python build/enrich_identifiers.py [--source register-source/compounds] [--offline]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import frontmatter

PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
USER_AGENT = "vallydia-ingredient-evidence-register/1.0 (dataset build; +https://vallydia.com)"
CAS_RE = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")

# Classes that cannot resolve to one structure. Marked 'none' without querying —
# guessing a CID for a blend is exactly the failure mode this script exists to prevent.
UNRESOLVABLE_CLASSES = {"blend"}

# Compounds that are biologics / large proteins / multi-component by nature: we do not
# assert a single small-molecule structure for them even if PubChem happens to have a record.
NO_STRUCTURE_SLUGS = {
    "exosomes", "wolverine-stack", "cjc-1295-ipamorelin", "dasatinib-quercetin",
    "cerebrolysin", "follistatin", "bimagrumab", "ceramides", "pdrn", "thymalin",
    "hyaluronic-acid",
}

FIELDS = [
    "slug", "name", "compound_class", "cas", "pubchem_cid", "inchikey", "inchi",
    "smiles", "unii", "chembl_id", "drugbank_id", "identifier_source", "identifier_confidence",
    "entity_note",
]

# Metals that appear in the register's coordination complexes (copper peptides).
METAL_RE = re.compile(r"\[(Cu|Zn|Mg|Mn|Fe)[^\]]*\]")


def entity_mismatch(name: str, synonyms: list[str], smiles: str) -> str:
    """Detect when PubChem's record is a different chemical entity than the register's compound.

    The live case: 'GHK-Cu (Copper Tripeptide-1)' resolves to CID 73587, which is the FREE
    tripeptide GHK — the ligand — with no copper in the structure. The identifier is real and
    correct for what it names, but it is not the copper(II) complex. Rather than silently
    labelling a metal-free peptide as the complex (or throwing the useful data away), we record
    exactly what the resolved record depicts, and the image layer labels the image accordingly.
    """
    hay = (name + " " + " ".join(synonyms)).lower()
    claims_metal = bool(re.search(r"\bcopper\b|-cu\b|\bcu\(ii\)|\bzinc\b", hay))
    if claims_metal and smiles and not METAL_RE.search(smiles):
        return ("PubChem record is the free peptide ligand — the coordinated metal ion is NOT "
                "part of this structure; the register compound is the metal complex")
    return ""


def cache_path(root: Path, key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)[:120]
    return root / "build" / ".cache" / "pubchem" / f"{safe}.json"


def fetch(url: str, root: Path, key: str, offline: bool) -> dict | None:
    cp = cache_path(root, key)
    if cp.exists():
        raw = cp.read_text(encoding="utf-8")
        return json.loads(raw) if raw.strip() else None
    if offline:
        return None
    cp.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:          # no match — cache the negative, it is a real answer
            cp.write_text("", encoding="utf-8")
            time.sleep(0.25)
            return None
        print(f"  ! HTTP {e.code} for {key}", file=sys.stderr)
        return None
    except Exception as e:                                   # network flake: degrade, don't guess
        print(f"  ! {type(e).__name__} for {key}: {e}", file=sys.stderr)
        return None
    cp.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.25)               # PubChem asks for <= 5 requests/second; stay well under
    return data


def pubchem_by_name(name: str, root: Path, offline: bool) -> list[int]:
    q = urllib.parse.quote(name, safe="")
    data = fetch(f"{PUBCHEM}/compound/name/{q}/cids/JSON", root, f"cids_{name}", offline)
    if not data:
        return []
    return list(data.get("IdentifierList", {}).get("CID", []))


def pubchem_props(cid: int, root: Path, offline: bool) -> dict:
    props = "SMILES,ConnectivitySMILES,InChI,InChIKey,MolecularFormula,MolecularWeight,IUPACName"
    data = fetch(f"{PUBCHEM}/compound/cid/{cid}/property/{props}/JSON", root, f"props_{cid}", offline)
    if not data:
        return {}
    rows = data.get("PropertyTable", {}).get("Properties", [])
    return rows[0] if rows else {}


def pubchem_synonyms(cid: int, root: Path, offline: bool) -> list[str]:
    data = fetch(f"{PUBCHEM}/compound/cid/{cid}/synonyms/JSON", root, f"syn_{cid}", offline)
    if not data:
        return []
    info = data.get("InformationList", {}).get("Information", [])
    return info[0].get("Synonym", []) if info else []


def pug_view_values(cid: int, heading: str, root: Path, offline: bool) -> list[str]:
    """Pull an authoritative identifier heading (CAS, UNII) from PubChem PUG-View.

    The synonym list is NOT a safe source for these: it mixes in registry numbers of
    salts, isomers and related mixtures (e.g. tranexamic acid's synonym list carries the
    cis/trans-mixture CAS alongside the canonical one). PUG-View returns the depositor-
    curated values under the heading, and we only accept a unique one.
    """
    url = (f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
           f"?heading={urllib.parse.quote(heading)}")
    data = fetch(url, root, f"view_{heading}_{cid}", offline)
    if not data:
        return []
    values: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for info in node.get("Information", []) or []:
                for sv in (info.get("Value", {}) or {}).get("StringWithMarkup", []) or []:
                    text = str(sv.get("String", "")).strip()
                    if text:
                        values.append(text)
            for section in node.get("Section", []) or []:
                walk(section)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data.get("Record", {}))
    return values


def unique_cas(cid: int, root: Path, offline: bool) -> str:
    """The consensus CAS for a CID, or blank.

    PUG-View's CAS heading lists every depositor-supplied registry number, which for many
    compounds includes salts, isomers and mixtures alongside the canonical one. We take the
    number the depositors agree on most often, and return blank on a tie rather than
    picking arbitrarily — an ambiguous CAS is left for a human, never guessed.
    """
    found = [m.group(1) for v in pug_view_values(cid, "CAS", root, offline)
             if (m := CAS_RE.fullmatch(v.strip()))]
    if not found:
        return ""
    counts = Counter(found)
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return ""
    return ranked[0][0]


def unique_unii(cid: int, root: Path, offline: bool) -> str:
    found = {v.strip() for v in pug_view_values(cid, "UNII", root, offline)
             if re.fullmatch(r"[A-Z0-9]{10}", v.strip())}
    return found.pop() if len(found) == 1 else ""


def pick_chembl(synonyms: list[str]) -> str:
    for s in synonyms:
        if s.strip().upper().startswith("CHEMBL"):
            return s.strip().upper()
    return ""


def pick_drugbank(synonyms: list[str]) -> str:
    for s in synonyms:
        if re.fullmatch(r"DB\d{5}", s.strip()):
            return s.strip()
    return ""


def seed_from_mdx(fm: dict, body: str) -> dict:
    """Pick up identifiers already present in the register (CAS mentions, explicit block)."""
    seeded = {}
    block = fm.get("identifiers") or {}
    if isinstance(block, dict):
        for k in ("cas", "pubchem_cid", "inchikey", "inchi", "smiles", "unii", "chembl_id", "drugbank_id"):
            if block.get(k):
                seeded[k] = str(block[k])
    if "cas" not in seeded:
        hay = " ".join(str(s) for s in (fm.get("synonyms") or [])) + " " + body[:4000]
        m = CAS_RE.search(hay)
        if m:
            seeded["cas"] = m.group(1)
    return seeded


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(root / "register-source" / "compounds"))
    ap.add_argument("--out", default=str(root / "data" / "identifiers.csv"))
    ap.add_argument("--offline", action="store_true", help="use only the local cache; never call PubChem")
    args = ap.parse_args()

    files = sorted(Path(args.source).glob("*.mdx"))
    if not files:
        print(f"ERROR: no .mdx in {args.source}", file=sys.stderr)
        return 2

    rows: list[dict] = []
    for path in files:
        post = frontmatter.load(path, encoding="utf-8")
        fm = dict(post.metadata)
        slug = fm.get("slug", path.stem)
        name = fm.get("name", slug)
        cls = fm.get("compound_class", "")
        synonyms = [str(s) for s in (fm.get("synonyms") or [])]

        row = {f: "" for f in FIELDS}
        row.update({"slug": slug, "name": name, "compound_class": cls,
                    "identifier_confidence": "none", "identifier_source": ""})

        seeded = seed_from_mdx(fm, post.content)
        row.update(seeded)
        if seeded:
            row["identifier_source"] = "MDX-provided"
            row["identifier_confidence"] = "medium"

        structural_dead_end = cls in UNRESOLVABLE_CLASSES or slug in NO_STRUCTURE_SLUGS
        if structural_dead_end:
            # Honest blank: no single chemical entity to identify.
            row["identifier_source"] = row["identifier_source"] or "not-a-single-entity"
            row["identifier_confidence"] = "none" if not seeded else "low"
            rows.append(row)
            print(f"{slug:28s} none  (no single chemical entity: {cls})")
            continue

        # Exact-name lookup against PubChem: the compound name, then INCI/synonyms.
        # Strip the parenthetical qualifier the register uses for display names.
        base = re.sub(r"\s*\(.*?\)\s*", " ", str(name)).strip()
        candidates = [base, str(name)] + [s.replace("INCI:", "").strip() for s in synonyms]
        cid = None
        matched_on = ""
        for cand in candidates:
            if not cand or len(cand) < 3:
                continue
            cids = pubchem_by_name(cand, root, args.offline)
            if len(cids) == 1:                    # exactly one hit = unambiguous
                cid, matched_on = cids[0], cand
                break
            if len(cids) > 1:                     # ambiguous: do not pick one, keep looking
                continue

        if cid is None:
            row["identifier_confidence"] = "none" if not seeded else "low"
            row["identifier_source"] = row["identifier_source"] or "unresolved"
            rows.append(row)
            print(f"{slug:28s} none  (no unambiguous PubChem match)")
            continue

        props = pubchem_props(cid, root, args.offline)
        syns = pubchem_synonyms(cid, root, args.offline)
        smiles = props.get("SMILES") or props.get("ConnectivitySMILES") or ""

        row["pubchem_cid"] = str(cid)
        row["smiles"] = smiles
        row["inchi"] = props.get("InChI", "")
        row["inchikey"] = props.get("InChIKey", "")
        row["cas"] = row.get("cas") or unique_cas(cid, root, args.offline)
        row["unii"] = unique_unii(cid, root, args.offline)
        row["chembl_id"] = pick_chembl(syns)
        row["drugbank_id"] = pick_drugbank(syns)
        row["identifier_source"] = f"PubChem exact-name match ({matched_on})"
        row["identifier_confidence"] = "high" if smiles else "medium"
        row["entity_note"] = entity_mismatch(str(name), synonyms, smiles)
        rows.append(row)
        flag = "  [entity note]" if row["entity_note"] else ""
        print(f"{slug:28s} {row['identifier_confidence']:6s} CID {cid}  {row['inchikey'] or '-'}{flag}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: r["slug"])
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    counts = {c: 0 for c in ("high", "medium", "low", "none")}
    for r in rows:
        counts[r["identifier_confidence"]] += 1

    print("\n" + "=" * 68)
    print("IDENTIFIER REPORT")
    print("=" * 68)
    for level in ("high", "medium", "low", "none"):
        slugs = [r["slug"] for r in rows if r["identifier_confidence"] == level]
        print(f"{level:6s}: {counts[level]:3d}  {', '.join(slugs) if slugs else '-'}")
    noted = [r for r in rows if r.get("entity_note")]
    if noted:
        print("\nentity notes (resolved record is a related but distinct entity):")
        for r in noted:
            print(f"  * {r['slug']}: {r['entity_note']}")
    print(f"\nwith SMILES : {sum(1 for r in rows if r['smiles'])}")
    print(f"with CAS    : {sum(1 for r in rows if r['cas'])}")
    print(f"with UNII   : {sum(1 for r in rows if r['unii'])}")
    print("Blank identifiers are intentional — no confident match means no identifier.")
    print("=" * 68)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
