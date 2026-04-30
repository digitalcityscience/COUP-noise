# Parameter Impact and Runtime Matrix

This matrix ranks the practical impact of COUP-noise inputs and settings on output behavior, runtime, and memory. It is based on the current adapter code plus the observed HafenCity runs in this repo. Treat it as operational guidance, not a substitute for benchmark data on the target deployment hardware.

## Legend

| Rating | Meaning |
| --- | --- |
| None | No meaningful effect in the current implementation. |
| Low | Usually small effect, unless combined with larger area/data. |
| Medium | Noticeable effect on output or runtime. |
| High | Major effect; should be chosen deliberately. |
| Very high | Dominant driver; can change runtime by orders of magnitude. |

Direction notation:

- `increase -> slower` means larger values usually increase runtime.
- `increase -> faster` means larger values usually reduce runtime.
- `on -> slower` means enabling a boolean usually increases runtime.

Known local observations:

- Legacy COUP run for a roughly 200 ha area was reported at about 30 seconds.
- HafenCity half-area `nm5_full` smoke run, about 30 ha with 10 m DEM sampling, took about 162 seconds.
- HafenCity full package is about 58 ha but has about 583k DEM points versus about 2.9k DEM points in the half 10 m package, so it is not a simple 2x scale-up.

## Most Important Levers

| Rank | Lever | Runtime impact | Output impact | Direction | Practical guidance |
| --- | --- | --- | --- | --- | --- |
| 1 | DEM point count / DEM spacing | Very high | Medium to high | more points -> slower | Downsample DEM for preview. Dense 1 m DEM can dominate import, memory, and propagation work. |
| 2 | `max_area` | Very high | High | increase -> faster | Main receiver mesh coarseness knob. Large values are suitable for preview; small values for detailed maps. |
| 3 | `max_source_distance` | Very high | High | increase -> slower | Larger search radius increases source-receiver combinations and contour reach. Keep short for preview. |
| 4 | Diffraction flags | High | High | on -> slower | `diff_horizontal` and `diff_vertical` improve physical behavior but are expensive. Disable for fast previews. |
| 5 | `reflection_order` | High to very high | Medium to high | increase -> slower | Reflections can be expensive. Keep `0` unless needed. |
| 6 | Project area size and tiling | High | High | larger -> slower | Runtime usually scales with area and receiver count. Consider buffered tiling for production. |
| 7 | Source count and source geometry complexity | High | High | more/complex -> slower | Simplify or filter minor sources for preview. |
| 8 | Building count and geometry complexity | Medium to high | High | more/complex -> slower | Buildings affect obstruction/reflection and receiver generation. Simplify geometry carefully for preview. |
| 9 | `max_error` | Medium to high | Medium | increase -> faster | Looser propagation error can improve runtime. Use higher values only for preview. |
| 10 | `thread_number` and worker CPU | Medium to high | None | tune to hardware | Helps single-job runtime if enough CPU is available. Avoid running too many multi-threaded jobs on one host. |

## Dataset and Layer Matrix

