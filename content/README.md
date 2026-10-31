# NOVA content folder

NOVA reads factions and nations from this folder at startup. They are separate:
factions represent species, cultures, or ideologies; nations are sovereign
political entities that may belong to a faction.

## Faction layout

```text
content/
  factions/
    my_faction/
      faction.json
      flag.svg
      emblem.svg
  nations/
    my_nation/
      nation.json
      flag.svg
```

Example `faction.json`:

```json
{
  "id": "my_faction",
  "name": "My Faction",
  "species": "aquatic",
  "flag": "flag.svg",
  "emblem": "emblem.svg"
}
```

Example `nation.json`:

```json
{
  "id": "my_nation",
  "name": "My Nation",
  "faction": "my_faction",
  "flag": "flag.svg",
  "primary_color": "#43d5d0",
  "secondary_color": "#ffc46b"
}
```

Faction `flag` is required and `emblem` is optional. Nation `flag` is required.
A nation may omit `faction` for an independent political identity. Players can
create both through the in-game faction/nation creator; the resulting manifest
and copied artwork are saved into this same structure. Supported artwork
formats are SVG, PNG, JPEG, and WebP. Asset paths must remain inside their
content folder. Use lowercase IDs with letters, numbers, underscores, or
hyphens.

Set a different content root in `config.toml`:

```toml
content_path = "my-content"
```

This makes it possible to keep personal or mod content outside the repository.
