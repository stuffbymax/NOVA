# NOVA art pack

The `generated` directory contains NOVA's editable SVG art pack. The images
follow the visual direction in `../prompts/visual-style.md`: dark navy space,
teal and amber accents, painterly layers, soft atmospheric lighting, and
dimensional shading. Assets are SVG so they can be adjusted without external
image tools.

Validate the SVG files from the repository root with:

```powershell
python tools\validate_art.py
```

Included art:

- galaxy and star-system backdrops
- ocean, desert, jungle, arctic, volcanic, and toxic planets
- faction emblem
- fleet silhouettes
- orbital station
- species silhouettes
- resource and interface icons

These are original 2D illustrations with layered shading and 3D-like
science-fiction material cues, not 3D renders. SVGs are the source assets;
edit them directly or replace a file while keeping its name to update the
client without changing its code.

The graphical client loads these assets through `nova.assets.AssetManager`,
which caches source images and scaled variants for the pygame renderer.
