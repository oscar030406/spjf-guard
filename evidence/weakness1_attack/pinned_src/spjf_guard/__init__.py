"""Pinned scheduling modules with read-only fallback to project data loaders."""
from pathlib import Path
__path__.append(str(Path(__file__).resolve().parents[4] / "src" / "spjf_guard"))
__version__ = "0.1.0"
