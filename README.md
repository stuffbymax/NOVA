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
and highlights routes from the selected system. Click a star to select it while
keeping the galaxy map open; use the SYSTEM tab to switch to its orbital view.
The map toolbar toggles ownership, fleets, trade routes, resources, sensors,
fog, and exploration layers; keyboard shortcuts P, T, R, S, F, and E remain
available. Ownership appears as translucent territory regions with colored
frontier lines and faction labels; connected systems owned by the same faction
are joined into a contiguous territory region. Colonizing a planet expands its
owner's region. The command bar presents resource stockpiles and campaign date;
the active navigation view is highlighted without obscuring the dark map. The
selected system is marked with a navigation reticle and summarized in the map
card. Use the status dropdown and search field to filter stars; press Enter in
search to locate and center a match. Zoom with the mouse wheel, pan with the
right mouse button, and press Home to reset the map. Ctrl+B bookmarks the
selected system and B jumps to the next bookmark. Fog hides uncharted systems
outside Union sensor coverage. Spiral, elliptical, and irregular sectors use
different density profiles; positions also include galactic height. Generated
stars use a weighted spectral distribution, approximate masses, luminosities,
ages, and metallicity gradients. Binary systems constrain stable planet orbits.
Planets have ordered AU-scale orbits, mass and radius estimates, and only
long-lived stars with a world in the temperate zone can generate habitable planets.
Moons, asteroid belts, rare wormholes, nebulae, ancient ruins, and resource
deposits are seeded too. The route network is connected, and the tutorial
landmarks remain available in every seed. This is a plausible game-scale
simulation, not an astronomical catalogue or precision astrophysics model.

## Star systems and planets

System inspection lists the generated planets, moons, and orbital objects.
Planet details include climate, atmosphere, surface conditions, gravity,
physical size, resources when surveyed, and orbital period. Select a planet
in the system view to open its dossier. Surveyed and colonized worlds receive a
procedural 2D planetary illustration and show population, capacity, climate,
habitability, gravity, atmosphere, terrain, and surveyed deposits. Unsurveyed
world details remain hidden until a survey is completed. Press M for the
management view or H for planetary history. Surveying and founding a colony add
dated entries to the planetary history. These environmental and capacity
values are procedural gameplay estimates, not scientific predictions.

## Empire and colony management

The main menu lets you choose Human, Auralith, Veyran, or Synthetic colonists
for the Union campaign. Click the naming-style selector or press N to cycle
through all names or a specific culture, including hierarchical Human pools
such as Uralic and Hungarian. Species biology, lifespan, growth, climate
preferences, needs, traits, and name pools are defined in
`content/species.json`. Original species portraits and civilization emblems
are in `assets/species/` and `assets/civilizations/`.

Open the **EMPIRE** tab to review population, colonies, resource stockpiles,
construction, research, fleets, and the Veyran Compact. Select a building and
choose **BUILD SELECTED** to queue it on the selected Union colony (or the
capital if the selected system is not a Union colony). Buildings consume
alloys, take time to finish, and then produce resources or research; energy
upkeep is deducted over time. Population grows according to species biology,
climate preference, food availability, and planetary capacity.

Open the **SPECIES** tab to review each Union colony's population, species,
rights, needs, climate fit, and adaptation progress. Select a colony and choose
an action to change that species' rights, organize migration to another colony
of the same species, or perform genetic engineering. Research Xenobiology to
unlock genetic modifications and synthetic conversion. Colonies persistently
outside their species' preferred climates gradually evolve a natural
adaptation. Rights affect population growth and happiness; restricted
populations cannot migrate. Genetic modifications cost 15 science and 3
influence; synthetic conversion costs 30 science and 5 influence; migration
costs 1 influence and moves up to 0.1 billion people.

Start research from the Empire tab. Research projects unlock technologies and
buildings; later projects require their prerequisites. Commission fleets with
**NEW FLEET**, select a destination system on the map, then use **MOVE FLEET**.
Fleets follow the generated route network and move while the simulation runs.
The Veyran Compact expands toward unclaimed habitable worlds over time.

## First contact, diplomacy, and conflict

Rival civilizations begin as intercepted signals, not established
relationships. Survey a Veyran-held system to open first contact, then use the
**DIPLO** tab to send envoys, negotiate non-aggression, trade and research
agreements, sign a defensive pact, or declare war. Envoys cost influence
and have a cooldown; proposals depend on the rival's opinion. Trade and
research agreements have ongoing effects on the Union's income. Active
agreements must be broken before war can be declared, and peace can be
negotiated after the rival is defeated or the war has lasted long enough. The
defensive pact currently prevents a direct declaration of war; mutual military
assistance is not implemented yet.

War changes the map: fleets fight automatically when they enter hostile
systems, ship losses are recorded, and victories transfer system ownership.
Rival fleets retaliate against Union territory while hostilities continue.
Fleet markers use different colors for Union and rival forces. The Chronicle
records first contact, negotiations, declarations, battles, territorial
changes, and ceasefires. These strategic systems are an initial playable
foundation; full tactical combat and the broader political and diplomatic
systems remain future work.

Use **F5** for a quick save, **F9** to load it, and **F10** to return to the
main menu. Saves are versioned, checksummed JSON files in `saves/`; override
the location with `save_path` in `config.toml`. The simulation can be paused
with Space or the pause button and accelerated with the speed control. These
are foundational strategy systems; diplomacy, tactical combat, espionage,
and advanced politics remain future work.
