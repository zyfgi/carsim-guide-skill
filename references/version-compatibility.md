# CarSim version compatibility

`scripts/version_compatibility.py` separates detection from verification.

- `parse_version(value)` accepts an explicit release in a version string or
  install path and returns `CarSimVersion`.
- `compatibility_status(value)` reports verified evidence/features or a
  non-blocking unverified warning.
- `supports(feature, value)` is true only for a feature/version pair with
  checked-in real-run evidence.

The initial registry contains CarSim 2024.0 features supported by existing
field verification. A newer release is **detected but unverified**: keep the
explicit product version, attempt the generic path, save the warning/features
in the run manifest, and judge the actual run artifacts. Do not reject it only
because it is newer, and do not call a successful parse “compatible.”
