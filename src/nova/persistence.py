"""Versioned JSON saves with integrity validation and atomic replacement."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .campaign import Campaign


class SaveError(RuntimeError):
    """Raised when a campaign save cannot be read or written."""


def save_campaign(path: Path, campaign: Campaign) -> None:
    payload = campaign.to_dict()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    document = {
        "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "campaign": payload,
        "metadata": {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "date": campaign.date_label,
            "galaxy": campaign.galaxy.name,
            "schema_version": payload["schema_version"],
        },
    }
    temporary_path = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    except OSError as error:
        raise SaveError(f"Could not write campaign save: {path}") from error
    finally:
        temporary_path.unlink(missing_ok=True)


def load_campaign(path: Path, content_path: Path | None = None) -> Campaign:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SaveError(f"Could not read campaign save: {path}") from error
    if not isinstance(document, dict):
        raise SaveError("Campaign save must contain a JSON object")
    payload = document.get("campaign")
    checksum = document.get("checksum")
    if not isinstance(payload, dict) or not isinstance(checksum, str):
        raise SaveError("Campaign save is missing its payload or checksum")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if checksum != expected:
        raise SaveError("Campaign save failed its integrity check")
    try:
        return Campaign.from_dict(payload, content_path)
    except (KeyError, TypeError, ValueError) as error:
        raise SaveError(f"Campaign save contains invalid game data: {error}") from error