| Input/layer | Engines | Result impact | Runtime impact | Memory impact | Direction | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `project_area.geojson` area | all | High | High | Medium | larger -> slower | Used for clipping in all engines and receiver fencing in `nm5_full`. |
| `project_area.geojson` boundary complexity | all | Medium | Low to medium | Low | more vertices -> slower | Can affect clipping and fenced receiver generation. |
| `upperfloor.geojson` feature count | all | High | Medium to high | Medium | more buildings -> slower | Legacy merges buildings; NM5 uses building obstacles and heights. |
| Building polygon vertex count | all | Medium | Medium | Medium | more vertices -> slower | Simplifying buildings can help, but over-simplification changes shielding. |
| Building height fields | NM5 | High | Low | None | richer heights -> similar runtime | Important for acoustic correctness; not a major runtime knob. Legacy ignores heights. |
| `roads.geojson` road count | all | High | High | Medium | more sources -> slower | Directly affects source generation and propagation. |
| Road geometry vertex count | all | Medium | Medium | Medium | more vertices -> slower | Segment simplification can improve runtime but changes source geometry. |
| `car_traffic_daily`, `truck_traffic_daily` | all | High | Low | None | larger values -> similar runtime | Affects emitted levels, not the amount of computation. |
| `max_speed` | all | Medium to high | Low | None | larger values -> similar runtime | Affects emissions. No material runtime change. |
| `traffic_settings_adjustable` | all | Medium | Low | None | true -> similar runtime | Changes whether request speed/quota modifies the road. |
| Rail feature count | all | Medium to high | Medium to high | Medium | more rail -> slower | NM5 rail has extra railway emission setup before propagation. |
| Rail traffic fields | all | Medium to high | Low | None | richer data -> similar runtime | Affects rail emissions more than runtime. |
| `dem.geojson` point count | NM5, `nm5_full` | Medium to high | Very high | Very high | more points -> slower | Ignored by legacy. Required by `nm5_full`. |
| `dem.geojson` vertical quality | NM5, `nm5_full` | Medium to high | None to low | None | better z -> similar runtime | Quality matters; point count is the runtime driver. |
| `ground_absorption.geojson` feature count | `nm5_full` | Medium | Medium | Medium | more polygons -> slower | Required by `nm5_full`; ignored by legacy and compatibility propagation. |
| `G` values | `nm5_full` | Medium | None | None | value changes -> similar runtime | Changes absorption, not compute size. |
| `atmospheric_settings` row count | `nm5_full` | Medium | Low to medium | Low | more periods -> slower | Required by `nm5_full`. Result normalization chooses one output period, default `D`. |
| `source_directivity` row count | `nm5_full` | Low to medium | Low to medium | Low | more rows -> slower | Only affects propagation when source rows reference matching `DIR_ID`. |

## Request-Level Parameter Matrix

| Parameter | Engines | Result impact | Runtime impact | Direction | Notes |
| --- | --- | --- | --- | --- | --- |
| `noise_engine=legacy` | all selection | High | Usually fastest | legacy -> faster | Old 2D path, no DEM/ground/weather/native NM5 full contract. |
| `noise_engine=nm5` | all selection | High | Medium | compatibility -> faster than full | Uses NM5 runner but fewer full-mode propagation features. |
| `noise_engine=nm5_full` | all selection | High | High to very high | full -> slower | Richer inputs, receiver fencing, DEM, ground absorption, atmospheric settings, exposed propagation controls. |
| `result_format=geojson` | all | None | Low | usually faster | Avoids PNG rasterization, but returns larger vector payloads. |
| `result_format=png` | all | None to low | Low to medium | rasterization -> slower | Adds clipping/rasterization and base64 output. |
| `png_style=raw` | all PNG | Display only | Low | raw -> slightly faster | Grayscale idiso burn. |
| `png_style=palette` | all PNG | Display only | Low | palette -> slightly slower | Adds RGBA rendering and legend metadata. |
| `max_speed` | all | Medium to high | Low | value change -> similar runtime | Affects road emission levels. |
| `traffic_quota` | all | High | Low | value change -> similar runtime | Affects traffic counts and levels. |
| `wall_absorption` | all | Medium | Low | value change -> similar runtime | Affects propagation behavior. Legacy only overrides when the value is truthy. |

## NM5 Settings Matrix

