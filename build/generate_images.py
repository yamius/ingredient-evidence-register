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

§12.2 grade cards are pure data-viz built from the grades themselves: a per-outcome A–F
strip, the overall grade, and a "based on N sources, M DOI-verified" line. They show grades
only — no claims language beyond the outcomes that were graded — and are reproducible from
data/compounds.jsonl.

Outputs: images/structures/<slug>.svg (+ .png), images/grade-cards/<slug>.svg,
images/MANIFEST.csv (with mandatory alt_text on every emitted image).

Usage:
    python build/generate_images.py
"""

from __future__ import annotations

import argparse
import csv
import html
import json
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

GRADECARD_SOURCE = "Vallydia Ingredient-Evidence Register (https://vallydia.com) — evidence-grade card rendered from the dataset grades"

# Chip fills for each grade. Distinct hues, all dark enough to carry white text at >= 4.5:1;
# the ungraded case is a neutral grey with an em dash (a null row is not an F — see METHODOLOGY).
GRADE_FILL = {
    "A": "#1a7f52", "B": "#4f9d3f", "C": "#c08a1e",
    "D": "#c56a2a", "F": "#b23b3b", None: "#8a9098",
}
GRADE_LABEL = {"A": "A", "B": "B", "C": "C", "D": "D", "F": "F", None: "–"}


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


def _wrap(text: str, width: int) -> list[str]:
    """Greedy word-wrap to at most two lines; the second is ellipsised if it overflows."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
        if len(lines) == 2:
            break
    if cur and len(lines) < 2:
        lines.append(cur)
    if len(lines) == 2 and (len(" ".join(words)) > sum(len(l) for l in lines) + 1):
        lines[1] = lines[1][: width - 1].rstrip() + "…"
    return lines[:2] or [""]


