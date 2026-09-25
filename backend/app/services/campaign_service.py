import asyncio
import hashlib
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.config import settings
from backend.app.models import (
    CallSession,
    CampaignRecord,
    CampaignStatus,
    LawEnforcementReport,
    ManipulationCategory,
    PrivacyMinimizedIncident,
    RiskTier,
)

logger = logging.getLogger("raksha.backend.campaign_service")


# --- Privacy-Preserving Caller Identifier Helpers ---


def normalize_phone_number(phone: Optional[str]) -> Optional[str]:
    """Normalize phone string by stripping non-dialable characters while preserving country code prefix."""
    if not phone:
        return None
    cleaned = phone.strip()
    if cleaned.lower() in {"unknown", "anonymous", "private", "unavailable", "null", "none", ""}:
        return None
    # Keep leading + and digits
    has_plus = cleaned.startswith("+")
    digits = re.sub(r"[^\d]", "", cleaned)
    if len(digits) < 5:
        return None
    return f"+{digits}" if has_plus else digits


def hash_caller_id(caller_id: Optional[str], salt: Optional[str] = None) -> Optional[str]:
    """Generate deterministic, non-reversible SHA-256 hash of normalized caller number with salt.

    Guarantees:
    - Never stores raw caller phone numbers in campaign records.
    - Uses configurable application salt to prevent rainbow table attacks.
    - Returns None for 'Unknown' or missing numbers so unknown callers never falsely match.
    """
    normalized = normalize_phone_number(caller_id)
    if not normalized:
        return None
    active_salt = salt if salt is not None else settings.CAMPAIGN_HASH_SALT
    return hashlib.sha256(f"{active_salt}:{normalized}".encode("utf-8")).hexdigest()


def mask_caller_id(caller_id: Optional[str]) -> str:
    """Mask caller number for operator UI/audit displays without exposing full digits.

    Example: '+91 98765 43210' -> '+91 987***10'
    """
    normalized = normalize_phone_number(caller_id)
    if not normalized:
        return "Unknown"
    if len(normalized) <= 6:
        return f"{normalized[:2]}***{normalized[-1:]}"
    prefix = normalized[:6]
    suffix = normalized[-2:]
    return f"{prefix}***{suffix}"


# --- Target Category & Semantic Vector Derivation ---


def derive_target_category(tactics: List[ManipulationCategory]) -> str:
    """Deterministically categorize primary scam attack vector from confirmed tactics."""
    tactic_set = set(tactics)
    if ManipulationCategory.INFORMATION_PHISHING in tactic_set:
        return "CREDENTIAL_OTP"
    if ManipulationCategory.FINANCIAL_REDIRECTION in tactic_set:
        return "FINANCIAL_REDIRECTION"
    if (
        ManipulationCategory.AUTHORITY_IMPERSONATION in tactic_set
        and ManipulationCategory.FEAR_INTIMIDATION in tactic_set
    ):
        return "AUTHORITY_EXTORTION"
    if ManipulationCategory.URGENCY in tactic_set:
        return "COERCIVE_URGENCY"
    return "GENERAL_MANIPULATION"


# --- Deterministic Mathematical Similarity Metrics ---


