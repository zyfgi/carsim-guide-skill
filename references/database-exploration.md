# Database Exploration

Every dataset in the CarSim database (DATADIR) is a **plain-text .par file** with a `#FullDataName` identity line. Dataset filenames look like `<Type>_<UUID>.par` — **UUIDs differ per install/version/clone, so always locate by name and never hardcode them**.

## 0. The Python API (scripts/database_tools.py — read-only)

The high-frequency operations are a callable API, so an agent handles unknown
keywords without hand-writing grep. Everything here only **reads**:

```python
import sys; sys.path.insert(0, "<skill>/scripts")
import database_tools as db

db.find_datasets(datadir, "spring")            # #FullDataName search -> [{path, full_data_name, library}]
db.get_dataset_identity(path)                  # header identity dict (no UUID needed)
db.get_parsfile_links(path, datadir)           # PARSFILE refs -> [{raw, path, exists}]
db.resolve_dataset_tree(path, datadir, 3)      # external refs recorded, not followed
graph = db.build_dependency_graph(path, datadir, allow_external=False, max_depth=10)
db.format_dependency_tree(graph)               # nodes/edges + readable report
db.find_keyword(datadir, "FS_COMP_COEFFICIENT")  # which datasets define a keyword
db.search_database_text(datadir, "27 N/mm")    # case-insensitive free-text grep
db.inspect_echo_keyword("run_echo.par", "M_SU")  # actual echoed value + comment
```

CLI equivalents: `python scripts/database_tools.py find-dataset|find-keyword|search|tree|identity|echo <query> --datadir <DATADIR>`. Pass `roots=["Suspensions", ...]` to keep scans inside chosen libraries; absolute or `..` roots outside DATADIR are rejected. The graph records cycles, missing/duplicate datasets, depth limits, and external references instead of hiding them. By default an outside-DATADIR reference becomes an `external=True` node plus an `external_reference` issue but is not recursively followed. Set `allow_external=True` only after explicitly accepting that wider read scope; descendant nodes remain marked external. The legacy tree API follows the same boundary. Workflow for unknown parameters: search → confirm keyword/unit in the dataset file → override (parameters.md) → verify with `inspect_echo_keyword`.

Commands below use Git Bash syntax (in PowerShell, use `Select-String -Pattern … -Recurse` equivalents).

## 1. Find datasets by name (≈ MCP find_dataset)

```bash
# Search dataset identity lines by keyword across a library (e.g. "EV AWD", "EPA", "1200")
grep -r -i "EV AWD" "<DATADIR>/Vehicles/Assembly" --include=*.par -l

# Show a dataset's full identity (Library`Dataset name`Category)
grep -m1 "#FullDataName" "<DATADIR>/Vehicles/Assembly/Vehicle_<id>.par"
```

Main library locations:

| Directory | Contents |
|---|---|
| `Vehicles\Assembly\` | vehicle assemblies (entry point for picking a car) |
| `Vehicles\Sprung_Mass\` | sprung mass (m0/IZZ0/CG) |
| `Powertrain\` | powertrains (incl. EV/HEV battery + motors) |
| `Procedures\` | procedures |
| `Runs\` | Run Controls (vehicle + procedure + camera, three reference lines) |
| `Control\Speed_t\`, `Control\Driver\`, `Control\Braking\` | speed schedules / driver models / braking datasets |
| `Roads\` | 3D roads, XY polyline roads, friction |
| `IO_Channels\I_Channels\` | import channels (e.g. four-wheel motor torque commands) |

## 2. Inspect the assembly tree (≈ MCP resolve_assembly)

A vehicle assembly links subsystems via `PARSFILE` lines; following them recursively two or three levels reveals the whole vehicle:

```bash
# What the vehicle links directly
grep -h "PARSFILE" "<DATADIR>/Vehicles/Assembly/Vehicle_<id>.par"

# One level deeper (loop example)
for f in $(grep -h "PARSFILE" Vehicle_<id>.par | sed 's/PARSFILE *//'); do
  echo "== $f"; grep -m1 "#FullDataName" "$f"; grep -h "PARSFILE" "$f"
