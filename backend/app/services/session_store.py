import asyncio
import time
from typing import Dict, List, Optional
from backend.app.models import (
    CallSession,
    CaregiverContact,
    InterventionRecord,
    NotificationRecord,
    ProtectionDecision,
    RiskAssessment,
    SessionStatus,
    TranscriptSegment,
    UserWarningRecord,
    UserWarningStatus,
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
        caregiver_contacts: Optional[List[CaregiverContact]] = None,
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
                caregiver_contacts=caregiver_contacts or [],
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

    async def update_user_warning_status(
        self,
        session_id: str,
        warning_id: str,
        status: UserWarningStatus,
        error: Optional[str] = None,
    ) -> Optional[UserWarningRecord]:
        """Update the status of a specific user warning record matching warning_id.

        Enforces deterministic correlation: only updates the record if warning_id
        strictly matches. Never updates by position or timing.
        """
        if not warning_id:
            return None

        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            for rec in session.user_warning_history:
                if rec.warning_id == warning_id:
                    rec.status = status
                    if error is not None:
                        rec.error = error
                    session.updated_at = time.time()
                    return rec
            return None

    MAX_INTERVENTION_HISTORY: int = 100

    async def add_intervention_record(
        self, session_id: str, record: InterventionRecord
    ) -> Optional[InterventionRecord]:
        """Append an intervention record to the session history (bounded)."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            if not any(r.intervention_id == record.intervention_id for r in session.intervention_history):
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

    async def find_session_by_conference(
        self,
        conference_name: Optional[str] = None,
        conference_sid: Optional[str] = None,
        call_sid: Optional[str] = None,
    ) -> Optional[CallSession]:
        """Deterministically look up a session by conference room name, conference SID, or call SID."""
        async with self._lock:
            # 1. Deterministic extraction from conference_name if format is raksha_conf_{session_id}
            if conference_name and conference_name.startswith("raksha_conf_"):
                derived_id = conference_name[len("raksha_conf_") :]
                if derived_id in self._sessions:
                    return self._sessions[derived_id]

            # 2. Direct session_id match
            if call_sid and call_sid in self._sessions:
                return self._sessions[call_sid]

            # 3. Targeted scan across stored sessions for child call, conference_sid, or exact name
            for s in self._sessions.values():
                if conference_sid and s.conference_sid == conference_sid:
                    return s
                if call_sid and (s.protected_user_call_sid == call_sid or s.parent_call_sid == call_sid):
                    return s
                if conference_name and s.conference_name == conference_name:
                    return s

            return None

    async def clear(self) -> None:
        """Clear all sessions (useful for test teardown)."""
        async with self._lock:
            self._sessions.clear()


# Global singleton instance
session_store = SessionStore()
