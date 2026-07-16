"""Tests for vallydia-register. Runs offline against the local checkout.

    VALLYDIA_REGISTER_DATA=../../data pytest packages/python/test_loader.py
(the conftest sets the env var automatically)
"""

import vallydia_register as vr


def test_compounds_load_offline():
    df = vr.load_compounds(source="local")
    assert len(df) == 85
    assert {"slug", "name", "compound_class", "overall_grade"} <= set(df.columns)


def test_grades_have_nulls_preserved():
    g = vr.load_grades(source="local")
    assert len(g) == 456
    # null grades are kept as empty/NaN, never coerced to a letter
    assert g.grade.isna().sum() + (g.grade == "").sum() == 97


def test_identifiers_no_fabrication():
    idf = vr.load_identifiers(source="local")
    # no SMILES on rows that are not high-confidence
    low = idf[idf.identifier_confidence != "high"]
    assert low.smiles.fillna("").eq("").all()


def test_cosmetic_claims_only_cosmetic():
    claims = vr.load_cosmetic_claims(source="local")
    comp = vr.load_compounds(source="local")
    cosmetic = set(comp[comp.is_cosmetic == True].slug)  # noqa: E712
    assert set(claims.slug) <= cosmetic


def test_attribution_present():
    assert "vallydia.com" in vr.ATTRIBUTION and "CC-BY-4.0" in vr.ATTRIBUTION
