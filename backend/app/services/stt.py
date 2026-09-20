import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional

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
        input_data: any,
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
    """Deepgram Streaming STT Provider (Interface / Stub for Phase 3B).

    Phase 3B will activate live streaming audio over WebSockets using Deepgram Nova-2.
    Expected parameters:
      - api_key: Deepgram API credentials (via settings.DEEPGRAM_API_KEY).
      - encoding: Audio encoding format (e.g. 'mulaw' for Twilio or 'linear16' for raw PCM).
      - sample_rate: Audio sampling frequency (e.g. 8000 for Twilio phone streams, 16000 for mic).
      - channels: 1 (mono) or 2 (dual-channel caller/callee diarization).

    To plug in during Phase 3B:
      Implement the WebSocket handshake with `wss://api.deepgram.com/v1/listen`,
      stream binary audio frames from Twilio/mic, parse returned JSON transcript
      words/alternatives, and yield `TranscriptSegment` instances.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        sample_rate: int = 8000,
        encoding: str = "mulaw",
        channels: int = 1,
    ) -> None:
        self.api_key = api_key
        self.sample_rate = sample_rate
        self.encoding = encoding
        self.channels = channels
        self._is_connected = False

    async def stream_transcripts(
        self,
        session_id: str,
        input_data: any,
        speaker: SpeakerType = SpeakerType.CALLER,
        delay_seconds: float = 0.0,
    ) -> AsyncIterator[TranscriptSegment]:
        """Stub implementation for Phase 3A. Raises NotImplementedError until Phase 3B."""
        raise NotImplementedError(
            "DeepgramSTTProvider is scheduled for activation in Phase 3B. "
            "Please use MockSTTProvider for Phase 3A streaming simulation."
        )
        if False:
            yield TranscriptSegment(session_id=session_id, text="")


# Global default mock provider instance
mock_stt_provider = MockSTTProvider()
