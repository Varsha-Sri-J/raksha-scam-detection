import asyncio
import json
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models import (
    ManipulationCategory,
    RiskTier,
    SpeakerType,
    TranscriptSegment,
    WSMessage,
    WSMessageType,
)
from backend.app.services.connection_manager import manager
from backend.app.services.pipeline import streaming_pipeline
from backend.app.services.session_store import session_store
from ai.classifier import semantic_classifier


@pytest.fixture(scope="module", autouse=True)
def init_classifier():
    """Ensure semantic classifier is initialized for WebSocket pipeline tests."""
    semantic_classifier.initialize()


# --- Test 1: WebSocket Connection and Initial Session Snapshot ---


def test_ws_connection_and_initial_snapshot(client: TestClient):
    """Verify WebSocket client connects and receives initial SESSION_STATUS with baseline risk."""
    session_id = "test-ws-init-snapshot-01"
    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        init_msg = websocket.receive_json()
        assert init_msg["type"] == WSMessageType.SESSION_STATUS.value
        session_data = init_msg["data"]["session"]
        assert session_data["session_id"] == session_id
        assert session_data["status"] == "ACTIVE"
        assert session_data["latest_risk"]["overall_score"] == 0.0
        assert session_data["latest_risk"]["risk_tier"] == "SAFE"


# --- Test 2: Session Isolation ---


def test_ws_session_isolation(client: TestClient):
    """Verify events in session A are never received by a client in session B."""
    session_a = "test-ws-isolation-a"
    session_b = "test-ws-isolation-b"

    with client.websocket_connect(f"/ws/call/{session_a}") as ws_a:
        with client.websocket_connect(f"/ws/call/{session_b}") as ws_b:
            # Drain initial SESSION_STATUS
            ws_a.receive_json()
            ws_b.receive_json()

            # Send scam utterance to session A
            ws_a.send_json({
                "type": WSMessageType.TRANSCRIPT_UPDATE.value,
                "data": {
                    "speaker": "CALLER",
                    "text": "This is Officer Miller from the Federal Police. An arrest warrant has been issued.",
                    "is_final": True,
                },
            })

            # Session A receives TRANSCRIPT_UPDATE, TACTIC_DETECTED, RISK_UPDATE
            msg_a1 = ws_a.receive_json()
            assert msg_a1["type"] == WSMessageType.TRANSCRIPT_UPDATE.value
            assert msg_a1["data"]["segment"]["session_id"] == session_a

            msg_a2 = ws_a.receive_json()
            assert msg_a2["type"] == WSMessageType.TACTIC_DETECTED.value
            assert msg_a2["data"]["session_id"] == session_a

            msg_a3 = ws_a.receive_json()
            assert msg_a3["type"] == WSMessageType.RISK_UPDATE.value
            assert msg_a3["data"]["risk"]["session_id"] == session_a

            # Verify Session B can still send and receive its own PING without receiving Session A events
            ws_b.send_json({"type": WSMessageType.PING.value})
            msg_b = ws_b.receive_json()
            assert msg_b["type"] == WSMessageType.PONG.value
            assert msg_b["data"]["reply"] == "pong"


# --- Test 3: Multiple Clients on One Session ---


def test_ws_multiple_clients_same_session(client: TestClient):
    """Verify multiple clients connected to the same session receive broadcasted events."""
    session_id = "test-ws-multi-client"

    with client.websocket_connect(f"/ws/call/{session_id}") as ws1:
        with client.websocket_connect(f"/ws/call/{session_id}") as ws2:
            # Drain initial messages
            ws1.receive_json()
            ws2.receive_json()

            # Send utterance via client 1
            ws1.send_json({
                "type": WSMessageType.TRANSCRIPT_UPDATE.value,
                "data": {
                    "speaker": "CALLER",
                    "text": "Your account is compromised. Transfer your funds now.",
                    "is_final": True,
                },
            })

            # Both ws1 and ws2 must receive TRANSCRIPT_UPDATE
            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()
            assert msg1["type"] == WSMessageType.TRANSCRIPT_UPDATE.value
            assert msg2["type"] == WSMessageType.TRANSCRIPT_UPDATE.value
            assert msg1["data"]["segment"]["text"] == msg2["data"]["segment"]["text"]


