import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from backend.app.config import settings
from backend.app.models import SpeakerType, TranscriptSegment

logger = logging.getLogger("raksha.backend.stt")


class BaseSTTProvider(ABC):
    """Abstract interface for Speech-to-Text streaming providers in RAKSHA.

    This interface decouples the transcription source (mock generators, local audio,
    or live cloud WebSockets like Deepgram) from the downstream manipulation detector
    and risk engine pipeline.
    """

    @abstractmethod
    async def stream_transcripts(
        self,
        session_id: str,
        input_data: Any,
        speaker: SpeakerType = SpeakerType.CALLER,
        delay_seconds: float = 0.0,
    ) -> AsyncIterator[TranscriptSegment]:
        """Stream transcript segments asynchronously.

        Args:
            session_id: The ID of the monitored call session.
            input_data: Text chunks, audio buffer, or audio stream source.
            speaker: Attributed speaker for the emitted segments.
            delay_seconds: Optional artificial delay between utterances to simulate real-time speech.

        Yields:
            TranscriptSegment instances as they are recognized.
        """
        pass


class MockSTTProvider(BaseSTTProvider):
    """Simulated Speech-to-Text provider for local testing and demonstration.

    Accepts a list of predefined text utterances (or defaults to a realistic multi-stage
    scam script) and emits them as chronological `TranscriptSegment` objects.
    Works completely offline with zero API keys.
    """

    DEFAULT_SCAM_CHUNKS: List[str] = [
        "This is Officer Miller from the Federal Police Department.",
        "An arrest warrant has been issued in your name for criminal money laundering.",
        "You have only fifteen minutes to resolve this before officers arrive.",
        "Do not disconnect this line and do not tell your family about this call.",
        "Read me the six digit security code that was just sent to your phone.",
    ]

    async def stream_transcripts(
        self,
        session_id: str,
        input_data: Optional[List[str]] = None,
        speaker: SpeakerType = SpeakerType.CALLER,
        delay_seconds: float = 0.0,
    ) -> AsyncIterator[TranscriptSegment]:
        """Yield TranscriptSegments one-by-one from the provided chunk list."""
        # Explicit test bridge behavior: drain the incoming audio chunks from the async iterator,
        # and yield deterministic simulated scam chunks for testing/simulation.
        if hasattr(input_data, "__aiter__"):
            chunk_idx = 0
            async for _audio_chunk in input_data:
                if delay_seconds > 0.0:
                    await asyncio.sleep(delay_seconds)
                if chunk_idx < len(self.DEFAULT_SCAM_CHUNKS):
                    text = self.DEFAULT_SCAM_CHUNKS[chunk_idx]
                    chunk_idx += 1
                    yield TranscriptSegment(
                        session_id=session_id,
                        speaker=speaker,
                        text=text.strip(),
                        timestamp=time.time(),
                        is_final=True,
                    )
            return

        chunks = input_data if input_data is not None else self.DEFAULT_SCAM_CHUNKS

        for text in chunks:
            if not text or not text.strip():
                continue

            if delay_seconds > 0.0:
                await asyncio.sleep(delay_seconds)

            segment = TranscriptSegment(
                session_id=session_id,
                speaker=speaker,
                text=text.strip(),
                timestamp=time.time(),
                is_final=True,
            )
            yield segment


