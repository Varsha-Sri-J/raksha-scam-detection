import json
from fastapi.testclient import TestClient
from backend.app.models import WSMessageType


def test_websocket_ping_pong(client: TestClient):
    session_id = "test-ws-session-001"
    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        # Initial message received should be SESSION_STATUS
        initial_msg = websocket.receive_json()
        assert initial_msg["type"] == WSMessageType.SESSION_STATUS.value
        assert "session" in initial_msg["data"]

        # Send PING
        websocket.send_json({"type": WSMessageType.PING.value})
        response = websocket.receive_json()
        assert response["type"] == WSMessageType.PONG.value
        assert response["data"]["reply"] == "pong"


def test_websocket_transcript_stream(client: TestClient):
    session_id = "test-ws-session-002"
    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        # Initial message
        websocket.receive_json()

        # Send transcript stream
        websocket.send_json({
            "type": WSMessageType.TRANSCRIPT_STREAM.value,
            "data": {
                "speaker": "CALLER",
                "text": "Hello, this is tech support.",
                "is_final": True,
            }
        })

        # Expect TRANSCRIPT_UPDATE or TRANSCRIPT_STREAM broadcast
        stream_event = websocket.receive_json()
        assert stream_event["type"] in [
            WSMessageType.TRANSCRIPT_STREAM.value,
            WSMessageType.TRANSCRIPT_UPDATE.value,
        ]
        assert stream_event["data"]["segment"]["text"] == "Hello, this is tech support."

        # Expect RISK_UPDATE broadcast (baseline 0.0)
        risk_event = websocket.receive_json()
        assert risk_event["type"] == WSMessageType.RISK_UPDATE.value
        assert risk_event["data"]["risk"]["overall_score"] == 0.0
        assert risk_event["data"]["risk"]["risk_tier"] == "SAFE"