def jaccard_similarity(
    set_a: Set[ManipulationCategory], set_b: Set[ManipulationCategory]
) -> float:
    """Calculate Jaccard similarity index across two manipulation tactic sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection_len = len(set_a.intersection(set_b))
    union_len = len(set_a.union(set_b))
    if union_len == 0:
        return 1.0
    return round(intersection_len / union_len, 3)


def sequence_similarity(seq_a: List[str], seq_b: List[str]) -> float:
    """Calculate deterministic sequence similarity using normalized Longest Common Subsequence (LCS).

    Returns 1.0 for identical tactic progression, 0.0 for disjoint progressions.
    """
    if not seq_a and not seq_b:
        return 1.0
    if not seq_a or not seq_b:
        return 0.0

    m, n = len(seq_a), len(seq_b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs_len = dp[m][n]
    return round((2.0 * lcs_len) / (m + n), 3)


def target_similarity(target_a: str, target_b: str) -> float:
    """Categorical match on target mechanism."""
    if not target_a or not target_b:
        return 0.0
    return 1.0 if target_a == target_b else 0.0


def caller_similarity(hash_a: Optional[str], hash_b: Optional[str]) -> float:
    """Match valid caller hashes. Unknown or null caller IDs never match."""
    if not hash_a or not hash_b:
        return 0.0
    return 1.0 if hash_a == hash_b else 0.0


# --- Campaign Link Analysis Service ---


class CampaignService:
    """Privacy-minimized cross-session Campaign Link Analysis Engine (Phase 10E-1).

    Responsibilities:
    1. Extract privacy-minimized incident summaries (zero transcripts, zero audio, zero victim PII).
    2. Compute multi-factor deterministic link similarity scores ($S_{link}$).
    3. Link related high/critical incidents into campaigns or initialize new campaigns.
    4. Enforce matching safety rules (SAFE/LOW calls NEVER seed or link to campaigns).
    5. Maintain bounded in-memory registry with deterministic LRU and TTL eviction.
    6. Ensure strict per-session idempotency.
    """

    def __init__(
        self,
        salt: Optional[str] = None,
        threshold: Optional[float] = None,
        max_active: Optional[int] = None,
        ttl_seconds: Optional[float] = None,
        weights: Optional[Dict[str, float]] = None,
        max_linked_incidents: Optional[int] = None,
        escalation_min_incidents: Optional[int] = None,
    ) -> None:
        self.salt = salt if salt is not None else settings.CAMPAIGN_HASH_SALT
        # Demo/engineering calibration threshold (not a scientifically validated probability)
        self.threshold = (
            threshold if threshold is not None else settings.CAMPAIGN_MATCH_THRESHOLD
        )
        self.max_active = (
            max_active if max_active is not None else settings.CAMPAIGN_MAX_ACTIVE
        )
        self.ttl_seconds = (
            ttl_seconds if ttl_seconds is not None else settings.CAMPAIGN_TTL_SECONDS
        )
        self.max_linked_incidents = (
            max_linked_incidents
            if max_linked_incidents is not None
            else settings.CAMPAIGN_MAX_LINKED_INCIDENTS
        )
        self.escalation_min_incidents = (
            escalation_min_incidents
            if escalation_min_incidents is not None
            else settings.CAMPAIGN_ESCALATION_MIN_INCIDENTS
        )
        self.weights = weights or {
            "tactic": settings.CAMPAIGN_WEIGHT_TACTIC,
            "progression": settings.CAMPAIGN_WEIGHT_PROGRESSION,
            "target": settings.CAMPAIGN_WEIGHT_TARGET,
            "caller": settings.CAMPAIGN_WEIGHT_CALLER,
        }

        self._campaigns: Dict[str, CampaignRecord] = {}
        self._session_to_campaign: Dict[str, str] = {}
        self._ingested_session_ids: Set[str] = set()
        self._reports: Dict[str, LawEnforcementReport] = {}
        self._campaign_reports: Dict[str, str] = {}
        self._lock: Optional[asyncio.Lock] = None

    def create_incident_summary(self, session: CallSession) -> PrivacyMinimizedIncident:
        """Create privacy-minimized incident representation from session telemetry.

        Guarantees zero raw transcripts, audio, or victim PII are included.
        """
        now = session.updated_at or session.created_at or time.time()
        c_hash = hash_caller_id(session.caller_id, self.salt)
        c_masked = mask_caller_id(session.caller_id)

        tactics = (
            list(session.latest_risk.accumulated_tactics)
            if session.latest_risk
            else []
        )
        sequence = (
            [t.value for t in session.ordered_tactic_sequence]
            if session.ordered_tactic_sequence
            else [t.value for t in tactics]
        )
        target = derive_target_category(tactics)

        score = session.latest_risk.overall_score if session.latest_risk else 0.0
        tier = session.latest_risk.risk_tier if session.latest_risk else RiskTier.SAFE

        caregiver_outcome = "NOT_TRIGGERED"
        if session.notification_history:
            caregiver_outcome = session.notification_history[-1].status.value

        intervention_outcome = "NOT_TRIGGERED"
        if session.intervention_history:
            intervention_outcome = session.intervention_history[-1].status.value

        return PrivacyMinimizedIncident(
            incident_id=session.session_id,
            timestamp=now,
            caller_hash=c_hash,
            caller_masked=c_masked,
            tactic_signature=tactics,
            tactic_sequence=sequence,
            target_category=target,
            peak_risk_score=score,
            final_risk_tier=tier,
            caregiver_notification_outcome=caregiver_outcome,
            intervention_outcome=intervention_outcome,
        )

    def calculate_similarity(
        self, incident: PrivacyMinimizedIncident, campaign: CampaignRecord
    ) -> Tuple[float, Dict[str, float]]:
        """Calculate multi-signal link score between an incident and a campaign."""
        # 1. Tactic similarity (Jaccard)
        s_tactic = jaccard_similarity(
            set(incident.tactic_signature), set(campaign.dominant_tactics)
        )

        # 2. Progression similarity (max LCS against known campaign variants)
        s_progression = 0.0
        if campaign.linked_incidents:
            prog_scores = [
                sequence_similarity(incident.tactic_sequence, inc.tactic_sequence)
                for inc in campaign.linked_incidents
            ]
            s_progression = max(prog_scores)
        else:
            s_progression = 1.0 if not incident.tactic_sequence else 0.0

        # 3. Target category similarity
        s_target = 1.0 if incident.target_category in campaign.target_categories else 0.0

        # 4. Caller similarity (matches any known caller hash in campaign)
        s_caller = 0.0
        if incident.caller_hash:
            known_hashes = {
                inc.caller_hash
                for inc in campaign.linked_incidents
                if inc.caller_hash
            }
            if incident.caller_hash in known_hashes:
                s_caller = 1.0

        sub_scores = {
            "tactic": s_tactic,
            "progression": s_progression,
            "target": s_target,
            "caller": s_caller,
        }

        total_score = (
            self.weights["tactic"] * s_tactic
            + self.weights["progression"] * s_progression
            + self.weights["target"] * s_target
            + self.weights["caller"] * s_caller
        )

        return round(total_score, 3), sub_scores

    def find_matching_campaign(
        self, incident: PrivacyMinimizedIncident
    ) -> Tuple[Optional[CampaignRecord], float]:
        """Find highest-scoring campaign matching the incident above the threshold."""
        best_campaign: Optional[CampaignRecord] = None
        best_score = 0.0

        for campaign in self._campaigns.values():
            score, _ = self.calculate_similarity(incident, campaign)
            if score >= self.threshold and score > best_score:
                best_score = score
                best_campaign = campaign

        return best_campaign, best_score

    def ingest_incident(
        self, incident: PrivacyMinimizedIncident
    ) -> Optional[Tuple[CampaignRecord, float, bool]]:
        """Evaluate an incident for campaign linking or seeding.

        Returns:
            Tuple of (CampaignRecord, link_score, is_new_campaign) or None if ineligible.
        """
        # Safety Rule (Hardened): ONLY HIGH or CRITICAL incidents can seed OR link to a campaign.
        # SAFE, LOW, and MEDIUM must return None and must not affect campaign records.
        if incident.final_risk_tier not in {RiskTier.HIGH, RiskTier.CRITICAL}:
            logger.info(
                "Incident %s in %s tier ignored for campaign matching under safety rule",
                incident.incident_id,
                incident.final_risk_tier.value,
            )
            return None

        # Check existing campaigns for a match
        matching_campaign, link_score = self.find_matching_campaign(incident)

        if matching_campaign:
            # Link to existing campaign
            matching_campaign.last_seen = max(
                matching_campaign.last_seen, incident.timestamp
            )
            matching_campaign.incident_count += 1
            matching_campaign.linked_incidents.append(incident)
            # Memory cap: Retain only the most recent N incident summaries
            if len(matching_campaign.linked_incidents) > self.max_linked_incidents:
                matching_campaign.linked_incidents = matching_campaign.linked_incidents[
                    -self.max_linked_incidents :
                ]

            # Update dominant tactics & target categories
            all_tactics: Set[ManipulationCategory] = set(
                matching_campaign.dominant_tactics
            )
            all_tactics.update(incident.tactic_signature)
            matching_campaign.dominant_tactics = sorted(
                list(all_tactics), key=lambda x: x.value
            )

            if incident.target_category not in matching_campaign.target_categories:
                matching_campaign.target_categories.append(incident.target_category)

            if (
                incident.caller_masked != "Unknown"
                and incident.caller_masked
                not in matching_campaign.observed_caller_identifiers
            ):
                matching_campaign.observed_caller_identifiers.append(
                    incident.caller_masked
                )

            # Update risk metrics
            matching_campaign.highest_risk_score = max(
                matching_campaign.highest_risk_score, incident.peak_risk_score
            )
            new_total = (
                matching_campaign.average_risk_score
                * (matching_campaign.incident_count - 1)
            ) + incident.peak_risk_score
            matching_campaign.average_risk_score = round(
                new_total / matching_campaign.incident_count, 1
            )

            tier_val = incident.final_risk_tier.value
            matching_campaign.risk_tier_distribution[tier_val] = (
                matching_campaign.risk_tier_distribution.get(tier_val, 0) + 1
            )

            # Advance status:
            # - If count >= self.escalation_min_incidents -> ESCALATION_ELIGIBLE (unless already REPORT_GENERATED)
            # - Else if count >= 2 -> ACTIVE_MONITORING
            if matching_campaign.status != CampaignStatus.REPORT_GENERATED:
                if matching_campaign.incident_count >= self.escalation_min_incidents:
                    matching_campaign.status = CampaignStatus.ESCALATION_ELIGIBLE
                elif matching_campaign.incident_count >= 2:
                    matching_campaign.status = CampaignStatus.ACTIVE_MONITORING

            self._session_to_campaign[incident.incident_id] = (
                matching_campaign.campaign_id
            )
            logger.info(
                "Linked incident %s to campaign %s (link_score=%.3f, count=%d, status=%s)",
                incident.incident_id,
                matching_campaign.campaign_id,
                link_score,
                matching_campaign.incident_count,
                matching_campaign.status.value,
            )
            return matching_campaign, link_score, False

        # No match found: Only HIGH or CRITICAL incidents can seed a NEW campaign
        if incident.final_risk_tier not in {RiskTier.HIGH, RiskTier.CRITICAL}:
            logger.info(
                "Incident %s in %s tier did not match existing campaign and is ineligible to seed a new campaign",
                incident.incident_id,
                incident.final_risk_tier.value,
            )
            return None

        # Seed new campaign
        campaign_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"
        callers = (
            [incident.caller_masked]
            if incident.caller_masked != "Unknown"
            else []
        )
        new_campaign = CampaignRecord(
            campaign_id=campaign_id,
            status=CampaignStatus.DETECTED,
            first_seen=incident.timestamp,
            last_seen=incident.timestamp,
            incident_count=1,
            linked_incidents=[incident],
            observed_caller_identifiers=callers,
            dominant_tactics=list(incident.tactic_signature),
            target_categories=[incident.target_category],
            average_risk_score=incident.peak_risk_score,
            highest_risk_score=incident.peak_risk_score,
            risk_tier_distribution={incident.final_risk_tier.value: 1},
        )

        # Enforce memory limits before inserting
        self._enforce_memory_limit()

        self._campaigns[campaign_id] = new_campaign
        self._session_to_campaign[incident.incident_id] = campaign_id
        logger.info(
            "Created new campaign %s for incident %s (tier=%s, score=%.1f)",
            campaign_id,
            incident.incident_id,
            incident.final_risk_tier.value,
            incident.peak_risk_score,
        )
        return new_campaign, 1.0, True

    async def ingest_session(
        self, session: CallSession
    ) -> Optional[Tuple[CampaignRecord, float, bool]]:
        """Ingest a completed or finalized CallSession into the campaign engine.

        Guarantees strict idempotency: a session is processed at most once.
        """
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if session.session_id in self._ingested_session_ids:
                existing_cid = self._session_to_campaign.get(session.session_id)
                if existing_cid and existing_cid in self._campaigns:
                    return self._campaigns[existing_cid], 1.0, False
                return None

            self._ingested_session_ids.add(session.session_id)
            incident = self.create_incident_summary(session)
            return self.ingest_incident(incident)

    def _enforce_memory_limit(self) -> None:
        """Evict oldest/least-recently-used campaigns when ceiling is exceeded."""
        self.prune_expired_campaigns()
        while len(self._campaigns) >= self.max_active:
            # Deterministic LRU eviction based on oldest last_seen
            oldest_id = min(
                self._campaigns.keys(),
                key=lambda cid: self._campaigns[cid].last_seen,
            )
            rep_id = self._campaign_reports.pop(oldest_id, None)
            if rep_id:
                self._reports.pop(rep_id, None)
            del self._campaigns[oldest_id]
            logger.info("Evicted LRU campaign %s to maintain bounded memory", oldest_id)

    def prune_expired_campaigns(self, now: Optional[float] = None) -> int:
        """Prune campaigns inactive longer than TTL window."""
        current_time = now if now is not None else time.time()
        expired = [
            cid
            for cid, c in self._campaigns.items()
            if current_time - c.last_seen > self.ttl_seconds
        ]
        for cid in expired:
            rep_id = self._campaign_reports.pop(cid, None)
            if rep_id:
                self._reports.pop(rep_id, None)
            del self._campaigns[cid]
        if expired:
            logger.info("Pruned %d expired campaigns beyond TTL window", len(expired))
        return len(expired)

    def evaluate_escalation(self, campaign: CampaignRecord) -> bool:
        """Check if campaign meets or exceeds the escalation threshold."""
        if campaign.incident_count >= self.escalation_min_incidents:
            if campaign.status != CampaignStatus.REPORT_GENERATED:
                campaign.status = CampaignStatus.ESCALATION_ELIGIBLE
            return True
        return False

    def generate_law_enforcement_report(self, campaign_id: str) -> LawEnforcementReport:
        """Generate a privacy-minimized mock law-enforcement report for an eligible campaign.

        Strictly idempotent: returns existing report if one was already generated.
        Guarantees zero transcripts, zero audio, zero victim PII, and only masked caller identifiers.
        """
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            raise KeyError(f"Campaign {campaign_id} not found")

        # Idempotency check: if report already exists for this campaign, return it
        existing_report_id = self._campaign_reports.get(campaign_id)
        if existing_report_id and existing_report_id in self._reports:
            return self._reports[existing_report_id]

        # Verify eligibility
        if campaign.incident_count < self.escalation_min_incidents:
            raise ValueError(
                f"Campaign {campaign_id} has {campaign.incident_count} incidents; "
                f"minimum {self.escalation_min_incidents} required for law-enforcement escalation"
            )

        report_id = f"RAKSHA-NCRP-{uuid.uuid4().hex[:8].upper()}"
        linked_incident_ids = [inc.incident_id for inc in campaign.linked_incidents]

        # Attack progression summary (unique chronological tactic progression across incidents)
        progression: List[str] = []
        for inc in campaign.linked_incidents:
            for t in inc.tactic_sequence:
                if t not in progression:
                    progression.append(t)

        escalation_reason = (
            f"Campaign contains {campaign.incident_count} linked HIGH/CRITICAL incidents "
            f"and crossed the configured campaign escalation threshold of {self.escalation_min_incidents}."
        )

        # Deterministic SHA-256 integrity hash of campaign intelligence fields
        integrity_hasher = hashlib.sha256()
        integrity_hasher.update(
            f"{campaign.campaign_id}:{campaign.incident_count}:{campaign.highest_risk_score}:{campaign.average_risk_score}".encode("utf-8")
        )
        for inc_id in sorted(linked_incident_ids):
            integrity_hasher.update(inc_id.encode("utf-8"))
        integrity_hash = integrity_hasher.hexdigest()

        report = LawEnforcementReport(
            report_id=report_id,
            campaign_id=campaign.campaign_id,
            generated_at=time.time(),
            campaign_status=CampaignStatus.REPORT_GENERATED,
            incident_count=campaign.incident_count,
            first_seen=campaign.first_seen,
            last_seen=campaign.last_seen,
            observed_caller_identifiers=list(campaign.observed_caller_identifiers),
            dominant_tactics=list(campaign.dominant_tactics),
            target_categories=list(campaign.target_categories),
            risk_tier_distribution=dict(campaign.risk_tier_distribution),
            highest_risk_score=campaign.highest_risk_score,
            average_risk_score=campaign.average_risk_score,
            attack_progression_summary=progression,
            linked_incident_ids=linked_incident_ids,
            escalation_reason=escalation_reason,
            status="MOCK_REPORT_GENERATED",
            disclaimer="DEMO ONLY — NO ACTUAL TRANSMISSION TO LAW ENFORCEMENT",
            integrity_hash=integrity_hash,
        )

        campaign.status = CampaignStatus.REPORT_GENERATED
        self._reports[report_id] = report
        self._campaign_reports[campaign_id] = report_id

        logger.info(
            "Generated mock law-enforcement report %s for campaign %s (incidents=%d, integrity=%s)",
            report_id,
            campaign_id,
            campaign.incident_count,
            integrity_hash[:8],
        )
        return report

    def get_report_by_campaign(self, campaign_id: str) -> Optional[LawEnforcementReport]:
        """Retrieve existing report for a campaign if generated."""
        report_id = self._campaign_reports.get(campaign_id)
        if report_id:
            return self._reports.get(report_id)
        return None

    def get_report(self, report_id: str) -> Optional[LawEnforcementReport]:
        """Retrieve report by report ID."""
        return self._reports.get(report_id)

    def get_campaign(self, campaign_id: str) -> Optional[CampaignRecord]:
        """Retrieve campaign by ID."""
        return self._campaigns.get(campaign_id)

    def list_campaigns(self) -> List[CampaignRecord]:
        """List all active campaigns sorted by last_seen descending."""
        return sorted(
            list(self._campaigns.values()),
            key=lambda c: c.last_seen,
            reverse=True,
        )

    def clear(self) -> None:
        """Reset all in-memory campaign data for test teardown."""
        self._campaigns.clear()
        self._session_to_campaign.clear()
        self._ingested_session_ids.clear()
        self._reports.clear()
        self._campaign_reports.clear()


# Global singleton instance
campaign_service = CampaignService()
