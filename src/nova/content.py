"""Data-driven content loading for factions, nations, and visual assets."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil


_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}


@dataclass(frozen=True)
class FactionDefinition:
    """A species, culture, or ideological identity."""

    faction_id: str
    name: str
    species: str
    flag_path: Path
    emblem_path: Path | None
    primary_color: str
    secondary_color: str


@dataclass(frozen=True)
class NationDefinition:
    """A sovereign political entity with its own flag."""

    nation_id: str
    name: str
    faction_id: str | None
    flag_path: Path
    primary_color: str
    secondary_color: str


class ContentError(ValueError):
    """Raised when user or mod content is invalid."""


def _asset_path(root: Path, asset_dir: Path, value: str, field: str) -> Path:
    path = (asset_dir / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ContentError(f"{field} must stay inside the content folder") from error
    if path.suffix.lower() not in _ASSET_EXTENSIONS:
        raise ContentError(f"{field} must be an image asset")
    if not path.is_file():
        raise ContentError(f"{field} does not exist: {path}")
    return path


def load_factions(content_root: Path) -> dict[str, FactionDefinition]:
    """Load every faction manifest below ``content_root/factions``.

    A missing factions directory is valid and produces an empty catalog. This
    lets a mod supply only the content it needs.
    """
    factions_root = content_root / "factions"
    if not factions_root.is_dir():
        return {}

    definitions: dict[str, FactionDefinition] = {}
    for manifest_path in sorted(factions_root.glob("*/faction.json")):
        faction_dir = manifest_path.parent
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            faction_id = str(data["id"])
            name = str(data["name"])
            species = str(data["species"])
            flag_path = _asset_path(content_root, faction_dir, str(data["flag"]), "flag")
            emblem_value = data.get("emblem")
            emblem_path = (
                _asset_path(content_root, faction_dir, str(emblem_value), "emblem")
                if emblem_value
                else None
            )
            definition = FactionDefinition(
                faction_id=faction_id,
                name=name,
                species=species,
                flag_path=flag_path,
                emblem_path=emblem_path,
                primary_color=str(data.get("primary_color", "#43d5d0")),
                secondary_color=str(data.get("secondary_color", "#ffc46b")),
            )
        except (KeyError, TypeError, json.JSONDecodeError, OSError) as error:
            raise ContentError(f"Invalid faction manifest: {manifest_path}") from error
        if not _ID_PATTERN.fullmatch(definition.faction_id):
            raise ContentError(f"Invalid faction id: {definition.faction_id}")
        if definition.faction_id in definitions:
            raise ContentError(f"Duplicate faction id: {definition.faction_id}")
        definitions[definition.faction_id] = definition
    return definitions


class ContentCatalog:
    """Loads and persists player-created factions and nations."""

    def __init__(self, content_root: Path) -> None:
        self.content_root = content_root
        self.factions = load_factions(content_root)
        self.nations = load_nations(content_root, self.factions)

    def create_faction(
        self,
        faction_id: str,
        name: str,
        species: str,
        flag_source: Path,
        *,
        emblem_source: Path | None = None,
        primary_color: str = "#43d5d0",
        secondary_color: str = "#ffc46b",
    ) -> FactionDefinition:
        """Create a player faction and copy its artwork into content."""
        self._validate_new_id(faction_id, self.factions, "faction")
        faction_dir = self.content_root / "factions" / faction_id
        faction_dir.mkdir(parents=True, exist_ok=False)
        flag_path = self._copy_asset(flag_source, faction_dir, "flag")
        emblem_path = (
            self._copy_asset(emblem_source, faction_dir, "emblem")
            if emblem_source
            else None
        )
        data = {
            "id": faction_id,
            "name": name,
            "species": species,
            "flag": flag_path.name,
            "primary_color": primary_color,
            "secondary_color": secondary_color,
        }
        if emblem_path:
            data["emblem"] = emblem_path.name
        (faction_dir / "faction.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        definition = load_factions(self.content_root)[faction_id]
        self.factions[faction_id] = definition
        return definition

    def create_nation(
        self,
        nation_id: str,
        name: str,
        flag_source: Path,
        *,
        faction_id: str | None = None,
        primary_color: str = "#43d5d0",
        secondary_color: str = "#ffc46b",
    ) -> NationDefinition:
        """Create a player nation and copy its flag into content."""
        self._validate_new_id(nation_id, self.nations, "nation")
        if faction_id is not None and faction_id not in self.factions:
            raise ContentError(f"Unknown faction: {faction_id}")
        nation_dir = self.content_root / "nations" / nation_id
        nation_dir.mkdir(parents=True, exist_ok=False)
        flag_path = self._copy_asset(flag_source, nation_dir, "flag")
        data = {
            "id": nation_id,
            "name": name,
            "flag": flag_path.name,
            "primary_color": primary_color,
            "secondary_color": secondary_color,
        }
        if faction_id:
            data["faction"] = faction_id
        (nation_dir / "nation.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        definition = load_nations(self.content_root, self.factions)[nation_id]
        self.nations[nation_id] = definition
        return definition

    @staticmethod
    def _validate_new_id(
        item_id: str, existing: dict[str, object], item_type: str
    ) -> None:
        if not _ID_PATTERN.fullmatch(item_id):
            raise ContentError(f"Invalid {item_type} id: {item_id}")
        if item_id in existing:
            raise ContentError(f"Duplicate {item_type} id: {item_id}")

    @staticmethod
    def _copy_asset(source: Path, destination: Path, field: str) -> Path:
        if not source.is_file():
            raise ContentError(f"{field} source does not exist: {source}")
        if source.suffix.lower() not in _ASSET_EXTENSIONS:
            raise ContentError(f"{field} must be an image asset")
        target = destination / f"{field}{source.suffix.lower()}"
        shutil.copyfile(source, target)
        return target


def load_nations(
    content_root: Path,
    factions: dict[str, FactionDefinition] | None = None,
) -> dict[str, NationDefinition]:
    """Load sovereign nations and their separate flags."""
    nations_root = content_root / "nations"
    if not nations_root.is_dir():
        return {}
    faction_ids = set(factions or load_factions(content_root))
    definitions: dict[str, NationDefinition] = {}
    for manifest_path in sorted(nations_root.glob("*/nation.json")):
        nation_dir = manifest_path.parent
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            nation_id = str(data["id"])
            faction_value = data.get("faction")
            faction_id = str(faction_value) if faction_value else None
            definition = NationDefinition(
                nation_id=nation_id,
                name=str(data["name"]),
                faction_id=faction_id,
                flag_path=_asset_path(content_root, nation_dir, str(data["flag"]), "flag"),
                primary_color=str(data.get("primary_color", "#43d5d0")),
                secondary_color=str(data.get("secondary_color", "#ffc46b")),
            )
        except (KeyError, TypeError, json.JSONDecodeError, OSError) as error:
            raise ContentError(f"Invalid nation manifest: {manifest_path}") from error
        if not _ID_PATTERN.fullmatch(definition.nation_id):
            raise ContentError(f"Invalid nation id: {definition.nation_id}")
        if definition.faction_id is not None and definition.faction_id not in faction_ids:
            raise ContentError(
                f"Nation {definition.nation_id} references unknown faction "
                f"{definition.faction_id}"
            )
        if definition.nation_id in definitions:
            raise ContentError(f"Duplicate nation id: {definition.nation_id}")
        definitions[definition.nation_id] = definition
    return definitions
