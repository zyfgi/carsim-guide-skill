"""Control-source semantics shared by CLI, Simulink and VS API routes."""
from dataclasses import dataclass

CONTROL_MODES = frozenset({
    "driver_internal", "predefined_table", "imported_signal",
    "simulink_external", "vs_api_external",
})

CONTROL_SEMANTICS = {
    "speed_target": "Driver/controller target; not a direct actuator command",
    "throttle_command": "Direct accelerator/actuator input",
    "brake_command": "Direct brake input",
    "steering_target": "Driver/path target; not road-wheel angle",
    "steering_wheel_angle": "Open-loop steering-wheel input",
    "road_wheel_angle": "Wheel state or direct low-level wheel-angle command",
    "wheel_torque_command": "Direct per-wheel drive torque input",
}


@dataclass(frozen=True)
class ControlSpec:
    """One control input with explicit coupling and physical semantics."""

    mode: str
    source: str
    semantic: str
    channel: str | None = None
    requires_closed_loop: bool = False

    def __post_init__(self) -> None:
        if self.mode not in CONTROL_MODES:
            raise ValueError(f"Unknown control mode: {self.mode}")
        if self.semantic not in CONTROL_SEMANTICS:
            raise ValueError(f"Unknown control semantic: {self.semantic}")
        external = self.mode in {"simulink_external", "vs_api_external"}
        if self.requires_closed_loop and not external:
            raise ValueError(
                "Runtime feedback requires simulink_external or vs_api_external")
        if not self.source.strip():
            raise ValueError("Control source must not be empty")


def select_external_mode(feedback_required: bool, prefer_simulink: bool = True) -> str:
    """Choose coupling class; never labels prerecorded batch data closed-loop."""
    if not feedback_required:
        return "predefined_table"
    return "simulink_external" if prefer_simulink else "vs_api_external"
