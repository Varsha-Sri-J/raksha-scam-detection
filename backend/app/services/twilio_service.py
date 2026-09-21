import base64
import binascii
import hashlib
import hmac
import json
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional, Tuple

from backend.app.config import settings

logger = logging.getLogger("raksha.backend.twilio")


class TwilioService:
    """Service for handling Twilio voice webhooks, TwiML generation, and Media Stream payloads."""

    def __init__(
        self,
        auth_token: Optional[str] = None,
        validate_signature: Optional[bool] = None,
    ) -> None:
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.validate_signature = (
            validate_signature
            if validate_signature is not None
            else settings.TWILIO_VALIDATE_SIGNATURE
        )

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
