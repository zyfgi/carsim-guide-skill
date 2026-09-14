# Estimator input and validation boundary (optional research workflow)

This is a workflow-layer contract on top of the core runtime, not a core
behavior: CarSim core reads and writes tire outputs (Fx/Fy/Fz/Kappa/Alpha) like
any other channel. These rules apply only once you enter an estimator /
machine-learning workflow and decide such channels are privileged simulator
information for your study.

Declare the estimator's hardware channels before generating data. A no-tire-force
or no-parameter-truth estimator receives only the declared observations. The
manifest, base parameters, echo, full native CSV and truth partition belong to
the evaluator; do not pass the RunData object or manifest to the model/data loader.

```python
from result_contract import load_run
from sensor_replay import replay, estimator_stream

run = load_run("run.csv", estimator_channels=["Ax", "Ay", "AVz"])
packets = replay(run.estimator_view(), {
    "accel": {"channels": ["Ax", "Ay"], "sample_hz": 100, "noise_std": 0.03},
    "gyro": {"channels": ["AVz"], "sample_hz": 100, "noise_std": 0.002},
}, seed=42)
for packet in estimator_stream(packets):
    # estimator.update(packet)  # interface to your own EKF/PINN implementation
    pass
# Separate evaluation stage can read run.evaluator_view().
```

Replay samples by causal zero-order hold, applies bias, independent Gaussian noise,
quantization, nonnegative latency with bounded uniform jitter, and packet drops.
It sorts packets by arrival time while retaining acquisition time. Noise and
quantization act on SI values. Rates above the solver sampling rate are rejected.
Packets may arrive after the simulation horizon; the consumer decides its cutoff.
Out-of-order acquisition is possible with jitter; online filters must decide
whether to discard late packets or support delayed measurements.

This is sensor impairment/replay, not a full physical IMU model: CarSim CG Ax/Ay
are not automatically off-CG accelerometer specific force. Sensor pose, lever-arm
rotational acceleration, gravity projection and frame rotation need an explicit
model when validating dual-IMU or real accelerometer algorithms.

When integrating PyTorch, construct tensors only from explicit signal keys; keep
timestamps and sensor IDs as timing metadata. Fit scalers on the training split,
split trajectories/conditions before constructing overlapping windows, and avoid
future interpolation or centered filtering for online claims. Evaluation may
align to sample time or arrival time, but must declare which. Exclude the known
standing-start Kappa transient (t < 0.5 s) only when the evaluation calls for it.

The current runner supplies data and reproducibility metadata. It does not supply
a generic PINN architecture, loss, optimizer, ground-truth parameter extraction
for all vehicles, or accuracy score. Those depend on the research hypothesis.
