import asyncio
import time
from typing import Dict, List, Optional
from backend.app.models import (
    CallSession,
    InterventionRecord,
    NotificationRecord,
    ProtectionDecision,
    RiskAssessment,
    SessionStatus,
    TranscriptSegment,
    UserWarningRecord,
)


class SessionStore:
    """Thread-safe in-memory session store for call sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, CallSession] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: Optional[str] = None,
        caller_id: Optional[str] = "Unknown",
        callee_id: Optional[str] = "Protected Callee",
    ) -> CallSession:
        """Create and store a new CallSession."""
        async with self._lock:
            now = time.time()
            session = CallSession(
                caller_id=caller_id,
                callee_id=callee_id,
                status=SessionStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                transcript_history=[],
                latest_risk=None,
            )
            if session_id:
                session.session_id = session_id

            self._sessions[session.session_id] = session
            return session

    async def get_session(self, session_id: str) -> Optional[CallSession]:
        """Retrieve a session by its ID."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def list_sessions(self, status: Optional[SessionStatus] = None) -> List[CallSession]:
        """List all stored sessions, optionally filtered by status."""
        async with self._lock:
            if status is None:
                return list(self._sessions.values())
            return [s for s in self._sessions.values() if s.status == status]

    async def add_transcript_segment(
        self, session_id: str, segment: TranscriptSegment
    ) -> Optional[TranscriptSegment]:
        """Append a transcript segment to the session history."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.transcript_history.append(segment)
            session.updated_at = time.time()
            return segment

    MAX_PROTECTION_HISTORY: int = 100

    async def update_risk_assessment(
        self, session_id: str, assessment: RiskAssessment
    ) -> Optional[RiskAssessment]:
        """Update the latest risk assessment for a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.latest_risk = assessment
            session.updated_at = time.time()
            return assessment

    async def add_protection_decision(
        self, session_id: str, decision: ProtectionDecision
    ) -> Optional[ProtectionDecision]:
        """Append a protection decision to the session history (bounded)."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.protection_history.append(decision)
            if len(session.protection_history) > self.MAX_PROTECTION_HISTORY:
                session.protection_history = session.protection_history[-self.MAX_PROTECTION_HISTORY :]
            session.updated_at = time.time()
            return decision

    MAX_NOTIFICATION_HISTORY: int = 100

    async def add_notification_record(
        self, session_id: str, record: NotificationRecord
    ) -> Optional[NotificationRecord]:
        """Append a notification record to the session history (bounded)."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.notification_history.append(record)
            if len(session.notification_history) > self.MAX_NOTIFICATION_HISTORY:
                session.notification_history = session.notification_history[-self.MAX_NOTIFICATION_HISTORY :]
            session.updated_at = time.time()
            return record

    MAX_USER_WARNING_HISTORY: int = 100

    async def add_user_warning_record(
        self, session_id: str, record: UserWarningRecord
    ) -> Optional[UserWarningRecord]:
        """Append a user warning record to the session history (bounded)."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.user_warning_history.append(record)
            if len(session.user_warning_history) > self.MAX_USER_WARNING_HISTORY:
                session.user_warning_history = session.user_warning_history[-self.MAX_USER_WARNING_HISTORY :]
            session.updated_at = time.time()
            return record

    MAX_INTERVENTION_HISTORY: int = 100

    async def add_intervention_record(
        self, session_id: str, record: InterventionRecord
    ) -> Optional[InterventionRecord]:
        """Append an intervention record to the session history (bounded)."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.intervention_history.append(record)
            if len(session.intervention_history) > self.MAX_INTERVENTION_HISTORY:
                session.intervention_history = session.intervention_history[-self.MAX_INTERVENTION_HISTORY :]
            session.updated_at = time.time()
            return record

    async def end_session(self, session_id: str) -> Optional[CallSession]:
        """Mark a session as ENDED."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            session.status = SessionStatus.ENDED
            session.updated_at = time.time()
            return session

    async def delete_session(self, session_id: str) -> bool:
        """Remove a session from storage."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    async def clear(self) -> None:
        """Clear all sessions (useful for test teardown)."""
        async with self._lock:
            self._sessions.clear()


# Global singleton instance
session_store = SessionStore()
