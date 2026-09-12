# CarSim Dataset (.par) Syntax Templates

## 0. Read this warning first: thin-parsfile direct reads are falsified

The solver **cannot** recursively parse raw database datasets (raw .par files contain GUI-only decorations, see §7; testing showed a deterministic segfault at the hanging-damper dataset). Therefore:

- **Do not** hand-write a thin parsfile that references a vehicle assembly and feed it to the solver;
- **Do not** write your own "expander" to clean raw datasets (fixing one error uncovers the next).

The templates in this file have exactly three legitimate uses:
1. **Reading** the dataset blocks inside GUI-generated Run_all.par / echo files (debugging, parameter checks);
2. Knowing what each keyword block means when editing/cloning database datasets via the **GUI or MCP tools**;
3. When writing override.par (see SKILL.md §3), knowing which dataset each underlying keyword comes from and what is being overridden.

## 1. Run Control (top-level thin parsfile — the raw material for GUI-generated bases)

```text
PARSFILE
#VEHICLECODE Ind_Ind
symbol_push  <<vehicle>> 0        ! GUI symbol stack (metadata; solver ignores, but DB files carry it)
symbol_push  <<unit>> 0
symbol_push  <<axle>> 0
symbol_push  <<id_run>> MY_RUN_1
OPT_ALL_WRITE 0
IOBJECT 0
IUNIT 0
IVEHICLE 0
OPT_INT_METHOD 0                  ! integrator selection
PARSFILE <DATADIR>\Animator\Cameras\Camera_<id>.par    ! camera (keep it: avoids animator errors)
PARSFILE <DATADIR>\Vehicles\Assembly\Vehicle_<id>.par  ! vehicle assembly (→ suspension/tires/powertrain/sprung mass)
PARSFILE <project dir>\proc.par                        ! procedure
Title My Run <MY>
END
```

In the GUI: clone a Run Control, swap the vehicle/procedure links, click **Run Math Model** — that expands to `Results\Run_<uuid>\Run_all.par` (the base).

## 2. Procedure

```text
PARSFILE
OPT_INIT_PATH 1            ! initialize along the path
OPT_STOP 1                 ! stop by time
SSTART 0
TSTART 0
TSTOP 65.0
OPT_DIRECTION 0            ! forward
*SPEED 50                  ! initial-speed hint (km/h, GUI use; actual initial speed comes from the speed table's first row)

! -- control injection area: closed-loop speed controller / path follower, or links to external datasets --
! (see §3, §4 — or override directly in override.par, see SKILL.md §3)

PARSFILE <DATADIR>\Control\Driver\StrDM_<id>.par      ! closed-loop steering driver (omit if unused)
PARSFILE <DATADIR>\Control\Braking\PbkCon_<id>.par    ! braking (constant 0 MPa)
PARSFILE <DATADIR>\Roads\3D_Road\Road_<id>.par        ! road
PARSFILE <DATADIR>\Animator\Cameras\Camera_<id>.par   ! camera
END
```

## 3. Closed-loop speed controller dataset (Speed Target table)

```text
PARSFILE
#FullDataName Control: Speed Target`My Profile`MY
INSTALL_SPEED_CONTROLLER
OPT_SC 1                       ! 1 = table-driven; 3 = constant target (with SPEED_TARGET_CONSTANT)
SET_ISPEED_FOR_ID 0
SPEED_ID_SC SPEED_TARGET_ID
SPEED_TARGET_COMBINE ADD
SPEED_TARGET_S_CONSTANT 0
OPT_BK_SC 1                    ! allow the speed controller to brake
OPT_SC_ENGINE_BRAKING 0        ! set 1 for EVs that should prefer regen on decel
SPEED_KI 0                     ! controller gains below (field-tuned, working values)
SPEED_KP 0.1
VLOW_STOP -1
BK_PERF_SC 0.00098
FPD_PERF_SC 0.1
PBK_CON_MAX_SC 0.1
SPEED_KP3 0
SPEED_TARGET_TABLE LINEAR_FLAT ! rows: time s, target speed km/h; initial speed = first row
0.00, 0.00
17.00, 54.00
ENDTABLE
END
```

When overriding inside override.par, you normally only need `OPT_SC 1 + SPEED_TARGET_COMBINE ADD + SPEED_TARGET_TABLE` (other parameters are inherited from the base; the full parameter set above is for building a dataset from scratch).

