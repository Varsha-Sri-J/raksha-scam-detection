"""Android Audio Capture Architecture and Client Contract for RAKSHA.

Defines technical contracts, audio frame schemas, and platform capability boundaries.
"""

import time
import uuid 
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class AudioSourceType(str, Enum):
    MIC = "MIC"
    VOICE_RECOGNITION = "VOICE_RECOGNITION"
    VOICE_COMMUNICATION = "VOICE_COMMUNICATION"
    VOICE_CALL_RESTRICTED = "VOICE_CALL_RESTRICTED"


class CaptureMode(str, Enum):
    LOCAL_MIC = "LOCAL_MIC"
    PLAYBACK_CAPTURE = "PLAYBACK_CAPTURE"
    CARRIER_BRIDGE = "CARRIER_BRIDGE"
    INCALL_SERVICE = "INCALL_SERVICE"


class AudioFormatConfig(BaseModel):
    sample_rate: int = 8000
    encoding: str = "mulaw"
    channels: int = 1
    chunk_size_bytes: int = 160


class AndroidAudioFrame(BaseModel):
    frame_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    sequence_number: int
    payload_base64: str
    timestamp: float = Field(default_factory=time.time)
    source_type: AudioSourceType = AudioSourceType.MIC
    capture_mode: CaptureMode = CaptureMode.CARRIER_BRIDGE


class AndroidCaptureBoundary(BaseModel):
    permission_record_audio: bool = True
    permission_capture_audio_output: bool = False
    is_default_dialer: bool = False
    is_system_app: bool = False
    supports_two_sided_cellular_capture: bool = False
    recommended_capture_mode: CaptureMode = CaptureMode.CARRIER_BRIDGE
    limitation_notice: str = (
        "Standard third-party Android apps cannot capture 2-sided cellular call audio "
        "via AudioRecord due to Android API 28+ restrictions. "
        "Dual-sided telemetry is routed via Twilio PSTN gateway or InCallService."
    )


def get_platform_capability_boundary(
    is_default_dialer: bool = False,
    is_system_app: bool = False
) -> AndroidCaptureBoundary:
    if is_default_dialer or is_system_app:
        return AndroidCaptureBoundary(
            permission_record_audio=True,
            permission_capture_audio_output=True,
            is_default_dialer=is_default_dialer,
            is_system_app=is_system_app,
            supports_two_sided_cellular_capture=True,
            recommended_capture_mode=CaptureMode.INCALL_SERVICE,
            limitation_notice="Operating as privileged dialer / InCallService."
        )
    return AndroidCaptureBoundary(
        permission_record_audio=True,
        permission_capture_audio_output=False,
        is_default_dialer=False,
        is_system_app=False,
        supports_two_sided_cellular_capture=False,
        recommended_capture_mode=CaptureMode.CARRIER_BRIDGE,
    )
