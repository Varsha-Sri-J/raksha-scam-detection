import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional, Tuple

import httpx

from backend.app.config import settings

logger = logging.getLogger("raksha.backend.twilio")


def get_conference_room_name(session_id: str) -> str:
    """Generate a deterministic application-level Twilio Conference name.

    Format: raksha_conf_{clean_session_id}
    Requirements:
    - No phone number, no user name, no risk information
    - Deterministic per session_id
    - Safe for Twilio conference naming and simulation-safe
    """
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    return f"raksha_conf_{clean_id}"


class TwilioService:
    """Service for handling Twilio voice webhooks, TwiML generation, and Media Stream payloads."""

    def __init__(
        self,
        auth_token: Optional[str] = None,
        validate_signature: Optional[bool] = None,
    ) -> None:
        self._auth_token = auth_token
        self._validate_signature = validate_signature

    @property
    def auth_token(self) -> Optional[str]:
        return self._auth_token if self._auth_token is not None else settings.TWILIO_AUTH_TOKEN

    @auth_token.setter
    def auth_token(self, value: Optional[str]) -> None:
        self._auth_token = value

    @property
    def validate_signature(self) -> bool:
        return (
            self._validate_signature
            if self._validate_signature is not None
            else settings.TWILIO_VALIDATE_SIGNATURE
        )

    @validate_signature.setter
    def validate_signature(self, value: Optional[bool]) -> None:
        self._validate_signature = value

    def generate_twiml_response(
        self,
        stream_url: str,
        session_id: str,
        status_callback_url: Optional[str] = None,
    ) -> str:
        """Generate standard TwiML XML to connect the call audio to a WebSocket Media Stream.

        Args:
            stream_url: The wss:// URL where Twilio should connect its Media Stream.
            session_id: The RAKSHA session ID (typically Twilio CallSid).
            status_callback_url: Optional URL for status change notifications.

        Returns:
            TwiML XML string with <?xml> declaration.
        """
        response_elem = ET.Element("Response")
        connect_elem = ET.SubElement(response_elem, "Connect")
        stream_elem = ET.SubElement(connect_elem, "Stream", {"url": stream_url})

        # Add session_id parameter so the stream endpoint knows the context
        ET.SubElement(
            stream_elem,
            "Parameter",
            {"name": "session_id", "value": session_id},
        )

        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_content = ET.tostring(response_elem, encoding="unicode")
        return xml_declaration + xml_content

    def generate_conference_twiml(
        self,
        stream_url: str,
        session_id: str,
        conference_name: str,
        status_callback_url: str,
    ) -> str:
        """Generate TwiML XML for the inbound scammer leg in Conference topology (Phase 7D-3).

        Starts an asynchronous unidirectional audio fork on inbound_track to RAKSHA STT,
        and dials the caller into the shared conference room. The scammer leg is the
        authoritative conference callback configuration.
        """
        response_elem = ET.Element("Response")

        # 1. Asynchronous non-blocking audio fork on inbound_track
        start_elem = ET.SubElement(response_elem, "Start")
        stream_elem = ET.SubElement(
            start_elem,
            "Stream",
            {"url": stream_url, "track": "inbound_track"},
        )
        ET.SubElement(
            stream_elem,
            "Parameter",
            {"name": "session_id", "value": session_id},
        )

        # 2. Authoritative Conference Bridge
        dial_elem = ET.SubElement(response_elem, "Dial")
        conf_attribs = {
            "participantLabel": "scammer",
            "statusCallback": status_callback_url,
            "statusCallbackEvent": "start end join leave announcement",
            "endConferenceOnExit": "true",
            "beep": "false",
        }
        conf_elem = ET.SubElement(dial_elem, "Conference", conf_attribs)
        conf_elem.text = conference_name

        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_content = ET.tostring(response_elem, encoding="unicode")
        return xml_declaration + xml_content

    def generate_protected_user_twiml(self, conference_name: str) -> str:
        """Generate TwiML XML for the protected user leg entering the conference room.

        Note: Does NOT duplicate conference-level callback configuration.
        """
        response_elem = ET.Element("Response")
        dial_elem = ET.SubElement(response_elem, "Dial")
        conf_elem = ET.SubElement(
            dial_elem,
            "Conference",
            {"participantLabel": "protected_user", "beep": "false"},
        )
        conf_elem.text = conference_name

        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_content = ET.tostring(response_elem, encoding="unicode")
        return xml_declaration + xml_content

    def generate_warning_twiml(self, message: str) -> str:
        """Generate TwiML XML speaking a canonical warning message to a participant.

        Uses Twilio <Say voice="Polly.Aditi" language="en-IN">.
        Delivered strictly to the participant without broadcasting to the conference.
        """
        response_elem = ET.Element("Response")
        say_elem = ET.SubElement(
            response_elem,
            "Say",
            {"voice": "Polly.Aditi", "language": "en-IN"},
        )
        say_elem.text = message

        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_content = ET.tostring(response_elem, encoding="unicode")
        return xml_declaration + xml_content

    async def create_outbound_call(
        self,
        to_phone_number: str,
        conference_name: str,
        status_callback_url: Optional[str] = None,
        from_phone_number: Optional[str] = None,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Initiate an outbound call to the protected user placing them into the conference.

        Returns:
            (success: bool, call_sid: Optional[str], error: Optional[str])
        """
        acc_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        auth_tok = auth_token or settings.TWILIO_AUTH_TOKEN
        from_number = from_phone_number or settings.TWILIO_PHONE_NUMBER

        if not acc_sid or not auth_tok or not acc_sid.strip() or not auth_tok.strip():
            logger.warning("Twilio credentials not configured; skipping outbound call")
            return False, None, "Twilio credentials not configured"

        if not from_number or not from_number.strip():
            logger.warning("TWILIO_PHONE_NUMBER not configured; skipping outbound call")
            return False, None, "Twilio from phone number not configured"

        if not to_phone_number or not to_phone_number.strip():
            logger.warning("Target to_phone_number not provided; skipping outbound call")
            return False, None, "Target phone number not provided"

        twiml_body = self.generate_protected_user_twiml(conference_name)
        url = f"https://api.twilio.com/2010-04-01/Accounts/{acc_sid}/Calls.json"
        data: Dict[str, str] = {
            "To": to_phone_number.strip(),
            "From": from_number.strip(),
            "Twiml": twiml_body,
        }
        if status_callback_url:
            data["StatusCallback"] = status_callback_url
            data["StatusCallbackEvent"] = "initiated ringing answered completed"
            data["StatusCallbackMethod"] = "POST"

        timeout = timeout_seconds or settings.TWILIO_API_TIMEOUT_SECONDS or 3.0

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    data=data,
                    auth=(acc_sid, auth_tok),
                )

            if response.status_code == 201:
                try:
                    resp_data = response.json()
                    call_sid = resp_data.get("sid")
                    logger.info("Successfully created outbound call: %s", call_sid)
                    return True, call_sid, None
                except Exception as exc:
                    logger.warning("Twilio returned HTTP 201 but invalid JSON: %s", exc)
                    return False, None, "Malformed JSON response from Twilio"

            err_msg = ""
            try:
                err_json = response.json()
                if isinstance(err_json, dict):
                    err_msg = err_json.get("message", "")
            except Exception:
                pass

            logger.warning(
                "Twilio rejected Create Call: HTTP %d%s",
                response.status_code,
                f" - {err_msg}" if err_msg else "",
            )
            return (
                False,
                None,
                f"Twilio rejected Create Call: HTTP {response.status_code}{f' - {err_msg}' if err_msg else ''}",
            )

        except httpx.TimeoutException:
            logger.warning("Twilio Create Call request timed out after %s seconds", timeout)
            return False, None, "Twilio Create Call request timed out"
        except (httpx.NetworkError, httpx.RequestError) as net_err:
            logger.warning(
                "Twilio Create Call network connection failed: %s",
                net_err.__class__.__name__,
            )
            return False, None, "Twilio network connection failed"
        except Exception as exc:
            logger.exception("Unexpected error in Twilio Create Call: %s", exc)
            return False, None, f"Twilio request failed: {str(exc)}"

    @staticmethod
    def parse_media_stream_message(raw_data: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Parse and validate an incoming Twilio Media Stream JSON message.

        Returns:
            A tuple of (event_type, payload_dict), or (None, None) if invalid JSON or missing 'event'.
        """
        try:
            msg_dict = json.loads(raw_data)
            if not isinstance(msg_dict, dict):
                return None, None
            event_type = msg_dict.get("event")
            if not event_type or not isinstance(event_type, str):
                return None, None
            return event_type, msg_dict
        except (json.JSONDecodeError, TypeError):
            return None, None

    @staticmethod
    def decode_media_payload(payload_b64: str) -> Optional[bytes]:
        """Safely decode a base64-encoded audio chunk from a Twilio 'media' event.

        Returns:
            Decoded raw audio bytes, or None if base64 decoding fails.
        """
        if not payload_b64 or not isinstance(payload_b64, str):
            return None
        try:
            return base64.b64decode(payload_b64, validate=True)
        except (binascii.Error, ValueError):
            logger.warning("Failed to decode Twilio media base64 payload")
            return None

    def verify_twilio_signature(
        self,
        url: str,
        params: Dict[str, Any],
        signature: Optional[str],
    ) -> bool:
        """Verify the X-Twilio-Signature header on an incoming webhook request.

        Uses HMAC-SHA1 as specified by Twilio:
        https://www.twilio.com/docs/usage/webhooks/webhooks-security

        Returns:
            True if signature is valid or if TWILIO_VALIDATE_SIGNATURE is disabled.
        """
        if not self.validate_signature:
            return True

        if not self.auth_token:
            logger.error("TWILIO_VALIDATE_SIGNATURE is True, but TWILIO_AUTH_TOKEN is not configured")
            return False

        if not signature:
            logger.warning("Missing X-Twilio-Signature header on protected webhook")
            return False

        # 1. Sort the POST form parameters by key alphabetically
        sorted_keys = sorted(params.keys())

        # 2. Concatenate the full request URL with the sorted key-value pairs
        data_to_sign = url
        for key in sorted_keys:
            data_to_sign += f"{key}{params[key]}"

        # 3. Compute HMAC-SHA1 using the auth token
        expected_mac = hmac.new(
            self.auth_token.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha1,
        )
        expected_signature = base64.b64encode(expected_mac.digest()).decode("utf-8")

        # 4. Constant-time comparison
        return hmac.compare_digest(expected_signature, signature)


# Global singleton instance
twilio_service = TwilioService()