class DeepgramSTTProvider(BaseSTTProvider):
    """Deepgram Streaming Speech-to-Text Provider (Phase 3B).

    Connects to Deepgram's live streaming WebSocket API (`wss://api.deepgram.com/v1/listen`)
    to perform real-time transcription on raw audio streams (e.g., mulaw 8000Hz from Twilio
    or linear16 PCM from microphone).

    Security:
      - Never logs or exposes the raw API key.
      - Uses settings.DEEPGRAM_API_KEY by default.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
        sample_rate: Optional[int] = None,
        encoding: Optional[str] = None,
        channels: int = 1,
        interim_results: bool = True,
    ) -> None:
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        self.model = model or settings.DEEPGRAM_MODEL
        self.language = language or settings.DEEPGRAM_LANGUAGE
        self.sample_rate = sample_rate or settings.DEEPGRAM_SAMPLE_RATE
        self.encoding = encoding or settings.DEEPGRAM_ENCODING
        self.channels = channels
        self.interim_results = interim_results

    def __repr__(self) -> str:
        masked_key = "***" if self.api_key else "None"
        return (
            f"DeepgramSTTProvider(model='{self.model}', language='{self.language}', "
            f"sample_rate={self.sample_rate}, encoding='{self.encoding}', api_key={masked_key})"
        )

    def build_websocket_url(self) -> str:
        """Construct the authenticated Deepgram listen WebSocket URL with query parameters."""
        interim_str = "true" if self.interim_results else "false"
        return (
            f"wss://api.deepgram.com/v1/listen?"
            f"model={self.model}&"
            f"language={self.language}&"
            f"encoding={self.encoding}&"
            f"sample_rate={self.sample_rate}&"
            f"channels={self.channels}&"
            f"interim_results={interim_str}&"
            f"punctuate=true&"
            f"smart_format=true"
        )

    @staticmethod
    def parse_deepgram_response(
        response_json: Dict[str, Any],
        session_id: str,
        speaker: SpeakerType = SpeakerType.CALLER,
    ) -> Optional[TranscriptSegment]:
        """Convert a Deepgram streaming JSON response into a TranscriptSegment.

        Returns None if the response contains no transcript words or text.
        """
        if not isinstance(response_json, dict):
            return None

        # Check for results payload
        channel_data = response_json.get("channel", {})
        alternatives = channel_data.get("alternatives", [])
        if not alternatives:
            return None

        primary_alt = alternatives[0]
        transcript_text = primary_alt.get("transcript", "").strip()
        if not transcript_text:
            return None

        is_final = bool(response_json.get("is_final", False))
        start_time = float(response_json.get("start", time.time()))

        detected_lang = (
            response_json.get("detected_language")
            or channel_data.get("detected_language")
            or primary_alt.get("language")
        )
        detected_langs = (
            primary_alt.get("languages", [])
            or response_json.get("detected_languages", [])
        )
        if detected_lang and not detected_langs:
            detected_langs = [detected_lang]
        elif detected_langs and not detected_lang:
            detected_lang = detected_langs[0]

        return TranscriptSegment(
            session_id=session_id,
            speaker=speaker,
            text=transcript_text,
            timestamp=start_time if start_time > 0 else time.time(),
            is_final=is_final,
            detected_language=detected_lang,
            detected_languages=detected_langs,
        )

    async def stream_transcripts(
        self,
        session_id: str,
        input_data: Any,
        speaker: SpeakerType = SpeakerType.CALLER,
        delay_seconds: float = 0.0,
    ) -> AsyncIterator[TranscriptSegment]:
        """Stream audio chunks to Deepgram WebSocket and yield TranscriptSegments."""
        if not self.api_key:
            raise ValueError(
                "DEEPGRAM_API_KEY is required to stream transcripts with Deepgram. "
                "Please configure DEEPGRAM_API_KEY in .env or switch to STT_PROVIDER=mock."
            )

        try:
            import websockets
        except ImportError as err:
            raise RuntimeError(
                "The 'websockets' package is required for Deepgram streaming. "
                "Please install it using: pip install websockets"
            ) from err

        ws_url = self.build_websocket_url()
        headers = {"Authorization": f"Token {self.api_key}"}

        try:
            async with websockets.connect(ws_url, extra_headers=headers) as ws:
                # Task to stream raw audio bytes into Deepgram
                async def send_audio_stream() -> None:
                    try:
                        if hasattr(input_data, "__aiter__"):
                            async for chunk in input_data:
                                if isinstance(chunk, (bytes, bytearray)):
                                    await ws.send(chunk)
                                    if delay_seconds > 0:
                                        await asyncio.sleep(delay_seconds)
                        elif isinstance(input_data, (list, tuple)):
                            for chunk in input_data:
                                if isinstance(chunk, (bytes, bytearray)):
                                    await ws.send(chunk)
                                    if delay_seconds > 0:
                                        await asyncio.sleep(delay_seconds)
                        # Send close frame
                        await ws.send(json.dumps({"type": "CloseStream"}))
                    except Exception as exc:
                        logger.error("Error streaming audio frames to Deepgram: %s", exc)

                sender_task = asyncio.create_task(send_audio_stream())

                try:
                    async for raw_message in ws:
                        try:
                            msg_dict = json.loads(raw_message)
                            segment = self.parse_deepgram_response(
                                msg_dict, session_id=session_id, speaker=speaker
                            )
                            if segment:
                                yield segment
                        except json.JSONDecodeError:
                            continue
                finally:
                    if not sender_task.done():
                        sender_task.cancel()

        except Exception as exc:
            logger.error("Deepgram WebSocket streaming connection failed: %s", exc)
            raise RuntimeError(
                f"Deepgram streaming connection error: {exc}. "
                f"Ensure internet connectivity and valid DEEPGRAM_API_KEY."
            ) from exc


class SarvamSTTProvider(BaseSTTProvider):
    """Sarvam AI Real-Time Multilingual Speech-to-Text Provider.

    Connects to Sarvam's live streaming WebSocket API (`wss://api.sarvam.ai/speech-to-text-realtime/ws`)
    to perform real-time multilingual and code-mixed transcription (Hindi, Kannada, Telugu, Tamil,
    Malayalam, Marathi, Bengali, Gujarati, Punjabi, Odia, English).

    Security:
      - Never logs or exposes the raw API key.
      - Uses settings.SARVAM_API_KEY by default.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        language_code: Optional[str] = None,
        sample_rate: Optional[int] = None,
        encoding: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or settings.SARVAM_API_KEY
        self.model = model or settings.SARVAM_STT_MODEL
        self.language_code = language_code or settings.SARVAM_LANGUAGE_CODE
        self.sample_rate = sample_rate or settings.SARVAM_SAMPLE_RATE
        self.encoding = encoding or settings.SARVAM_ENCODING

    def __repr__(self) -> str:
        masked_key = "***" if self.api_key else "None"
        return (
            f"SarvamSTTProvider(model='{self.model}', language_code='{self.language_code}', "
            f"sample_rate={self.sample_rate}, encoding='{self.encoding}', api_key={masked_key})"
        )

    def build_websocket_url(self) -> str:
        """Construct the authenticated Sarvam real-time STT WebSocket URL with query parameters."""
        return (
            f"wss://api.sarvam.ai/speech-to-text-realtime/ws?"
            f"model={self.model}&"
            f"language_code={self.language_code}&"
            f"sample_rate={self.sample_rate}&"
            f"encoding={self.encoding}"
        )

    @staticmethod
    def parse_sarvam_response(
        response_json: Dict[str, Any],
        session_id: str,
        speaker: SpeakerType = SpeakerType.CALLER,
    ) -> Optional[TranscriptSegment]:
        """Convert a Sarvam streaming JSON response into a TranscriptSegment.

        Returns None if the response contains no transcript words or text.
        """
        if not isinstance(response_json, dict):
            return None

        # Extract transcript text from Sarvam payload
        transcript_text = (
            response_json.get("transcript")
            or response_json.get("text")
            or response_json.get("data", {}).get("transcript")
            or ""
        )
        if isinstance(transcript_text, str):
            transcript_text = transcript_text.strip()
        else:
            transcript_text = ""

        if not transcript_text:
            return None

        is_final = bool(response_json.get("is_final", True))
        timestamp = float(response_json.get("timestamp", time.time()))

        detected_lang = (
            response_json.get("language_code")
            or response_json.get("detected_language")
            or response_json.get("data", {}).get("language_code")
        )
        detected_langs = response_json.get("detected_languages", [])
        if detected_lang and not detected_langs:
            detected_langs = [detected_lang]
        elif detected_langs and not detected_lang:
            detected_lang = detected_langs[0]

        return TranscriptSegment(
            session_id=session_id,
            speaker=speaker,
            text=transcript_text,
            timestamp=timestamp if timestamp > 0 else time.time(),
            is_final=is_final,
            detected_language=detected_lang,
            detected_languages=detected_langs,
        )

    async def stream_transcripts(
        self,
        session_id: str,
        input_data: Any,
        speaker: SpeakerType = SpeakerType.CALLER,
        delay_seconds: float = 0.0,
    ) -> AsyncIterator[TranscriptSegment]:
        """Stream audio chunks to Sarvam WebSocket and yield TranscriptSegments."""
        if not self.api_key:
            raise ValueError(
                "SARVAM_API_KEY is required to stream transcripts with Sarvam. "
                "Please configure SARVAM_API_KEY in .env or switch to STT_PROVIDER=mock."
            )

        try:
            import websockets
        except ImportError as err:
            raise RuntimeError(
                "The 'websockets' package is required for Sarvam streaming. "
                "Please install it using: pip install websockets"
            ) from err

        ws_url = self.build_websocket_url()
        headers = {"api-subscription-key": self.api_key}

        try:
            async with websockets.connect(ws_url, extra_headers=headers) as ws:
                async def send_audio_stream() -> None:
                    try:
                        if hasattr(input_data, "__aiter__"):
                            async for chunk in input_data:
                                if isinstance(chunk, (bytes, bytearray)):
                                    await ws.send(chunk)
                                    if delay_seconds > 0:
                                        await asyncio.sleep(delay_seconds)
                        elif isinstance(input_data, (list, tuple)):
                            for chunk in input_data:
                                if isinstance(chunk, (bytes, bytearray)):
                                    await ws.send(chunk)
                                    if delay_seconds > 0:
                                        await asyncio.sleep(delay_seconds)
                        await ws.send(json.dumps({"type": "CloseStream"}))
                    except Exception as exc:
                        logger.error("Error streaming audio frames to Sarvam: %s", exc)

                sender_task = asyncio.create_task(send_audio_stream())

                try:
                    async for raw_message in ws:
                        try:
                            msg_dict = json.loads(raw_message)
                            segment = self.parse_sarvam_response(
                                msg_dict, session_id=session_id, speaker=speaker
                            )
                            if segment:
                                yield segment
                        except json.JSONDecodeError:
                            continue
                finally:
                    if not sender_task.done():
                        sender_task.cancel()

        except Exception as exc:
            logger.error("Sarvam WebSocket streaming connection failed: %s", exc)
            raise RuntimeError(
                f"Sarvam streaming connection error: {exc}. "
                f"Ensure internet connectivity and valid SARVAM_API_KEY."
            ) from exc