## 4. Path-follower driver (LTARG lateral-offset table)

```text
SET_ILTARG_FOR_ID 0
INSTALL_DM_PATH_FOLLOWER
OPT_DM 3                       ! path-follower mode
INSTALL_DM_IMPORTS
LTARG_TABLE SPLINE_FLAT        ! rows: station s, lateral offset m
0.0, 0.00
210.0, 1.70
340.0, 0.00
ENDTABLE
LTARG_ID_DM LTARG_ID
OPT_STR_BY_TRQ 0
AV_SW_MAX_DM 1200              ! steering-wheel angular velocity limit, deg/s
A_SW_MAX_DM 540                ! steering-wheel angular acceleration limit
TPREV_CONSTANT 0.75            ! preview time, s
VLOW_DM 10
```

**Warning repeated**: a same-name TABLE in an override is **row-appended**, not replaced — overriding the base's steering with LTARG_TABLE concatenates the two tables into a phantom target (observed in testing). Use open-loop `STEER_SW_TABLE` for steering overrides only.

## 5. Segment-Builder road (straight + arc sequences)

Path segments dataset (`Path: Segment Builder`):

```text
PARSFILE
#FullDataName Path: Segment Builder`My Gentle Curves`MY
SET_IPATH_FOR_ID 0
OPT_PATH_START 0
OPT_PATH_LOOP 0
SPATH_START 0
PATH_ID_DM = PATH_ID
NSEGMENTS 5
IPATHSEG 1
SEGMENT_TYPE 0                 ! 0 = straight
SEGMENT_LENGTH 400.000
IPATHSEG 2
SEGMENT_TYPE 3                 ! 3 = arc
SEGMENT_RADIUS 250.000         ! positive = left turn
SEGMENT_ARC 392.699082         ! arc length = |heading change rad| × radius
! ... subsequent segments follow the same pattern
END
```

Road dataset (`Road: 3D Surface`, wrapping path segments + friction):

```text
PARSFILE
#FullDataName Road: 3D Surface`My Road (mu 0.9)`MY
SET_IROAD_FOR_ID 0
CURRENT_ROAD_ID = ROAD_ID
PARSFILE <project dir>\roadseg.par            ! the path segments above
ROAD_PATH_ID = PATH_ID
PARSFILE <DATADIR>\Roads\Friction\RdMu_<id>.par   ! friction dataset
RR_SURF_CONSTANT 1
END
```

Recommended curve radius ≥ 200 m (ordinary-driving-level lateral acceleration). XY polyline roads (`Roads\XY_Table\`, `DEFINE_XY_TABLES` + `SEGMENT_XY_TABLE` with rows `X, Y, s`) allow freer shapes — compute the polyline points in Python first, then generate.

## 6. Numeric parameter overrides (load / inertia / tires — write into override.par)

```text
M_SU 1134            ! sprung mass, kg
IZZ_SU 1343.1        ! sprung yaw inertia, kg·m²
LX_CG_SU 1040        ! CG to front axle, mm
H_CG_SU 540          ! CG height, mm
Y_CG_SU 150          ! lateral CG offset, mm, left positive (base default 0)
RRE(1,1) 287.0       ! effective rolling radius, mm; 1,1=FL 1,2=FR 2,1=RL 2,2=RR
R0(1,1) 287.0        ! unloaded radius, mm
```

**Y_CG_SU quirk (verified in controlled A/B/C/D runs)**: the static left-right tire-load split responds exactly linearly to the value, but measures ≈2.07× the naive rigid prediction `W_total·y_CG_total/track` (the solver's own echo shows the correct total CG via `Y_CG_TL` ≈ m_SU/m_total·y_SU, so the factor is an internal implementation detail). For ground-truth lateral CG, read the `Y_CG_TL` (CALC) line from `run_echo.par` — do not invert the Fz split naively.

## 7. GUI-only decorations (what breaks direct solver reads)

These items in raw database .par files exist for the GUI and are the root cause of the "thin-parsfile direct read segfault" — skip them when reading:

- `SET_UNITS_TABLE_ROW` (per-table-row unit annotations)
- `symbol_add` / `symbol_push` / `symbol_pop` / `symbol_set` (GUI symbol-stack machinery)
- animator references (lines containing `\animator\` or `.ani`)
- `#` metadata lines (`#FullDataName`, `#BlueLink`, … — very useful for humans locating datasets; the solver ignores them)