# --- Test 4: Event Delivery Sequence (Transcript -> Tactic -> Risk -> Alert) ---


def test_ws_event_delivery_sequence(client: TestClient):
    """Verify events are emitted in strict chronological order when a critical scam is detected."""
    session_id = "test-ws-event-sequence"

    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        # Drain initial SESSION_STATUS
        websocket.receive_json()

        # Send multi-tactic critical scam phrase
        websocket.send_json({
            "type": WSMessageType.TRANSCRIPT_UPDATE.value,
            "data": {
                "speaker": "CALLER",
                "text": (
                    "This is Officer Miller from the Federal Police. "
                    "An arrest warrant has been issued in your name for criminal money laundering. "
                    "You have only fifteen minutes to resolve this. "
                    "Do not tell your family. Read me the six digit security code right now."
                ),
                "is_final": True,
            },
        })

        # Event 1: TRANSCRIPT_UPDATE
        e1 = websocket.receive_json()
        assert e1["type"] == WSMessageType.TRANSCRIPT_UPDATE.value
        assert "segment" in e1["data"]

        # Event 2: TACTIC_DETECTED
        e2 = websocket.receive_json()
        assert e2["type"] == WSMessageType.TACTIC_DETECTED.value
        assert len(e2["data"]["tactics"]) > 0

        # Event 3: RISK_UPDATE
        e3 = websocket.receive_json()
        assert e3["type"] == WSMessageType.RISK_UPDATE.value
        assert e3["data"]["risk"]["overall_score"] >= 75.0

        # Event 4: ALERT_TRIGGERED (score >= 75 / HIGH/CRITICAL)
        e4 = websocket.receive_json()
        assert e4["type"] == WSMessageType.ALERT_TRIGGERED.value
        assert e4["data"]["session_id"] == session_id
        assert e4["data"]["risk_tier"] in ["HIGH", "CRITICAL"]


# --- Test 5: Simulation Triggering Live WebSocket Events ---


def test_ws_simulation_streaming(client: TestClient):
    """Verify triggering simulation via REST broadcasts live events to an open WebSocket."""
    session_id = "test-ws-sim-streaming"

    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        # Drain initial SESSION_STATUS
        websocket.receive_json()

        # Trigger simulation via REST
        resp = client.post(
            f"/api/sessions/{session_id}/simulate",
            json={
                "chunks": [
                    "This is Officer Miller from the Federal Police.",
                ],
                "delay_seconds": 0.0,
            },
        )
        assert resp.status_code == 200

        # Receive streamed events
        msg_transcript = websocket.receive_json()
        assert msg_transcript["type"] == WSMessageType.TRANSCRIPT_UPDATE.value

        msg_tactic = websocket.receive_json()
        assert msg_tactic["type"] == WSMessageType.TACTIC_DETECTED.value

        msg_risk = websocket.receive_json()
        assert msg_risk["type"] == WSMessageType.RISK_UPDATE.value
        assert msg_risk["data"]["risk"]["overall_score"] > 0.0


# --- Test 6: Dead Socket Pruning ---


@pytest.mark.asyncio
async def test_dead_socket_pruning():
    """Verify dead/broken sockets are pruned from manager during broadcast without errors."""
    session_id = "test-dead-socket-prune"

    class BrokenWebSocket:
        async def send_text(self, text: str):
            raise RuntimeError("Connection reset by peer")

    class WorkingWebSocket:
        def __init__(self):
            self.received = []

        async def send_text(self, text: str):
            self.received.append(text)

    broken_ws = BrokenWebSocket()
    working_ws = WorkingWebSocket()

    # Manually add to manager's active_connections
    async with manager._lock:
        manager.active_connections[session_id] = {broken_ws, working_ws}

    assert await manager.get_connection_count(session_id) == 2

    # Broadcast an event
    msg = WSMessage(type=WSMessageType.PING, data={"test": "pruning"})
    await manager.broadcast_session(session_id, msg)

    # Broken socket should be pruned, working socket preserved
    assert await manager.get_connection_count(session_id) == 1
    assert working_ws in manager.active_connections[session_id]
    assert len(working_ws.received) == 1

    # Clean up
    async with manager._lock:
        manager.active_connections.pop(session_id, None)


# --- Test 7: Malformed Input and Error Handling ---


