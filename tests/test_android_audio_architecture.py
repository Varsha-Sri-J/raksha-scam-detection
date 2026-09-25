# Tests for Android Audio Capture Architecture and Platform Boundaries.

import pytest
from android.audio_capture import (
    AudioFormatConfig,
    AndroidAudioFrame,
    AudioSourceType,
    CaptureMode,
    get_platform_capability_boundary,
)


def test_android_audio_format_config():
    config = AudioFormatConfig()
    assert config.sample_rate == 8000
    assert config.encoding== "mulaw"
    assert config.channels == 1


def test_android_audio_frame_structure():
    frame = AndroidAudioFrame(
        session_id="session-android-001",
        sequence_number=1,
        payload_base64="dGVzdF9hdWppb19kYXRh",
        source_type=AudioSourceType.MIC,
        capture_mode=CaptureMode.CARRIER_BRIDGE,
    )
    assert frame.session_id == "session-android-001"
    assert frame.source_type == AudioSourceType.MIC



def test_android_unprivileged_third_party_boundary():
    boundary = get_platform_capability_boundary(is_default_dialer=False, is_system_app=False)
    assert boundary.supports_two_sided_cellular_capture is False
    assert boundary.recommended_capture_mode == CaptureMode.CARRIER_BRIDGE
    assert "Android API 28+" in boundary.limitation_notice


def test_android_privileged_dialer_boundary():
    boundary = get_platform_capability_boundary(is_default_dialer=True, is_system_app=False)
    assert boundary.supports_two_sided_cellular_capture is True
    assert boundary.recommended_capture_mode == CaptureMode.INCALL_SERVICE