done
```

Note: relative paths resolve against DATADIR; powertrains keep linking into the HEV system (battery + motors) → motor datasets. To confirm which datasets a given base run actually used, read the run artifact `run_log.txt` (it lists them) rather than recursing by hand.

## 3. Read dataset parameters (≈ MCP get_dataset)

Just read the file. Scalars are `KEYWORD value`; tables are `KEYWORD <interp> … ENDTABLE` blocks; `!` starts a comment, `#` lines are GUI metadata. Block-by-block syntax is in [dataset-syntax.md](dataset-syntax.md). Quick parameter extraction:

```bash
grep -E "^(M_SU|IZZ_SU|LX_CG_SU|Y_CG_SU|H_CG_SU) " "<DATADIR>/Vehicles/Sprung_Mass/SprMass_<id>.par"
```

More recipes:

```bash
# procedures that use closed-loop speed control
grep -r -l "INSTALL_SPEED_CONTROLLER" "<DATADIR>/Procedures" --include=*.par

# friction datasets: peak friction values
grep -r -E "MU_MAX" "<DATADIR>/Roads/Friction" --include=*.par | head

# per-wheel motor-torque import channels
grep -r -l "Wheel Motors Command" "<DATADIR>/IO_Channels/I_Channels" --include=*.par

# custom-geometry roads built from the Segment Builder
grep -r -l "NSEGMENTS" "<DATADIR>/Roads" --include=*.par | head
```

Keyword → dataset-family cheat sheet (saw a keyword, need its source dataset):

| Keyword | Dataset family |
|---|---|
| `M_SU`, `IZZ_SU`, `LX_CG_SU`, `H_CG_SU`, `Y_CG_SU` | `Vehicles\Sprung_Mass\` |
| `SPEED_TARGET_TABLE` | `Control\Speed_t\` |
| `LTARG_TABLE`, `OPT_DM 3` | `Control\Driver\` (path follower) |
| `NSEGMENTS`, `SEGMENT_TYPE` | Path: Segment Builder (referenced by road datasets) |
| `MU_ROAD_CARPET`, `MU_MAX` | `Roads\Friction\` / road datasets |
| `IMPORT` channel names | `IO_Channels\I_Channels\` |

## 4. Look up keyword meaning / units (≈ MCP describe_keyword)

Three sources, fastest first:

1. **Echo files**: the `run_echo.par` of any successful run echoes "every keyword + value (with unit comments) as actually parsed by the solver" — both a lookup source and variable-verification evidence. Historical echoes live in `<DATADIR>/Results/*/*_echo.par`; your own runs write one into the scenario directory:
   ```bash
   grep -h "M_SU" "<scenario dir>/run_echo.par"
   ```
2. **Local manuals**: `<PROG>\Help\Memos\*.pdf` (VS_Commands_API, Procedures_VS_Commands, VS_SolverWrapper, …), `<PROG>\Help\Manuals\VS_SDK.pdf`.
3. **GUI**: the VS Browser shows each parameter's name/unit/range (most convenient for humans).

## 5. Switching to a new Run Control execution context (the GUI-dependent flow)

1. Find the target vehicle assembly by name (§1, confirm via `#FullDataName`).
2. In the GUI (VS Browser), open a Run Control referencing that vehicle (clone one if needed; edit the three PARSFILE links: vehicle / procedure / camera).
3. Click **Run Math Model** (or Generate Files) → get `Results\Run_<uuid>\Run_all.par` = the new base.
4. Bind that expanded Run Control (vehicle + procedure + controls + road context) by name and SHA256. Compatible scenarios can then use the override pattern without another GUI step.

## 6. MCP acceleration mapping (optional, when available)

| Task | grep approach (above) | MCP tool (if configured) |
|---|---|---|
| Find dataset | §1 | `find_dataset('name')`, `browse_library` |
| Assembly tree | §2 | `resolve_assembly(par, max_depth)` |
| Read dataset | §3 | `get_dataset(par, annotate=True)` |
| Keyword/units | §4 | `describe_keyword` (run `build_keyword_dictionary` once) |
| Clone dataset | clone in the GUI | `clone_dataset` |

**Warning**: the MCP tools `set_dataset`/`set_table`/`set_link`/`write_parsfile` **write database files directly** (leaving .bak backups). Under a read-only database convention, never call them — change parameters via override.par (no DB writes) or save explicitly in the GUI.
