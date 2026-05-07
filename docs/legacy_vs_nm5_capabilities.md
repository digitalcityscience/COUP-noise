# Legacy NoiseMap vs NoiseModelling 5 Capabilities

This note compares the older NoiseMap-style model and NoiseModelling 5 in general terms. It is not about the adapter code in this repository.

## Short Answer

NoiseModelling 5 is not simply "the old model plus 3D." The older NoiseMap stack could already do some 3D propagation when used through its 3D functions.

The real benefit of NoiseModelling 5 is that it is the current, better documented, CNOSSOS-oriented workflow. It models roads, railways, time periods, atmosphere, ground, directivity, receivers, and diagnostics in a richer and more explicit way.

## Terms

- `Legacy NoiseMap`: the older OrbisGIS/H2GIS NoiseMap function stack, for example `BR_TriGrid`, `BR_TriGrid3D`, `BR_PtGrid`, and `BR_PtGrid3D`.
- `NoiseModelling 5` or `NM5`: the current NoiseModelling WPS/JDBC stack, with scripts such as `Road_Emission_from_Traffic`, `Railway_Emission_from_Traffic`, `Noise_level_from_traffic`, `Noise_level_from_source`, `Delaunay_Grid`, and `Create_Isosurface`.

## Capability Comparison

| Capability | Legacy NoiseMap | NoiseModelling 5 |
| --- | --- | --- |
| Basic road noise map | Yes | Yes |
| Building obstacles | Yes | Yes |
| Building heights | Possible through 3D functions | First-class input through `BUILDINGS.HEIGHT` |
| DEM / terrain | Possible through 3D functions | First-class optional propagation input |
| Ground absorption | Possible through 3D functions | First-class `GROUND` / `tableGroundAbs` input |
| Reflections | Yes, through reflection order | Yes, through `confReflOrder` and reflection distance |
| Diffraction | Yes, through diffraction order | Yes, with separate horizontal and vertical flags |
| Road source detail | Older, simpler road/source interface | CNOSSOS-style vehicle classes, speeds, pavement, slope, junction, direction, studded tyres |
| Rail source detail | Simpler tram/rail support | Separate rail sections and rail traffic with train type, speed, track count, roughness, impact, curvature, bridge, tunnel, and D/E/N traffic |
| Time periods | Usually one map or simpler period handling | Day/evening/night and custom periods are part of the normal workflow |
| Atmospheric settings | More limited in the normal workflow | Temperature, humidity, favourable occurrences, wind rose, pressure, ground discontinuity flags |
| Directivity | Limited compared with NM5 workflow | Directivity table for source orientation and octave-band attenuation |
| Source diagnostics | Limited | Can export levels by source id and optionally export rays |
| Receiver generation | Grid/triangle functions | Dedicated receiver workflows, including Delaunay receiver generation with fence, building buffer, road width, mesh size |
| Current maintenance path | Older stack | Current NoiseModelling stack |

## What NM5 Really Adds

### Better source descriptions

The biggest practical improvement is source modelling.

For roads, NM5 can describe separate vehicle classes: light vehicles, medium vehicles, heavy vehicles, mopeds, motorcycles, and their speeds. It also supports pavement, slope, junction distance, junction type, traffic direction, and studded tyres.

For railways, NM5 separates the track from the traffic. Track sections can describe track count, track speed, transfer function, roughness, impact noise, curvature, bridge type, and tunnel status. Rail traffic can describe train type, train speed, and day/evening/night train counts.

### Better time modelling

NM5 treats periods as normal data. You can use day/evening/night fields or custom period rows such as `08:00-09:00`. Period-specific propagation and atmospheric settings can then be attached to the calculation.

### Better environmental modelling

NM5 makes DEM, ground absorption, building heights, humidity, temperature, pressure, and favourable propagation occurrence part of the documented workflow. Legacy 3D functions could accept some of this, but NM5 makes it much clearer and easier to combine with modern road and rail emissions.

### Better diagnostics

NM5 can keep source identifiers in receiver results, export propagation rays, and work through explicit intermediate tables such as source emission tables and receiver level tables. That makes validation and debugging easier.

### Better future value

The old model can still be useful for fast compatibility or historic parity checks. NM5 is the better place to invest new work because it is the maintained workflow and aligns with the current NoiseModelling documentation.

## What NM5 Does Not Automatically Solve

NM5 is not automatically better if the input data stays simple.

If both models are fed only rough roads, rough traffic counts, flat terrain, no building heights, no ground data, no atmosphere, no directivity, and legacy-like propagation settings, then NM5 may mainly give a better architecture rather than a dramatically better result.

The result quality improves when the input quality improves.

## Practical Migration Logic

1. Start with NM5 configured like legacy: no reflections, no diffraction, similar source distance, similar wall absorption, and a coarse receiver mesh.
2. Validate that the outputs are in the same rough range.
3. Add richer source data first: vehicle classes, rail metadata, day/evening/night periods, pavement, slope, and junctions.
4. Add environmental data: building heights, DEM, ground absorption, and atmosphere.
5. Enable expensive propagation features such as diffraction and reflections only when the runtime budget allows it.

## Sources

- NoiseModelling documentation: https://noisemodelling.readthedocs.io/en/latest/
- Roads input: https://noisemodelling.readthedocs.io/en/latest/Input_roads.html
- Railways input: https://noisemodelling.readthedocs.io/en/latest/Input_railways.html
- Buildings input: https://noisemodelling.readthedocs.io/en/latest/Input_buildings.html
- DEM input: https://noisemodelling.readthedocs.io/en/latest/Input_dem.html
- Ground input: https://noisemodelling.readthedocs.io/en/latest/Input_ground.html
- Acoustic parameters: https://noisemodelling.readthedocs.io/en/latest/Input_acoustics.html
- Bundled legacy classes checked locally: `noise_analysis/orbisgis_java/bundle/noisemap-h2-2.1.2-SNAPSHOT.jar`
- Bundled NM5 WPS scripts checked locally: `NoiseModelling/wps_scripts/src/main/groovy/org/noise_planet/noisemodelling/wps`