def get_stt_provider(mode: Optional[str] = None) -> BaseSTTProvider:
    """Factory to retrieve the active STT provider.

    Resolution order:
      1. Explicit 'mode' argument ('mock', 'deepgram', or 'sarvam').
      2. Environment / settings.STT_PROVIDER.
      3. Error validation for missing API keys or invalid provider names.
    """
    selected_mode = (mode or settings.STT_PROVIDER or "mock").lower().strip()

    if selected_mode == "mock":
        return MockSTTProvider()
    elif selected_mode == "deepgram":
        if not settings.DEEPGRAM_API_KEY:
            raise ValueError(
                "STT_PROVIDER is configured as 'deepgram', but DEEPGRAM_API_KEY is not set. "
                "Please configure DEEPGRAM_API_KEY in your .env or set STT_PROVIDER=mock."
            )
        return DeepgramSTTProvider(api_key=settings.DEEPGRAM_API_KEY)
    elif selected_mode == "sarvam":
        if not settings.SARVAM_API_KEY:
            raise ValueError(
                "STT_PROVIDER is configured as 'sarvam', but SARVAM_API_KEY is not set. "
                "Please configure SARVAM_API_KEY in your .env or set STT_PROVIDER=mock."
            )
        return SarvamSTTProvider(api_key=settings.SARVAM_API_KEY)
    else:
        raise ValueError(
            f"Unsupported STT provider '{selected_mode}'. "
            f"Supported providers are 'mock', 'deepgram', and 'sarvam'."
        )


# Global default instances
mock_stt_provider = MockSTTProvider()
