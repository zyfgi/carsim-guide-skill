"""Seeded causal sensor packets; timestamps and all signal values are SI.

At acquisition time use the latest solver sample (zero-order hold). Delivery
latency and bounded jitter never permit delivery before acquisition. Packet
drops remove whole packets. No interpolation or backward fill from the future.
"""
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from result_contract import no_truth_channels


@dataclass(frozen=True)
class SensorConfig:
    channels: list
    sample_hz: float
    latency_s: float = 0.0
    noise_std: float = 0.0
    bias: float = 0.0
    quantization: float = 0.0
    jitter_s: float = 0.0
    drop_probability: float = 0.0

    def __post_init__(self):
        no_truth_channels(self.channels)
        if not self.channels or "Time" in self.channels or len(set(self.channels)) != len(self.channels):
            raise ValueError("Sensor channels must be unique signal names")
        values = (self.sample_hz, self.latency_s, self.noise_std, self.bias,
                  self.quantization, self.jitter_s, self.drop_probability)
        if not all(math.isfinite(x) for x in values):
            raise ValueError("Sensor settings must be finite")
        if self.sample_hz <= 0 or min(self.latency_s, self.noise_std, self.quantization, self.jitter_s) < 0:
            raise ValueError("Positive sample rate and nonnegative noise/timing/quantization required")
        if not 0 <= self.drop_probability <= 1:
            raise ValueError("drop_probability must be in [0, 1]")


def replay(observable, sensors, seed):
    """Return a packet table per sensor, sorted by delivery time.

    Each group has shared noise/bias/quantization settings; split groups when
    units or sensor precision differ. Seed and sorted group order are stable.
    """
    no_truth_channels(observable.columns)
    times = observable["Time"].to_numpy(dtype=float)
    if len(times) < 2 or not np.isfinite(times).all() or not (np.diff(times) > 0).all():
        raise ValueError("Replay requires finite strictly increasing Time")
    result = {}
    seeds = np.random.SeedSequence(seed).spawn(len(sensors))
    for (name, settings), child_seed in zip(sorted(sensors.items()), seeds):
        spec = SensorConfig(**settings)
        if spec.sample_hz > 1 / np.max(np.diff(times)) + 1e-6:
            raise ValueError("Sensor rate exceeds available solver samples")
        rng = np.random.default_rng(child_seed)
        count = int(np.floor((times[-1] - times[0]) * spec.sample_hz + 1e-9)) + 1
        acquired = times[0] + np.arange(count) / spec.sample_hz
        indices = np.searchsorted(times, acquired, side="right") - 1
        values = observable.loc[:, spec.channels].to_numpy(dtype=float)[indices]
        if not np.isfinite(values).all():
            raise ValueError("Replay input contains NaN/inf")
        values = values + spec.bias + rng.normal(0, spec.noise_std, size=values.shape)
        if spec.quantization:
            values = np.round(values / spec.quantization) * spec.quantization
        delay = np.maximum(0, spec.latency_s + rng.uniform(-spec.jitter_s, spec.jitter_s, count))
        packets = pd.DataFrame(values, columns=spec.channels)
        packets.insert(0, "sample_time_s", acquired)
        packets.insert(1, "arrival_time_s", acquired + delay)
        keep = rng.random(count) >= spec.drop_probability
        result[name] = packets.loc[keep].sort_values("arrival_time_s", kind="stable").reset_index(drop=True)
    return result


def estimator_stream(packets):
    """Yield independent sensor packets in delivery order, with no truth data."""
    events = []
    for sensor, frame in sorted(packets.items()):
        for row in frame.to_dict("records"):
            events.append({"sensor": sensor, **row})
    yield from sorted(events, key=lambda e: e["arrival_time_s"])
