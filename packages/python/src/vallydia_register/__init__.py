"""
vallydia-register — a thin loader for the Vallydia Ingredient-Evidence Register.

Evidence-graded cosmetic and research ingredients, returned as pandas DataFrames. Data is
pulled from the published dataset (GitHub raw by default, or the Hugging Face mirror) and
cached locally; point at a local checkout with the ``VALLYDIA_REGISTER_DATA`` env var or the
``source=`` argument for offline use.

    from vallydia_register import load_compounds, load_grades
    df = load_grades()
    df[df.grade == "A"]

Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0.
Any use must attribute Vallydia.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

__version__ = "1.1.0"

ATTRIBUTION = "Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0."
HOMEPAGE = "https://vallydia.com"

SOURCES = {
    "github": "https://raw.githubusercontent.com/yamius/ingredient-evidence-register/main",
    "hf": "https://huggingface.co/datasets/vallydia/ingredient-evidence-register/resolve/main",
}

# Tidy tables published as parquet.
_TABLES = {
    "compounds", "grades", "legal_status", "citations",
    "cosmetic_claims", "identifiers", "citations_enriched",
}


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    d = Path(base) / "vallydia-register"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve(name: str, source: str) -> str | Path:
    """Return a local Path or a remote URL for the parquet file ``name``.

    source resolution:
      * "github" / "hf" — the published remote (default), UNLESS VALLYDIA_REGISTER_DATA is
        set, in which case that local checkout wins (the documented offline path).
      * "local"         — use VALLYDIA_REGISTER_DATA (raises if it is unset).
      * anything else    — treated as a local data directory path.
    """
    env = os.environ.get("VALLYDIA_REGISTER_DATA")
    if source not in SOURCES and source != "local":
        base_dir: Path | None = Path(source)          # an explicit filesystem path
    elif source == "local":
        if not env:
            raise ValueError("source='local' requires the VALLYDIA_REGISTER_DATA env var")
        base_dir = Path(env)
    elif env:
        base_dir = Path(env)                           # env overrides the remote default (offline)
    else:
        base_dir = None
    if base_dir is not None:
        cand = base_dir / "parquet" / f"{name}.parquet"
        return cand if cand.exists() else base_dir / f"{name}.parquet"
    return f"{SOURCES[source]}/data/parquet/{name}.parquet"


def _load(name: str, source: str = "github", use_cache: bool = True) -> pd.DataFrame:
    if name not in _TABLES:
        raise ValueError(f"unknown table {name!r}; one of {sorted(_TABLES)}")
    target = _resolve(name, source)
    if isinstance(target, Path):
        return pd.read_parquet(target)

    cache = _cache_dir() / f"{name}.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache)
    df = pd.read_parquet(target)           # pandas/pyarrow fetch the URL directly
    if use_cache:
        try:
            df.to_parquet(cache, index=False)
        except Exception:
            pass                            # a read-only cache dir is not fatal
    return df


def load_compounds(source: str = "github", use_cache: bool = True) -> pd.DataFrame:
    """One row per compound (flat core + pipe-joined lists). 85 rows."""
    return _load("compounds", source, use_cache)


def load_grades(source: str = "github", use_cache: bool = True) -> pd.DataFrame:
    """One row per compound x outcome. Grade may be null (safety/penetration rows)."""
    return _load("grades", source, use_cache)


def load_legal_status(source: str = "github", use_cache: bool = True) -> pd.DataFrame:
    """One row per compound x region (INT/EU/US/UK)."""
    return _load("legal_status", source, use_cache)


def load_citations(source: str = "github", use_cache: bool = True,
                   enriched: bool = False) -> pd.DataFrame:
    """DOI-verified citations. Pass ``enriched=True`` for the scholarly cross-links."""
    return _load("citations_enriched" if enriched else "citations", source, use_cache)


def load_cosmetic_claims(source: str = "github", use_cache: bool = True) -> pd.DataFrame:
    """Permitted / forbidden cosmetic-claim wordings (is_cosmetic compounds only)."""
    return _load("cosmetic_claims", source, use_cache)


def load_identifiers(source: str = "github", use_cache: bool = True) -> pd.DataFrame:
    """Chemical identifiers with confidence + provenance. Blanks are honest, not missing."""
    return _load("identifiers", source, use_cache)


__all__ = [
    "load_compounds", "load_grades", "load_legal_status", "load_citations",
    "load_cosmetic_claims", "load_identifiers",
    "ATTRIBUTION", "HOMEPAGE", "__version__",
]
