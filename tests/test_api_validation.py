import pytest


@pytest.fixture
def qa_session_id():
    return "qa-validation-session"


def _create_session(client, session_id):
    response = client.post(
        "/api/sessions",
        json={
            "session_id": session_id,
            "caller_id": "caller-123",
            "callee_id": "callee-456",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_missing_required_segment_field_returns_422(client, qa_session_id):
    _create_session(client, qa_session_id)

    response = client.post(
        f"/api/sessions/{qa_session_id}/segments",
        json={"speaker": "CALLER"},
    )

    assert response.status_code == 422
    assert "text" in response.text.lower()


def test_invalid_segment_data_types_return_422(client, qa_session_id):
    _create_session(client, qa_session_id)

    response = client.post(
        f"/api/sessions/{qa_session_id}/segments",
        json={"speaker": "CALLER", "text": 123},
    )

    assert response.status_code == 422
    assert "text" in response.text.lower()

    bad_speaker = client.post(
        f"/api/sessions/{qa_session_id}/segments",
        json={"speaker": "NOT_A_SPEAKER", "text": "hello"},
    )
    assert bad_speaker.status_code == 422


def test_empty_string_and_very_long_transcripts_are_processed(client, qa_session_id):
    _create_session(client, qa_session_id)

    empty_response = client.post(
        f"/api/sessions/{qa_session_id}/segments",
        json={"speaker": "CALLER", "text": "   "},
    )
    assert empty_response.status_code == 200
    assert empty_response.json()["text"] == "   "

    long_text = "Please hold for verification. " * 500
    long_response = client.post(
        f"/api/sessions/{qa_session_id}/segments",
        json={"speaker": "CALLEE", "text": long_text},
    )
    assert long_response.status_code == 200
    assert long_response.json()["text"] == long_text


def test_nonexistent_session_ids_return_404(client):
    missing_session = "ghost-session"

    get_response = client.get(f"/api/sessions/{missing_session}")
    assert get_response.status_code == 404
    assert "not found" in get_response.json()["detail"].lower()

    segment_response = client.post(
        f"/api/sessions/{missing_session}/segments",
        json={"speaker": "CALLER", "text": "hello"},
    )
    assert segment_response.status_code == 404
    assert "not found" in segment_response.json()["detail"].lower()

    end_response = client.post(f"/api/sessions/{missing_session}/end")
    assert end_response.status_code == 404
    assert "not found" in end_response.json()["detail"].lower()


def test_invalid_session_operations_and_completed_session_state(client, qa_session_id):
    _create_session(client, qa_session_id)

    end_response = client.post(f"/api/sessions/{qa_session_id}/end")
    assert end_response.status_code == 200
    assert end_response.json()["status"] == "ENDED"

    segment_after_end = client.post(
        f"/api/sessions/{qa_session_id}/segments",
        json={"speaker": "CALLER", "text": "This is after the session ended."},
    )
    assert segment_after_end.status_code == 200

    fetched = client.get(f"/api/sessions/{qa_session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "ENDED"

    repeat_end = client.post(f"/api/sessions/{qa_session_id}/end")
    assert repeat_end.status_code == 200
    assert repeat_end.json()["status"] == "ENDED"


def test_duplicate_session_ids_and_unexpected_fields_are_handled(client):
    first = client.post(
        "/api/sessions",
        json={"session_id": "qa-duplicate", "caller_id": "caller-a"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/sessions",
        json={"session_id": "qa-duplicate", "caller_id": "caller-b", "unexpected": "value"},
    )
    assert second.status_code == 201

    fetched = client.get("/api/sessions/qa-duplicate")
    assert fetched.status_code == 200
    assert fetched.json()["caller_id"] == "caller-b"

    unexpected_fields = client.post(
        "/api/sessions",
        json={"session_id": "qa-unexpected", "caller_id": "caller-c", "unknown_field": "ignore-me"},
    )
    assert unexpected_fields.status_code == 201
    assert unexpected_fields.json()["session_id"] == "qa-unexpected"


def test_malformed_json_and_non_object_requests_are_rejected(client, qa_session_id):
    _create_session(client, qa_session_id)

    malformed = client.post(
        f"/api/sessions/{qa_session_id}/segments",
        content="not-valid-json",
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code in {400, 422}

    list_payload = client.post(
        f"/api/sessions/{qa_session_id}/segments",
        json=["not", "a", "dict"],
    )
    assert list_payload.status_code == 422

    invalid_status = client.get("/api/sessions?status_filter=INVALID_STATUS")
    assert invalid_status.status_code == 422