| `nm5_settings` field | Applies to | Result impact | Runtime impact | Direction | Preview guidance | Detailed guidance |
| --- | --- | --- | --- | --- | --- | --- |
| `receiver_height` | `nm5_full` | Medium | Low | value change -> similar runtime | Keep default `4`. | Set to project requirement. |
| `max_cell_dist` | `nm5`, `nm5_full` | Medium | Medium to high | increase -> faster | Use large values such as `500-750`. | Use smaller values only if receiver detail needs it. |
| `road_width` | `nm5`, `nm5_full` | Low to medium | Low | increase -> slightly slower | Keep `1.5`. | Keep aligned with source modeling assumptions. |
| `building_buffer` | `nm5_full` | Medium | Low to medium | larger buffer -> fewer/shifted receivers | Usually leave unset. | Set only if receiver placement near buildings needs control. |
| `max_area` | `nm5`, `nm5_full` | High | Very high | increase -> faster | Use very large values, e.g. `5000-25000`. | Use lower values, e.g. `275-1000`, when quality matters. |
| `skip_cell_no_sources_minimal_distance` | `nm5_full` | Low to medium | Medium | higher skip distance can be faster | Consider for preview after benchmarking. | Use cautiously; can remove quiet-area receivers. |
| `fence_negative_buffer` | `nm5_full` | Low to medium | Low to medium | tighter fence -> faster | May help reduce edge workload. | Use only if clipping/fence behavior is understood. |
| `iso_surface_in_buildings` | `nm5_full` | Medium | Low to medium | on -> slower | Usually false/unset. | Enable only if contours inside buildings are required. |
| `export_triangles_geometries` | `nm5_full` | Debug only | Medium | on -> slower/larger output | Keep false/unset. | Enable only for diagnostics. |
| `reflection_order` | `nm5_full` | Medium to high | High to very high | increase -> slower | Use `0`. | Use `1+` only when reflections are required. |
| `max_source_distance` | `nm5_full` | High | Very high | increase -> slower | Use short distances, e.g. `150-250`. | Use `600-750+` for defensible propagation extent. |
| `max_reflection_distance` | `nm5_full` | Medium when reflections on | High when reflections on | increase -> slower | Keep low, e.g. `25-50`, or irrelevant with `reflection_order=0`. | Increase only with reflection studies. |
| `thread_number` | `nm5_full` | None | Medium to high | tune -> faster until saturation | Set relative to worker CPU, or keep `0`. | Benchmark fixed values such as `4`, `8`, `16`. |
| `diff_vertical` | `nm5_full` | Medium to high | High | on -> slower | Use `False`. | Enable when vertical diffraction matters, especially rail/terrain contexts. |
| `diff_horizontal` | `nm5_full` | Medium to high | High | on -> slower | Use `False`. | Enable for more physical propagation around obstacles. |
| `export_source_id` | `nm5_full` | Debug/traceability | Low to medium | on -> slower/larger tables | Keep false/unset. | Enable for source contribution diagnostics. |
| `humidity` | `nm5_full` | Low to medium | Low | value change -> similar runtime | Usually leave unset if atmospheric table exists. | Set only for controlled scenarios. |
| `temperature` | `nm5_full` | Low to medium | Low | value change -> similar runtime | Usually leave unset if atmospheric table exists. | Set only for controlled scenarios. |
| `favourable_occurrences` | `nm5_full` | Medium | Low | value change -> similar runtime | Leave unset. | Set according to acoustic methodology. |
| `rays_name` | `nm5_full` | Debug/output | Low to medium | on/name -> more output | Leave unset. | Use only when ray output is needed. |
| `max_error` | `nm5_full` | Medium | Medium to high | increase -> faster | Use looser values, e.g. `0.5-1.0`. | Use default `0.1` or stricter after validation. |
| `iso_classes` | `nm5`, `nm5_full` | Display/classification high | Low to medium | more classes -> slightly slower/more polygons | Keep default classes. | Adjust to reporting requirements. |
| `result_table_field` | `nm5`, `nm5_full` | High if changed | Low | value change -> similar runtime | Keep `LAEQ`. | Change only if the result table contains the desired field. |

## Legacy Settings Matrix

Legacy exposes only `wall_absorption` through the request. The rest are hard-coded.

| Legacy setting | Value | Result impact | Runtime impact | Direction if changed in code | Notes |
| --- | --- | --- | --- | --- | --- |
| `max_prop_distance` | `750` | High | Very high | increase -> slower | Similar role to NM5 source distance. |
| `max_wall_seeking_distance` | `50` | Medium | Medium | increase -> slower | Wall/obstacle search distance. |
| `road_with` | `1.5` | Low to medium | Low | increase -> slightly slower | Typo preserved from code. |
| `receiver_densification` | `2.8` | High | High | lower usually more detailed/slower | Legacy-specific receiver density control. |
| `max_triangle_area` | `275` | High | High | increase -> faster | Similar practical role to NM5 `max_area`. |
| `sound_reflection_order` | `0` | Medium to high | High | increase -> slower | Currently no reflections. |
| `sound_diffraction_order` | `0` | Medium to high | High | increase -> slower | Currently no diffraction. |
| `wall_absorption` | `0.23` default | Medium | Low | value change -> similar runtime | Request can override with `wall_absorption`, except `0` is treated as unset by legacy code. |

