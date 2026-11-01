# NOVA art pack

Add active, editable art directly under `assets/` or in its named content
folders. The runtime does not load files from `generated examples`. The
included galaxy background follows the visual direction in
`../prompts/visual-style.md`: dark navy space,
teal and amber accents, painterly layers, soft atmospheric lighting, and
dimensional shading. Assets are SVG so they can be adjusted without external
image tools.

Validate the SVG files from the repository root with:

```powershell
python tools\validate_art.py
```

The active art includes:

- a galaxy background at `galaxy-background.svg`
- an ancient gateway illustration at `Anomalies/ancient gateway.jpg`
- three original species portraits under `species/`
- civilization emblems under `civilizations/`
- additional content-specific art can be added directly under `assets/`

These are original 2D illustrations with layered shading and 3D-like
science-fiction material cues, not 3D renders. SVGs are the source assets;
edit or replace them directly to update the client without changing its code.

The graphical client loads these assets through `nova.assets.AssetManager`,
which caches source images and scaled variants for the pygame renderer.
