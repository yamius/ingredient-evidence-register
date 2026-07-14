#!/usr/bin/env python3
"""
Image layer for the Vallydia Ingredient-Evidence Register — §12.1 molecular structures.

Every image here is derived from data and correct by construction. Nothing is decorative,
nothing is AI-"beautified", and nothing is claims-adjacent.

Rendering rules (documented because they are the integrity contract):

  1. A structure is rendered ONLY from a SMILES whose identifier_confidence is 'high'.
     No confident identifier -> no image. A subtly-wrong molecule presented as fact would
     be a credibility failure worse than a missing picture.
  2. Small and short-peptide molecules (<= HEAVY_ATOM_LIMIT heavy atoms) are drawn as a
     clean 2D structure with RDKit.
  3. Large peptides / proteins / GLP-1-class analogs (> HEAVY_ATOM_LIMIT heavy atoms) are
     NOT drawn in 2D — at that size a 2D depiction is an unreadable hairball that misleads
     more than it informs. They get a factual sequence/schematic card instead: class,
     molecular formula, heavy-atom count, molecular weight, InChIKey, and an explicit
     "2D structure not shown" note.
  4. Compounds with no confident structure at all (blends, stacks, biologics) get no image
     and are recorded in the manifest with a reason.

Outputs: images/structures/<slug>.svg (+ .png), images/MANIFEST.csv (with mandatory alt_text).

Usage:
    python build/generate_images.py
"""

from __future__ import annotations

import argparse
import csv
import html
import sys
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, Draw, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D

RDLogger.DisableLog("rdApp.*")

# Above this heavy-atom count a 2D depiction stops being readable. GHK-Cu (~25) and the
# cosmetic peptides sit well below it; semaglutide (~350) sits far above.
HEAVY_ATOM_LIMIT = 70

SVG_W, SVG_H = 640, 480
LICENSE = "CC-BY-4.0"
SOURCE = "Vallydia Ingredient-Evidence Register (https://vallydia.com) — structure rendered with RDKit from a PubChem-resolved SMILES"

MANIFEST_FIELDS = ["slug", "image_type", "path", "format", "alt_text", "license", "source", "note"]