def render_grade_card(rec: dict, path_svg: Path) -> str:
    """Evidence-grade infographic for one compound. Returns the factual alt_text.

    Pure data-viz: overall grade badge + a per-outcome A–F strip + a provenance line. No
    claims language beyond the outcomes the register actually graded.
    """
    e = html.escape
    name = rec["name"]
    overall = rec.get("overall_grade")
    outcomes = rec.get("grades_by_outcome", [])
    n_sources = len(rec.get("sources", []))
    n_doi = len([c for c in rec.get("citation_ids", []) if c.get("doi")])

    row_h, top, foot = 46, 150, 74
    height = top + max(1, len(outcomes)) * row_h + foot
    rows_svg = []
    y = top
    for g in outcomes:
        grade = g.get("grade")
        fill = GRADE_FILL.get(grade, GRADE_FILL[None])
        lines = _wrap(str(g.get("outcome", "")), 52)
        chip = (f'<rect x="40" y="{y-22}" width="34" height="34" rx="7" fill="{fill}"/>'
                f'<text x="57" y="{y+1}" text-anchor="middle" class="chip">{GRADE_LABEL.get(grade, "–")}</text>')
        if len(lines) == 1:
            txt = f'<text x="90" y="{y+1}" class="out">{e(lines[0])}</text>'
        else:
            txt = (f'<text x="90" y="{y-8}" class="out">{e(lines[0])}</text>'
                   f'<text x="90" y="{y+12}" class="out">{e(lines[1])}</text>')
        rows_svg.append(chip + txt)
        y += row_h

    obadge = ""
    if overall:
        obadge = (f'<rect x="{SVG_W-118}" y="44" width="72" height="72" rx="14" fill="{GRADE_FILL.get(overall)}"/>'
                  f'<text x="{SVG_W-82}" y="92" text-anchor="middle" class="obig">{e(overall)}</text>'
                  f'<text x="{SVG_W-82}" y="132" text-anchor="middle" class="olab">overall</text>')
    else:
        obadge = (f'<text x="{SVG_W-82}" y="92" text-anchor="middle" class="olab">overall:</text>'
                  f'<text x="{SVG_W-82}" y="112" text-anchor="middle" class="olab">not assigned</text>')

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{height}" viewBox="0 0 {SVG_W} {height}" role="img">
  <style>
    .t {{ font: 600 27px system-ui, -apple-system, "Segoe UI", sans-serif; fill: currentColor; }}
    .s {{ font: 400 14px system-ui, -apple-system, "Segoe UI", sans-serif; fill: currentColor; opacity:.6; }}
    .out {{ font: 400 16px system-ui, -apple-system, "Segoe UI", sans-serif; fill: currentColor; }}
    .chip {{ font: 700 18px system-ui, -apple-system, "Segoe UI", sans-serif; fill: #fff; }}
    .obig {{ font: 700 40px system-ui, -apple-system, "Segoe UI", sans-serif; fill: #fff; }}
    .olab {{ font: 500 13px system-ui, -apple-system, "Segoe UI", sans-serif; fill: currentColor; opacity:.6; }}
    .f  {{ font: 400 14px system-ui, -apple-system, "Segoe UI", sans-serif; fill: currentColor; opacity:.75; }}
    .b  {{ fill: none; stroke: currentColor; stroke-opacity:.2; stroke-width:1.5; }}
  </style>
  <rect class="b" x="12" y="12" width="{SVG_W-24}" height="{height-24}" rx="16"/>
  <text x="40" y="66" class="t">{e(name)}</text>
  <text x="40" y="90" class="s">{e(rec["slug"])} · evidence by outcome</text>
  {obadge}
  <line x1="40" y1="120" x2="{SVG_W-40}" y2="120" stroke="currentColor" stroke-opacity=".18"/>
  {''.join(rows_svg)}
  <line x1="40" y1="{height-foot+14}" x2="{SVG_W-40}" y2="{height-foot+14}" stroke="currentColor" stroke-opacity=".18"/>
  <text x="40" y="{height-foot+42}" class="f">Based on {n_sources} cited sources · {n_doi} DOI-verified · grades are Vallydia's evidence assessment (CC-BY-4.0)</text>
</svg>
"""
    path_svg.write_text(svg, encoding="utf-8", newline="\n")

    parts = [f"Evidence-grade card for {name}.",
             f"Overall grade {overall}." if overall else "Overall grade not assigned."]
    graded = [f"{g.get('outcome')}: {g.get('grade') or 'not graded'}" for g in outcomes]
    if graded:
        parts.append("Per-outcome — " + "; ".join(graded) + ".")
    parts.append(f"Based on {n_sources} cited sources, {n_doi} DOI-verified.")
    return " ".join(parts)


def build_grade_cards(compounds_path: Path, out: Path, manifest: list[dict],
                      failures: list[str]) -> int:
    """Render a grade card per compound from compounds.jsonl; append manifest rows."""
    if not compounds_path.exists():
        failures.append(f"grade cards skipped — {compounds_path.name} not found (run generate_dataset.py first)")
        return 0
    gc_dir = out / "grade-cards"
    gc_dir.mkdir(parents=True, exist_ok=True)
    recs = [json.loads(l) for l in compounds_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = 0
    for rec in sorted(recs, key=lambda r: r["slug"]):
        svg = gc_dir / f"{rec['slug']}.svg"
        alt = render_grade_card(rec, svg)
        manifest.append({
            "slug": rec["slug"], "image_type": "grade_card",
            "path": f"images/grade-cards/{rec['slug']}.svg", "format": "svg",
            "alt_text": alt, "license": LICENSE, "source": GRADECARD_SOURCE, "note": "",
        })
        n += 1
    return n


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--identifiers", default=str(root / "data" / "identifiers.csv"))
    ap.add_argument("--compounds", default=str(root / "data" / "compounds.jsonl"))
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

    n_grade = build_grade_cards(Path(args.compounds), out, manifest, failures)

    manifest.sort(key=lambda m: (m["slug"], m["image_type"]))
    with (out / "MANIFEST.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(manifest)

    print("=" * 68)
    print("IMAGE REPORT — structures (§12.1) + grade cards (§12.2)")
    print("=" * 68)
    print(f"2D structures rendered : {n_struct}  (heavy atoms <= {HEAVY_ATOM_LIMIT})")
    print(f"sequence cards         : {n_card}  (too large for an honest 2D depiction)")
    print(f"no structure (blank)   : {n_skip}  (identifier confidence below 'high')")
    print(f"grade cards rendered   : {n_grade}  (one per compound, from the grades data)")
    print(f"manifest rows          : {len(manifest)} (alt_text on every emitted image)")
    if failures:
        print("\nfailures:")
        for f in failures:
            print(f"  ! {f}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