## Preset Interpretation

The notebook presets are best understood as runtime/quality tradeoffs:

| Preset | Intended use | Runtime expectation | Main runtime choices |
| --- | --- | --- | --- |
| `preview` | UI-speed exploratory check | Fastest NM5-full option, still needs benchmarking | `max_area=25000`, `max_source_distance=150`, no reflections/diffraction, `max_error=1.0`. |
| `smoke` | Quick mechanical validation | Measured about 162 seconds on half 10 m HafenCity package | `max_area=5000`, `max_source_distance=250`, no reflections/diffraction. |
| `fast` | Better half-area check | Slower than smoke | `max_area=2500`, `max_source_distance=400`. |
| `balanced` | More plausible half-area run | Slower | `max_area=1000`, `max_source_distance=600`, horizontal diffraction on. |
| `detailed` | Detailed half-area run | Much slower | `max_area=275`, `reflection_order=1`, vertical and horizontal diffraction on. |
| `full_area` | Full HafenCity package | Potentially hours with dense DEM | Full package, `max_area=1000`, horizontal diffraction on. |

## Recommended Starting Points

## Local Machine Tuning

For this workstation, the host reports 22 logical CPUs. The currently running worker containers were configured with a 2 CPU cgroup quota, so increasing NM5 `thread_number` alone would oversubscribe the worker and is unlikely to help.

The HafenCity notebook now has local tuning variables near the top:

```python
LOCAL_WORKER_CPUS = 10
LOCAL_NM5_THREADS = 9
RUN_SINGLE_WORKER = True
```

Practical rule:

- set Docker worker CPU limit first
- set `thread_number` to roughly `worker_cpus - 1`
- run one worker for single-job benchmarking
- use multiple workers only for throughput across several independent jobs

The runner now sends an explicit NM5 thread count even when the request omits
`nm5_settings.thread_number`: request value wins, then `NM5_THREAD_NUMBER`, then
the detected container CPU quota or host CPU count. `NM5_THREAD_RESERVE` can be
set to keep one or more CPUs free for H2/WPS/JVM overhead.

The base Docker Compose worker CPU quota is configurable with `WORKER_CPUS`; the
notebook override pins both `cpus` and `JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount`
so Java and NM5 see the same local CPU budget.

Good local benchmark candidates on this machine are `thread_number` values `1`, `2`, `4`, `8`, and `9`. The best value is not guaranteed to be the highest value because Java, WPS import/export, database work, and memory bandwidth can become bottlenecks.

### Interactive Preview

Use this when users need feedback in roughly the same class as the old legacy workflow:

```json
{
  "noise_engine": "nm5_full",
  "nm5_settings": {
    "max_cell_dist": 750,
    "max_area": 25000,
    "reflection_order": 0,
    "max_source_distance": 150,
    "max_reflection_distance": 25,
    "diff_vertical": false,
    "diff_horizontal": false,
    "max_error": 1.0
  }
}
```

Pair this with a downsampled DEM, for example 10 m or 20 m spacing, and simplified source/building geometries where acceptable.

### Detailed Batch Run

Use this only for asynchronous jobs:

```json
{
  "noise_engine": "nm5_full",
  "nm5_settings": {
    "max_cell_dist": 500,
    "max_area": 1000,
    "reflection_order": 0,
    "max_source_distance": 600,
    "max_reflection_distance": 100,
    "diff_vertical": false,
    "diff_horizontal": true,
    "max_error": 0.1
  }
}
```

For even more detailed studies, reduce `max_area`, increase `max_source_distance`, and enable reflections/diffraction only after measuring the runtime cost.
