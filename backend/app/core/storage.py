"""Portable, traversal-safe runtime file storage."""
from pathlib import Path
from app.core.config import BASE_DIR

# This file handles how MediExplain+ stores and resolves file references at runtime.
# New files are kept as paths relative to the project directory so the application
# can be moved between different machines without depending on one computer's
# absolute folder structure. When a stored reference is resolved, the resulting
# path is checked to make sure it remains inside the MediExplain+ project storage
# area, which prevents directory traversal outside the application. A small cleanup
# helper is also provided for safely deleting stored files when they are no longer
# needed.

def to_storage_ref(path: str | Path | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    if not p.is_absolute():
        return p.as_posix()
    try:
        return p.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"File is outside MediExplain+ storage: {p}") from exc

def resolve_storage_ref(ref: str | Path | None) -> Path | None:
    if ref is None:
        return None
    p = Path(ref)
    if p.is_absolute():
        # Backwards compatibility for legacy rows. New writes are always relative.
        return p
    resolved = (BASE_DIR / p).resolve()
    base = BASE_DIR.resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError("Invalid storage reference")
    return resolved

def safe_unlink(ref: str | Path | None) -> bool:
    try:
        path = resolve_storage_ref(ref)
    except ValueError:
        return False
    if path and path.exists() and path.is_file():
        path.unlink(missing_ok=True)
        return True
    return False
