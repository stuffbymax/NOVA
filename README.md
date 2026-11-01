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
diameter. The map distinguishes star types and system survey status, marks
gateways, wormholes, anomalies, Union territory, and the Frontier Survey Group,
and highlights routes from the selected system. The P toggle displays faction
ownership as translucent territory regions with faction-colored borders and
labels; connected systems owned by the same faction are joined into a contiguous
territory region. Colonizing a planet expands its owner's region. Use the status
dropdown and search field to filter stars; press Enter in search to locate and
center a match. Zoom with the mouse wheel, pan with the right mouse button, and
press Home to reset the map. Map overlays are toggled with P (territory), T
(trade routes between Union systems), R (surveyed resources), S (sensor
coverage), F (fog of war), and E (exploration). Ctrl+B bookmarks the selected
system and B jumps to the next bookmark. Fog hides uncharted systems outside
Union sensor coverage. Spiral, elliptical, and irregular sectors use different
density profiles; positions also include galactic height. Generated stars use a
weighted spectral distribution, approximate masses, luminosities, ages, and
metallicity gradients. Binary systems constrain stable planet orbits. Planets
have ordered AU-scale orbits, mass and radius estimates, and only long-lived
stars with a world in the temperate zone can generate habitable planets.
Moons, asteroid belts, rare wormholes, nebulae, ancient ruins, and resource
deposits are seeded too. The route network is connected, and the tutorial
landmarks remain available in every seed. This is a plausible game-scale
simulation, not an astronomical catalogue or precision astrophysics model.

## Star systems and planets

System inspection lists the generated planets, moons, and orbital objects.
Planet details include climate, atmosphere, surface conditions, gravity,
physical size, resources when surveyed, and orbital period. Select a planet
and press M for its management view, H for its event history, or D to return to
the details view. The management view reports ownership, population, and
estimated population capacity; surveying and founding a colony add dated
entries to the planetary history. These environmental and capacity values are
procedural gameplay estimates, not scientific predictions.

## Empire and colony management

The main menu lets you choose Human, Auralith, or Veyran colonists for the
Union campaign. Species biology, lifespan, growth, climate preferences, needs,
traits, and hierarchical name pools are defined in `content/species.json`.
Original species portraits and civilization emblems are in `assets/species/`
and `assets/civilizations/`.

Open the **EMPIRE** tab to review population, colonies, resource stockpiles,
construction, research, fleets, and the Veyran Compact. Select a building and
choose **BUILD SELECTED** to queue it on the selected Union colony (or the
capital if the selected system is not a Union colony). Buildings consume
alloys, take time to finish, and then produce resources or research; energy
upkeep is deducted over time. Population grows according to species biology,
climate preference, food availability, and planetary capacity.

Start research from the Empire tab. Research projects unlock technologies and
buildings; later projects require their prerequisites. Commission fleets with
**NEW FLEET**, select a destination system on the map, then use **MOVE FLEET**.
Fleets follow the generated route network and move while the simulation runs.
The Veyran Compact expands toward unclaimed habitable worlds over time.

Use **F5** for a quick save, **F9** to load it, and **F10** to return to the
main menu. Saves are versioned, checksummed JSON files in `saves/`; override
the location with `save_path` in `config.toml`. The simulation can be paused
with Space or the pause button and accelerated with the speed control. These
are foundational strategy systems; diplomacy, tactical combat, espionage,
and advanced politics remain future work.
