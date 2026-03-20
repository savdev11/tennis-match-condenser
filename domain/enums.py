from enum import Enum


class CaptureState(str, Enum):
    IDLE = "IDLE"
    RECORDING = "RECORDING"
    PAUSED_WITHIN_POINT = "PAUSED_WITHIN_POINT"


def normalize_capture_state(value: CaptureState | str | None) -> CaptureState:
    if isinstance(value, CaptureState):
        return value
    try:
        return CaptureState(str(value))
    except ValueError:
        return CaptureState.IDLE