def render_structure(mol: Chem.Mol, path_svg: Path) -> None:
    """2D structure, transparent background, consistent style."""
    Chem.rdDepictor.Compute2DCoords(mol)
    Chem.rdDepictor.StraightenDepiction(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(SVG_W, SVG_H)
    opts = drawer.drawOptions()
    opts.clearBackground = False          # transparent — usable on light and dark pages
    opts.bondLineWidth = 2
    opts.addStereoAnnotation = True
    opts.padding = 0.08
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    path_svg.write_text(drawer.GetDrawingText(), encoding="utf-8", newline="\n")


def render_sequence_card(slug: str, name: str, cls: str, formula: str, heavy: int,
                         mw: float, inchikey: str, path_svg: Path) -> None:
    """Factual card for molecules too large to depict honestly in 2D."""
    e = html.escape
    rows = [
        ("Class", cls),
        ("Molecular formula", formula),
        ("Heavy atoms", str(heavy)),
        ("Molecular weight", f"{mw:.1f} g/mol"),
        ("InChIKey", inchikey or "—"),
    ]
    lines = "".join(
        f'<text x="40" y="{170 + i * 46}" class="k">{e(k)}</text>'
        f'<text x="270" y="{170 + i * 46}" class="v">{e(v)}</text>'
        for i, (k, v) in enumerate(rows)
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" viewBox="0 0 {SVG_W} {SVG_H}" role="img">
  <style>
    .t {{ font: 600 26px system-ui, -apple-system, "Segoe UI", sans-serif; fill: currentColor; }}
    .s {{ font: 400 15px system-ui, -apple-system, "Segoe UI", sans-serif; fill: currentColor; opacity: .65; }}
    .k {{ font: 500 16px system-ui, -apple-system, "Segoe UI", sans-serif; fill: currentColor; opacity: .6; }}
    .v {{ font: 400 16px ui-monospace, "SF Mono", Consolas, monospace; fill: currentColor; }}
    .n {{ font: 400 14px system-ui, -apple-system, "Segoe UI", sans-serif; fill: currentColor; opacity: .7; }}
    .b {{ fill: none; stroke: currentColor; stroke-opacity: .22; stroke-width: 1.5; }}
  </style>
  <rect class="b" x="12" y="12" width="{SVG_W - 24}" height="{SVG_H - 24}" rx="14"/>
  <text x="40" y="70" class="t">{e(name)}</text>
  <text x="40" y="98" class="s">{e(slug)}</text>
  <line x1="40" y1="124" x2="{SVG_W - 40}" y2="124" stroke="currentColor" stroke-opacity=".18"/>
  {lines}
  <text x="40" y="{SVG_H - 58}" class="n">Large peptide — 2D structure not shown</text>
  <text x="40" y="{SVG_H - 36}" class="n">(a 2D depiction at this size is unreadable and misleading)</text>
</svg>
"""
    path_svg.write_text(svg, encoding="utf-8", newline="\n")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--identifiers", default=str(root / "data" / "identifiers.csv"))
    ap.add_argument("--out", default=str(root / "images"))
    args = ap.parse_args()

    ident_path = Path(args.identifiers)
    if not ident_path.exists():
        print(f"ERROR: {ident_path} not found — run build/enrich_identifiers.py first", file=sys.stderr)
        return 2

    out = Path(args.out)
    struct_dir = out / "structures"
    struct_dir.mkdir(parents=True, exist_ok=True)

    with ident_path.open(newline="", encoding="utf-8") as fh:
        rows = sorted(csv.DictReader(fh), key=lambda r: r["slug"])

    manifest: list[dict] = []
    n_struct = n_card = n_skip = 0
    failures: list[str] = []

    for r in rows:
        slug, name, cls = r["slug"], r["name"], r["compound_class"]
        smiles, conf = r["smiles"].strip(), r["identifier_confidence"]

        if conf != "high" or not smiles:
            n_skip += 1
            manifest.append({
                "slug": slug, "image_type": "none", "path": "", "format": "",
                "alt_text": "", "license": LICENSE, "source": SOURCE,
                "note": f"no image — identifier confidence '{conf}'; no confident structure to render",
            })
            continue

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            failures.append(f"{slug}: RDKit could not parse the SMILES — no image emitted")
            n_skip += 1
            manifest.append({
                "slug": slug, "image_type": "none", "path": "", "format": "",
                "alt_text": "", "license": LICENSE, "source": SOURCE,
                "note": "no image — SMILES failed to parse; not rendered rather than guessed",
            })
            continue

        heavy = mol.GetNumHeavyAtoms()
        formula = rdMolDescriptors.CalcMolFormula(mol)
        mw = Descriptors.MolWt(mol)
        svg = struct_dir / f"{slug}.svg"

        if heavy <= HEAVY_ATOM_LIMIT:
            render_structure(mol, svg)
            try:
                Draw.MolToFile(mol, str(struct_dir / f"{slug}.png"), size=(SVG_W, SVG_H))
            except Exception as e:                       # SVG is the canonical artifact
                failures.append(f"{slug}: PNG render failed ({e}); SVG emitted")
            n_struct += 1
            alt = (f"2D chemical structure of {name} ({formula}), "
                   f"molecular weight {mw:.1f} g/mol, {heavy} heavy atoms.")
            entity_note = r.get("entity_note", "").strip()
            if entity_note:
                # The rendered molecule is a related-but-distinct entity (e.g. the free
                # peptide ligand of a copper complex). Say so in the alt text — an image
                # labelled with the compound's name but depicting something else is a lie.
                alt = (f"2D chemical structure of the entity resolved for {name} ({formula}), "
                       f"molecular weight {mw:.1f} g/mol, {heavy} heavy atoms. "
                       f"Note: {entity_note}.")
            manifest.append({
                "slug": slug, "image_type": "structure",
                "path": f"images/structures/{slug}.svg", "format": "svg",
                "alt_text": alt, "license": LICENSE, "source": SOURCE, "note": entity_note,
            })
        else:
            render_sequence_card(slug, name, cls, formula, heavy, mw, r["inchikey"], svg)
            n_card += 1
            alt = (f"Data card for {name}: {cls}, molecular formula {formula}, {heavy} heavy atoms, "
                   f"molecular weight {mw:.1f} g/mol. Large peptide — 2D structure not shown.")
            manifest.append({
                "slug": slug, "image_type": "sequence_card",
                "path": f"images/structures/{slug}.svg", "format": "svg",
                "alt_text": alt, "license": LICENSE, "source": SOURCE,
                "note": f"large molecule ({heavy} heavy atoms > {HEAVY_ATOM_LIMIT}) — schematic card, not a 2D depiction",
            })

    manifest.sort(key=lambda m: (m["slug"], m["image_type"]))
    with (out / "MANIFEST.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(manifest)

    print("=" * 68)
    print("IMAGE REPORT — structures (§12.1)")
    print("=" * 68)
    print(f"2D structures rendered : {n_struct}  (heavy atoms <= {HEAVY_ATOM_LIMIT})")
    print(f"sequence cards         : {n_card}  (too large for an honest 2D depiction)")
    print(f"no image (honest blank): {n_skip}  (identifier confidence below 'high')")
    print(f"manifest rows          : {len(manifest)} (alt_text on every emitted image)")
    if failures:
        print("\nfailures:")
        for f in failures:
            print(f"  ! {f}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
