"""Remote backend normalization and legacy compatibility helpers."""

from __future__ import annotations

from typing import Final

BACKEND_ALIASES: Final[dict[str, str]] = {
    "dropbox": "dropbox",
    "onedrive": "onedrive",
    "drive": "drive",
    "googledrive": "drive",
    "gdrive": "drive",
    "erda": "erda",
    "ucloud": "ucloud",
    "lumio": "lumio",
    "lumi-o": "lumio",
    "lumip": "lumip",
    "lumi-p": "lumip",
    "lumi-f": "lumip",
    "lumi": "lumio",  # legacy fallback
    "local": "local",
    "s3": "s3",
    "sftp": "sftp",
}

CANONICAL_BACKENDS: Final[tuple[str, ...]] = (
    "dropbox",
    "onedrive",
    "drive",
    "erda",
    "ucloud",
    "lumio",
    "lumip",
    "local",
    "s3",
    "sftp",
)


def normalize_backend(value: str | None) -> str | None:
    """Normalize explicit backend input to a canonical backend."""
    if not value:
        return None
    key = str(value).strip().lower()
    return BACKEND_ALIASES.get(key)


def infer_backend_from_remote_name(remote_name: str | None) -> str | None:
    """
    Infer backend from alias prefix for backward compatibility.
    Returns None if no known prefix is present.
    """
    remote_lower = (remote_name or "").strip().lower()
    if not remote_lower:
        return None

    for alias in sorted(BACKEND_ALIASES.keys(), key=len, reverse=True):
        if remote_lower == alias:
            return BACKEND_ALIASES[alias]
        if remote_lower.startswith(alias):
            next_char = remote_lower[len(alias) : len(alias) + 1]
            if next_char in {"", "-", "_", ":"}:
                return BACKEND_ALIASES[alias]
    return None


def resolve_backend(explicit_backend: str | None, remote_name: str | None) -> str:
    """
    Resolve backend with precedence:
    1) explicit --backend
    2) inferred from remote alias
    3) fallback to sftp (legacy behavior)
    """
    normalized_explicit = normalize_backend(explicit_backend)
    if normalized_explicit:
        return normalized_explicit
    inferred = infer_backend_from_remote_name(remote_name)
    if inferred:
        return inferred
    return "sftp"


def get_base_remote_type(backend: str) -> str:
    """Map canonical backend to rclone backend type."""
    mapping = {
        "erda": "sftp",
        "ucloud": "sftp",
        "lumip": "sftp",
        "lumio": "s3",
    }
    return mapping.get(backend, backend)


def _detect_remote_type(remote_name: str) -> str:
    """Legacy compatibility wrapper."""
    return resolve_backend(None, remote_name)


def _get_base_remote_type(remote_name: str) -> str:
    """Legacy compatibility wrapper."""
    return get_base_remote_type(_detect_remote_type(remote_name))
