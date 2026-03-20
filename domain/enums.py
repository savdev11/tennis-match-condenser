from enum import Enum


class CaptureState(str, Enum):
    IDLE = "IDLE"
    RECORDING = "RECORDING"
    PAUSED_WITHIN_POINT = "PAUSED_WITHIN_POINT"
