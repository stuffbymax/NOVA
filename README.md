bit of AI gen was used

## Procedural galaxies

NOVA generates a reproducible Milky Way sector when a campaign starts. Galaxy
size can be `small` (24 systems), `medium` (48), or `large` (80); supported
shapes are `spiral`, `elliptical`, and `irregular`. A seed reproduces the same
map, systems, routes, planets, and discoveries. The galaxy catalogue includes
the Milky Way, Andromeda, Triangulum, Whirlpool, Pinwheel, Sombrero, Messier 87,
Messier 49, Messier 60, and the Large and Small Magellanic Clouds. Select a
catalogue entry only with its matching morphology. Galaxy diameter is based on
the selected galaxy; the map's stars are a generated game-scale sector, not
survey data.

Set these options in `config.toml` to choose a galaxy:

```toml
galaxy_seed = 2480
galaxy_size = "medium"
galaxy_shape = "spiral"
galaxy_name = "Milky Way"
```

The galaxy view shows its name, sector, morphology, system count, seed, and
diameter. Spiral, elliptical, and irregular sectors use different density
profiles; positions also include galactic height. Generated stars use a
weighted spectral distribution, approximate masses, luminosities, ages, and
metallicity gradients. Binary systems constrain stable planet orbits. Planets
have ordered AU-scale orbits, mass and radius estimates, and only long-lived
stars with a world in the temperate zone can generate habitable planets.
Moons, asteroid belts, rare wormholes, nebulae, ancient ruins, and resource
deposits are seeded too. The route network is connected, and the tutorial
landmarks remain available in every seed. This is a plausible game-scale
simulation, not an astronomical catalogue or precision astrophysics model.
