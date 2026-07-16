"""Point the loader at the local checkout so the package tests run offline."""
import os
from pathlib import Path

os.environ.setdefault(
    "VALLYDIA_REGISTER_DATA",
    str(Path(__file__).resolve().parent.parent.parent / "data"),
)