def test_ws_malformed_input_handling(client: TestClient):
    """Verify WebSocket handles invalid JSON, non-dict payloads, and invalid fields gracefully."""
    session_id = "test-ws-malformed-input"

    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        # Drain initial SESSION_STATUS
        websocket.receive_json()

        # 1. Send invalid JSON string
        websocket.send_text("this is not valid json")
        err1 = websocket.receive_json()
        assert err1["type"] == WSMessageType.ERROR.value
        assert "Invalid JSON format" in err1["data"]["error"]

        # 2. Send non-object JSON (e.g. string)
        websocket.send_text('"just a string"')
        err2 = websocket.receive_json()
        assert err2["type"] == WSMessageType.ERROR.value
        assert "JSON payload must be an object" in err2["data"]["error"]

        # 3. Send non-object 'data' field
        websocket.send_json({
            "type": WSMessageType.TRANSCRIPT_UPDATE.value,
            "data": "not a dict",
        })
        err3 = websocket.receive_json()
        assert err3["type"] == WSMessageType.ERROR.value
        assert "Field 'data' must be an object" in err3["data"]["error"]

        # 4. Send empty text
        websocket.send_json({
            "type": WSMessageType.TRANSCRIPT_UPDATE.value,
            "data": {"text": "   "},
        })
        err4 = websocket.receive_json()
        assert err4["type"] == WSMessageType.ERROR.value
        assert "Field 'text' must be a non-empty string" in err4["data"]["error"]

        # 5. Send unsupported message type
        websocket.send_json({
            "type": "UNKNOWN_ACTION",
            "data": {},
        })
        err5 = websocket.receive_json()
        assert err5["type"] == WSMessageType.ERROR.value
        assert "Unsupported message type" in err5["data"]["error"]

        # 6. Verify connection is still healthy with PING
        websocket.send_json({"type": WSMessageType.PING.value})
        pong = websocket.receive_json()
        assert pong["type"] == WSMessageType.PONG.value


# --- Test 8: Disconnect Cleanup ---


def test_ws_disconnect_cleanup(client: TestClient):
    """Verify WebSocket disconnect removes connection from manager."""
    session_id = "test-ws-disconnect-cleanup"

    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        websocket.receive_json()
        # Active connections should be 1
        assert session_id in manager.active_connections
        assert len(manager.active_connections[session_id]) == 1

    # After exiting with block, socket is disconnected
    assert session_id not in manager.active_connections


# --- Test 9: Benign Conversation Behavior ---


def test_ws_benign_conversation_no_alert(client: TestClient):
    """Verify friendly/benign conversation never triggers ALERT_TRIGGERED over WebSocket."""
    session_id = "test-ws-benign-conversation"

    with client.websocket_connect(f"/ws/call/{session_id}") as websocket:
        websocket.receive_json()

        websocket.send_json({
            "type": WSMessageType.TRANSCRIPT_UPDATE.value,
            "data": {
                "speaker": "CALLER",
                "text": "Hi grandma, how are the flowers in your garden doing?",
                "is_final": True,
            },
        })

        # Expect TRANSCRIPT_UPDATE
        m1 = websocket.receive_json()
        assert m1["type"] == WSMessageType.TRANSCRIPT_UPDATE.value

        # Expect RISK_UPDATE (score 0.0, SAFE)
        m2 = websocket.receive_json()
        assert m2["type"] == WSMessageType.RISK_UPDATE.value
        assert m2["data"]["risk"]["overall_score"] == 0.0
        assert m2["data"]["risk"]["risk_tier"] == "SAFE"

        # Verify no ALERT_TRIGGERED is received by sending PING
        websocket.send_json({"type": WSMessageType.PING.value})
        m3 = websocket.receive_json()
        assert m3["type"] == WSMessageType.PONG.value


# --- Test 10: Mock STT and Simulation Compatibility ---


@pytest.mark.asyncio
async def test_mock_stt_simulation_compatibility():
    """Verify MockSTTProvider runs seamlessly through pipeline without external services."""
    session_id = "test-mock-stt-compat"
    results = await streaming_pipeline.run_simulation(
        session_id=session_id,
        chunks=["First test chunk", "Second test chunk"],
        broadcast=False,
    )
    assert len(results) == 2
    assert results[0]["segment"].text == "First test chunk"
    assert results[1]["segment"].text == "Second test chunk"
