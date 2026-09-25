import asyncio
import time
import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app
from backend.app.models import (
    CallSession,
    CampaignRecord,
    CampaignStatus,
    CaregiverContact,
    InterventionRecord,
    InterventionStatus,
    InterventionType,
    ManipulationCategory,
    NotificationChannel,
    NotificationRecord,
    NotificationStatus,
    PrivacyMinimizedIncident,
    RiskAssessment,
    RiskTier,
    SessionStatus,
    TranscriptSegment,
)
from backend.app.services.campaign_service import (
    CampaignService,
    campaign_service,
    derive_target_category,
    hash_caller_id,
    jaccard_similarity,
    mask_caller_id,
    normalize_phone_number,
    sequence_similarity,
)


@pytest.fixture(autouse=True)
def reset_campaign_service():
    """Ensure clean campaign service state before each test."""
    campaign_service.clear()
    yield
    campaign_service.clear()


def make_test_session(
    session_id: str,
    score: float,
    tier: RiskTier,
    caller_id: str = "+91 98765 43210",
    tactics: list = None,
    ordered_sequence: list = None,
    caregiver_status: NotificationStatus = None,
    intervention_status: InterventionStatus = None,
) -> CallSession:
    """Helper to construct a deterministic CallSession for testing."""
    t_list = tactics or []
    seq_list = ordered_sequence or t_list
    session = CallSession(
        session_id=session_id,
        caller_id=caller_id,
        callee_id="Lakshmi R.",
        status=SessionStatus.ACTIVE,
        created_at=time.time(),
        updated_at=time.time(),
        ordered_tactic_sequence=seq_list,
        latest_risk=RiskAssessment(
            session_id=session_id,
            overall_score=score,
            risk_tier=tier,
            accumulated_tactics=t_list,
            triggered_tactics=[],
            explanation="Test assessment",
        ),
    )
    if caregiver_status:
        session.notification_history.append(
            NotificationRecord(
                session_id=session_id,
                channel=NotificationChannel.SMS,
                recipient="+91 91234 56789",
                message="Test alert",
                status=caregiver_status,
            )
        )
    if intervention_status:
        session.intervention_history.append(
            InterventionRecord(
                session_id=session_id,
                type=InterventionType.DISCONNECT,
                status=intervention_status,
                reason="Test acute disconnect",
            )
        )
    return session


# --- Requirement 1: First HIGH scam creates campaign ---
def test_first_high_scam_creates_campaign():
    service = CampaignService()
    session = make_test_session(
        session_id="sess_high_1",
        score=82.0,
        tier=RiskTier.HIGH,
        caller_id="+91 98765 43210",
        tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.URGENCY,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
    )
    incident = service.create_incident_summary(session)
    result = service.ingest_incident(incident)

    assert result is not None
    campaign, link_score, is_new = result
    assert is_new is True
    assert link_score == 1.0
    assert campaign.status == CampaignStatus.DETECTED
    assert campaign.incident_count == 1
    assert len(campaign.linked_incidents) == 1
    assert campaign.linked_incidents[0].incident_id == "sess_high_1"


# --- Requirement 2: First CRITICAL scam creates campaign ---
def test_first_critical_scam_creates_campaign():
    service = CampaignService()
    session = make_test_session(
        session_id="sess_crit_1",
        score=100.0,
        tier=RiskTier.CRITICAL,
        caller_id="+91 99887 76655",
        tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.URGENCY,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
    )
    incident = service.create_incident_summary(session)
    result = service.ingest_incident(incident)

    assert result is not None
    campaign, link_score, is_new = result
    assert is_new is True
    assert campaign.status == CampaignStatus.DETECTED
    assert campaign.highest_risk_score == 100.0


# --- Requirement 3 & 4: SAFE and LOW calls do NOT create campaign ---
def test_safe_call_does_not_create_campaign():
    service = CampaignService()
    session = make_test_session(
        session_id="sess_safe_1",
        score=0.0,
        tier=RiskTier.SAFE,
        caller_id="+91 98765 43210",
        tactics=[],
    )
    incident = service.create_incident_summary(session)
    result = service.ingest_incident(incident)
    assert result is None
    assert len(service.list_campaigns()) == 0


def test_low_call_does_not_create_campaign():
    service = CampaignService()
    session = make_test_session(
        session_id="sess_low_1",
        score=35.0,
        tier=RiskTier.LOW,
        caller_id="+91 98765 43210",
        tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
    )
    incident = service.create_incident_summary(session)
    result = service.ingest_incident(incident)
    assert result is None
    assert len(service.list_campaigns()) == 0


# --- Hardening: MEDIUM calls cannot seed OR link to a campaign ---
def test_medium_call_does_not_seed_or_link_campaign():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.FINANCIAL_REDIRECTION,
    ]
    caller = "+91 98765 43210"

    # 1. Verify MEDIUM call cannot seed a new campaign
    sess_med_seed = make_test_session(
        session_id="sess_med_seed",
        score=55.0,
        tier=RiskTier.MEDIUM,
        caller_id=caller,
        tactics=tactics,
    )
    res_seed = service.ingest_incident(service.create_incident_summary(sess_med_seed))
    assert res_seed is None
    assert len(service.list_campaigns()) == 0

    # 2. Seed an existing HIGH campaign
    sess_high = make_test_session(
        session_id="sess_high_seed",
        score=85.0,
        tier=RiskTier.HIGH,
        caller_id=caller,
        tactics=tactics,
    )
    res_high = service.ingest_incident(service.create_incident_summary(sess_high))
    assert res_high is not None
    campaign, _, is_new = res_high
    assert is_new is True
    assert campaign.incident_count == 1
    assert len(campaign.linked_incidents) == 1

    # 3. Attempt to link a MEDIUM incident with identical caller, tactics, and target
    sess_med_link = make_test_session(
        session_id="sess_med_link",
        score=60.0,
        tier=RiskTier.MEDIUM,
        caller_id=caller,
        tactics=tactics,
    )
    res_med_link = service.ingest_incident(service.create_incident_summary(sess_med_link))
    assert res_med_link is None

    # 4. Verify existing campaign is completely unaffected
    assert campaign.incident_count == 1
    assert len(campaign.linked_incidents) == 1
    assert campaign.average_risk_score == 85.0
    assert campaign.status == CampaignStatus.DETECTED
    assert "MEDIUM" not in campaign.risk_tier_distribution



# --- Requirement 5: Same caller + same tactics links strongly ---
def test_same_caller_same_tactics_links_strongly():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.URGENCY,
        ManipulationCategory.FINANCIAL_REDIRECTION,
    ]
    # Incident 1
    s1 = make_test_session("s1", 85.0, RiskTier.HIGH, "+91 98765 43210", tactics)
    service.ingest_incident(service.create_incident_summary(s1))

    # Incident 2 with identical caller and tactics
    s2 = make_test_session("s2", 87.0, RiskTier.HIGH, "+91 98765 43210", tactics)
    result = service.ingest_incident(service.create_incident_summary(s2))

    assert result is not None
    campaign, link_score, is_new = result
    assert is_new is False
    assert link_score == 1.0  # Perfect match across all 4 signals
    assert campaign.incident_count == 2
    assert campaign.status == CampaignStatus.ACTIVE_MONITORING


# --- Requirement 6: Different caller + same behavioral pattern can still link ---
def test_different_caller_same_behavioral_pattern_links():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.FEAR_INTIMIDATION,
        ManipulationCategory.ISOLATION_SECRECY,
        ManipulationCategory.INFORMATION_PHISHING,
    ]
    # Incident 1 with caller A
    s1 = make_test_session("s1", 95.0, RiskTier.CRITICAL, "+91 91111 22222", tactics)
    service.ingest_incident(service.create_incident_summary(s1))

    # Incident 2 with spoofed/different caller B but identical playbook
    s2 = make_test_session("s2", 98.0, RiskTier.CRITICAL, "+91 99999 88888", tactics)
    result = service.ingest_incident(service.create_incident_summary(s2))

    assert result is not None
    campaign, link_score, is_new = result
    assert is_new is False
    # Caller similarity is 0.0, but tactic (0.35) + progression (0.25) + target (0.25) = 0.85 >= 0.72
    assert link_score >= 0.80
    assert campaign.incident_count == 2


# --- Requirement 7: Same caller + completely different behavior does NOT automatically link ---
def test_same_caller_different_behavior_does_not_link():
    service = CampaignService()
    # Campaign A: Courier parcel extortion
    s1 = make_test_session(
        "s1",
        85.0,
        RiskTier.HIGH,
        "+91 98765 43210",
        [
            ManipulationCategory.URGENCY,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
    )
    res1 = service.ingest_incident(service.create_incident_summary(s1))
    cmp1_id = res1[0].campaign_id

    # Session 2: Same caller number, but completely different attack: Cybercrime police impersonation with OTP
    s2 = make_test_session(
        "s2",
        95.0,
        RiskTier.CRITICAL,
        "+91 98765 43210",
        [
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
    )
    res2 = service.ingest_incident(service.create_incident_summary(s2))

    # Should seed a separate campaign because tactics & targets are disjoint
    # Caller score is only 0.15, which is well below the 0.72 threshold
    assert res2 is not None
    cmp2_id = res2[0].campaign_id
    assert cmp1_id != cmp2_id
    assert len(service.list_campaigns()) == 2


# --- Requirement 8: Different scam campaigns remain separate ---
def test_different_scam_campaigns_remain_separate():
    service = CampaignService()
    # Campaign 1: Customs parcel scam
    s1 = make_test_session(
        "s1",
        85.0,
        RiskTier.HIGH,
        "+91 98111 11111",
        [
            ManipulationCategory.URGENCY,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
    )
    # Campaign 2: Fake CBI officer arrest scam
    s2 = make_test_session(
        "s2",
        100.0,
        RiskTier.CRITICAL,
        "+91 98222 22222",
        [
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
    )
    service.ingest_incident(service.create_incident_summary(s1))
    service.ingest_incident(service.create_incident_summary(s2))

    campaigns = service.list_campaigns()
    assert len(campaigns) == 2
    assert campaigns[0].campaign_id != campaigns[1].campaign_id


# --- Requirement 9: Similar wording but unrelated tactics does not incorrectly link ---
def test_unrelated_tactics_do_not_link():
    service = CampaignService()
    s1 = make_test_session(
        "s1",
        80.0,
        RiskTier.HIGH,
        "+91 98111 00001",
        [
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
    )
    service.ingest_incident(service.create_incident_summary(s1))

    # Completely different tactics: Cognitive overwhelm + Relief false salvation
    s2 = make_test_session(
        "s2",
        80.0,
        RiskTier.HIGH,
        "+91 98222 00002",
        [
            ManipulationCategory.CONFUSION_OVERWHELM,
            ManipulationCategory.RELIEF_FALSE_SALVATION,
        ],
    )
    service.ingest_incident(service.create_incident_summary(s2))

    assert len(service.list_campaigns()) == 2


# --- Requirement 10: Attack progression contributes to matching ---
def test_attack_progression_contributes_to_matching():
    # Sequence A: [AUTH, FEAR, URG, PHISH]
    seq_a = ["AUTHORITY_IMPERSONATION", "FEAR_INTIMIDATION", "URGENCY", "INFORMATION_PHISHING"]
    # Sequence B identical
    sim_identical = sequence_similarity(seq_a, seq_a)
    assert sim_identical == 1.0

    # Sequence C partially matching
    seq_c = ["AUTHORITY_IMPERSONATION", "URGENCY", "INFORMATION_PHISHING"]
    sim_partial = sequence_similarity(seq_a, seq_c)
    assert 0.70 < sim_partial < 1.0

    # Sequence D reversed / disjoint
    seq_d = ["FINANCIAL_REDIRECTION", "CONFUSION_OVERWHELM"]
    sim_disjoint = sequence_similarity(seq_a, seq_d)
    assert sim_disjoint == 0.0


# --- Requirement 11: Target similarity contributes to matching ---
def test_target_similarity_contributes_to_matching():
    t_otp = derive_target_category([ManipulationCategory.INFORMATION_PHISHING])
    t_fin = derive_target_category([ManipulationCategory.FINANCIAL_REDIRECTION])
    t_ext = derive_target_category([
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.FEAR_INTIMIDATION,
    ])

    assert t_otp == "CREDENTIAL_OTP"
    assert t_fin == "FINANCIAL_REDIRECTION"
    assert t_ext == "AUTHORITY_EXTORTION"


# --- Requirement 12: Unknown caller does not create false caller matches ---
def test_unknown_caller_does_not_create_false_matches():
    service = CampaignService()
    # Both callers are Unknown
    s1 = make_test_session(
        "s1",
        85.0,
        RiskTier.HIGH,
        caller_id="Unknown",
        tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION, ManipulationCategory.FINANCIAL_REDIRECTION],
    )
    s2 = make_test_session(
        "s2",
        85.0,
        RiskTier.HIGH,
        caller_id=None,
        tactics=[ManipulationCategory.FEAR_INTIMIDATION, ManipulationCategory.INFORMATION_PHISHING],
    )
    inc1 = service.create_incident_summary(s1)
    inc2 = service.create_incident_summary(s2)

    assert inc1.caller_hash is None
    assert inc2.caller_hash is None

    # Computing caller similarity for two unknown callers must yield 0.0
    from backend.app.services.campaign_service import caller_similarity
    assert caller_similarity(inc1.caller_hash, inc2.caller_hash) == 0.0


# --- Requirement 13: Session ingestion is idempotent ---
@pytest.mark.asyncio
async def test_session_ingestion_is_idempotent():
    service = CampaignService()
    session = make_test_session(
        "sess_idempotent",
        90.0,
        RiskTier.CRITICAL,
        "+91 98765 43210",
        [
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
    )
    # First ingestion creates campaign
    res1 = await service.ingest_session(session)
    assert res1 is not None
    cmp_id = res1[0].campaign_id
    assert res1[0].incident_count == 1

    # Second ingestion of the same session must return existing campaign without incrementing count
    res2 = await service.ingest_session(session)
    assert res2 is not None
    assert res2[0].campaign_id == cmp_id
    assert res2[0].incident_count == 1
    assert len(service.list_campaigns()) == 1


# --- Requirement 14: Campaign incident count increments correctly ---
def test_campaign_incident_count_increments_correctly():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.URGENCY,
        ManipulationCategory.FINANCIAL_REDIRECTION,
    ]
    s1 = make_test_session("s1", 80.0, RiskTier.HIGH, "+91 98765 43210", tactics)
    s2 = make_test_session("s2", 90.0, RiskTier.CRITICAL, "+91 98765 43210", tactics)
    s3 = make_test_session("s3", 85.0, RiskTier.HIGH, "+91 98765 43210", tactics)

    c1, _, is_new1 = service.ingest_incident(service.create_incident_summary(s1))
    assert is_new1 is True
    assert c1.incident_count == 1
    assert len(c1.linked_incidents) == 1

    c2, _, is_new2 = service.ingest_incident(service.create_incident_summary(s2))
    assert is_new2 is False
    assert c2.incident_count == 2
    assert len(c2.linked_incidents) == 2

    c3, _, is_new3 = service.ingest_incident(service.create_incident_summary(s3))
    assert is_new3 is False
    assert c3.incident_count == 3
    assert len(c3.linked_incidents) == 3


# --- Requirement 15: Campaign statistics update correctly ---
def test_campaign_statistics_update_correctly():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.URGENCY,
        ManipulationCategory.FINANCIAL_REDIRECTION,
    ]
    s1 = make_test_session("s1", 80.0, RiskTier.HIGH, "+91 98765 43210", tactics)
    s2 = make_test_session("s2", 90.0, RiskTier.CRITICAL, "+91 98765 43210", tactics)

    service.ingest_incident(service.create_incident_summary(s1))
    res = service.ingest_incident(service.create_incident_summary(s2))

    campaign = res[0]
    assert campaign.incident_count == 2
    assert campaign.highest_risk_score == 90.0
    assert campaign.average_risk_score == 85.0
    assert campaign.risk_tier_distribution == {"HIGH": 1, "CRITICAL": 1}
    assert campaign.status == CampaignStatus.ACTIVE_MONITORING


# --- Requirement 16: Campaign registry remains bounded ---
def test_campaign_registry_remains_bounded():
    # Use max_active = 3 for test
    service = CampaignService(max_active=3)
    for i in range(5):
        # Create distinctly different high scams
        s = make_test_session(
            f"sess_{i}",
            85.0,
            RiskTier.HIGH,
            f"+91 98000 0000{i}",
            [ManipulationCategory.AUTHORITY_IMPERSONATION, ManipulationCategory.values()[i % len(ManipulationCategory.values())] if hasattr(ManipulationCategory, "values") else ManipulationCategory.URGENCY],
        )
        service.ingest_incident(service.create_incident_summary(s))

    # Must be bounded by max_active
    campaigns = service.list_campaigns()
    assert len(campaigns) <= 3


# --- Hardening: Linked incident memory cap (max 50 summaries per campaign) ---
def test_linked_incident_memory_cap():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.FINANCIAL_REDIRECTION,
    ]
    caller = "+91 98765 43210"

    last_campaign = None
    # Ingest 55 linked incidents
    for i in range(55):
        s = make_test_session(
            session_id=f"sess_cap_{i}",
            score=80.0 + (i % 15),
            tier=RiskTier.HIGH,
            caller_id=caller,
            tactics=tactics,
        )
        res = service.ingest_incident(service.create_incident_summary(s))
        assert res is not None
        last_campaign = res[0]

    # 1. incident_count reflects the full count (55)
    assert last_campaign.incident_count == 55
    # 2. len(linked_incidents) <= 50 (capped at exactly 50)
    assert len(last_campaign.linked_incidents) <= 50
    assert len(last_campaign.linked_incidents) == 50
    # 3. Retained incidents are the newest ones (sess_cap_5 through sess_cap_54)
    retained_ids = [inc.incident_id for inc in last_campaign.linked_incidents]
    assert retained_ids[0] == "sess_cap_5"
    assert retained_ids[-1] == "sess_cap_54"
    assert "sess_cap_0" not in retained_ids
    assert "sess_cap_4" not in retained_ids


# --- Requirement 17: Expired campaigns can be removed ---
def test_expired_campaigns_removal():
    service = CampaignService(ttl_seconds=100.0)
    now = time.time()
    s = make_test_session(
        "s_old",
        85.0,
        RiskTier.HIGH,
        "+91 98765 43210",
        [ManipulationCategory.AUTHORITY_IMPERSONATION, ManipulationCategory.FINANCIAL_REDIRECTION],
    )
    incident = service.create_incident_summary(s)
    incident.timestamp = now - 500.0  # Simulated old timestamp
    service.ingest_incident(incident)

    assert len(service.list_campaigns()) == 1
    pruned = service.prune_expired_campaigns(now=now)
    assert pruned == 1
    assert len(service.list_campaigns()) == 0


# --- Requirement 18: No transcript/audio/raw evidence in campaign records ---
def test_privacy_invariants_no_transcripts_or_audio():
    service = CampaignService()
    session = make_test_session(
        "s_priv",
        95.0,
        RiskTier.CRITICAL,
        "+91 98765 43210",
        [ManipulationCategory.AUTHORITY_IMPERSONATION, ManipulationCategory.INFORMATION_PHISHING],
    )
    # Attach sensitive transcript segment
    session.transcript_history.append(
        TranscriptSegment(
            session_id="s_priv",
            text="My name is Lakshmi and my bank account number is 123456789",
        )
    )
    incident = service.create_incident_summary(session)
    res = service.ingest_incident(incident)
    campaign = res[0]

    # Verify PrivacyMinimizedIncident has no transcript or audio fields
    assert not hasattr(incident, "transcript")
    assert not hasattr(incident, "audio")
    assert not hasattr(incident, "text")

    # Serialize campaign record to dict and inspect for leakage
    dumped = campaign.model_dump()
    dumped_str = str(dumped)
    assert "123456789" not in dumped_str
    assert "Lakshmi" not in dumped_str
    assert "transcript" not in dumped_str


# --- Requirement 19: Caller hashing is deterministic ---
def test_caller_hashing_is_deterministic():
    salt = "test_custom_salt_123"
    h1 = hash_caller_id("+91 98765 43210", salt=salt)
    h2 = hash_caller_id("+919876543210", salt=salt)
    h3 = hash_caller_id("+91 98765-43210", salt=salt)

    assert h1 is not None
    assert h1 == h2
    assert h2 == h3

    # Different number produces different hash
    h_diff = hash_caller_id("+91 91234 56789", salt=salt)
    assert h1 != h_diff


# --- Requirement 20: Caller raw number is not stored in campaign intelligence ---
def test_caller_raw_number_is_not_stored():
    service = CampaignService()
    raw_number = "+91 98765 43210"
    session = make_test_session(
        "s_raw",
        85.0,
        RiskTier.HIGH,
        raw_number,
        [ManipulationCategory.AUTHORITY_IMPERSONATION, ManipulationCategory.FINANCIAL_REDIRECTION],
    )
    incident = service.create_incident_summary(session)
    res = service.ingest_incident(incident)
    campaign = res[0]

    # Inspect incident
    assert raw_number not in str(incident.model_dump())
    assert incident.caller_masked == "+91987***10"

    # Inspect campaign
    assert raw_number not in str(campaign.model_dump())
    assert raw_number not in campaign.observed_caller_identifiers
    assert "+91987***10" in campaign.observed_caller_identifiers


# --- Requirement 21 & REST API: GET /api/campaigns and GET /api/campaigns/{id} ---
def test_campaign_api_endpoints():
    client = TestClient(app)
    # Initially empty
    resp = client.get("/api/campaigns")
    assert resp.status_code == 200
    assert resp.json() == []

    # Ingest a high incident via campaign_service
    s = make_test_session(
        "api_sess_1",
        88.0,
        RiskTier.HIGH,
        "+91 98765 43210",
        [ManipulationCategory.AUTHORITY_IMPERSONATION, ManipulationCategory.FINANCIAL_REDIRECTION],
    )
    inc = campaign_service.create_incident_summary(s)
    res = campaign_service.ingest_incident(inc)
    cmp_id = res[0].campaign_id

    # List campaigns
    resp_list = client.get("/api/campaigns")
    assert resp_list.status_code == 200
    data = resp_list.json()
    assert len(data) == 1
    assert data[0]["campaign_id"] == cmp_id

    # Get campaign detail
    resp_get = client.get(f"/api/campaigns/{cmp_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["campaign_id"] == cmp_id

    # Non-existent campaign returns 404
    resp_404 = client.get("/api/campaigns/CMP-NONEXISTENT")
    assert resp_404.status_code == 404


# ==============================================================================
# Phase 10E-2: Campaign Escalation & Law-Enforcement Report Tests
# ==============================================================================


# --- Requirement 1, 2, 3: Status transitions (DETECTED -> ACTIVE_MONITORING -> ESCALATION_ELIGIBLE) ---
def test_campaign_status_lifecycle_transitions():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.FEAR_INTIMIDATION,
        ManipulationCategory.FINANCIAL_REDIRECTION,
    ]
    caller = "+91 98765 43210"

    # Incident 1 -> DETECTED
    s1 = make_test_session("trans_1", 82.0, RiskTier.HIGH, caller, tactics)
    res1 = service.ingest_incident(service.create_incident_summary(s1))
    assert res1 is not None
    c1 = res1[0]
    assert c1.incident_count == 1
    assert c1.status == CampaignStatus.DETECTED

    # Incident 2 -> ACTIVE_MONITORING
    s2 = make_test_session("trans_2", 88.0, RiskTier.HIGH, caller, tactics)
    res2 = service.ingest_incident(service.create_incident_summary(s2))
    assert res2 is not None
    c2 = res2[0]
    assert c2.incident_count == 2
    assert c2.status == CampaignStatus.ACTIVE_MONITORING

    # Incident 3 -> ESCALATION_ELIGIBLE
    s3 = make_test_session("trans_3", 92.0, RiskTier.CRITICAL, caller, tactics)
    res3 = service.ingest_incident(service.create_incident_summary(s3))
    assert res3 is not None
    c3 = res3[0]
    assert c3.incident_count == 3
    assert c3.status == CampaignStatus.ESCALATION_ELIGIBLE


# --- Requirement 4: SAFE/LOW/MEDIUM incidents cannot increase count or trigger escalation ---
def test_safe_low_medium_cannot_increase_campaign_count():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.FINANCIAL_REDIRECTION,
    ]
    caller = "+91 98765 43210"

    # Seed with 2 HIGH incidents -> ACTIVE_MONITORING
    s1 = make_test_session("s_hi_1", 85.0, RiskTier.HIGH, caller, tactics)
    s2 = make_test_session("s_hi_2", 85.0, RiskTier.HIGH, caller, tactics)
    service.ingest_incident(service.create_incident_summary(s1))
    c = service.ingest_incident(service.create_incident_summary(s2))[0]
    assert c.incident_count == 2
    assert c.status == CampaignStatus.ACTIVE_MONITORING

    # Attempt SAFE call
    s_safe = make_test_session("s_safe_test", 0.0, RiskTier.SAFE, caller, [])
    assert service.ingest_incident(service.create_incident_summary(s_safe)) is None

    # Attempt LOW call
    s_low = make_test_session("s_low_test", 30.0, RiskTier.LOW, caller, tactics)
    assert service.ingest_incident(service.create_incident_summary(s_low)) is None

    # Attempt MEDIUM call
    s_med = make_test_session("s_med_test", 60.0, RiskTier.MEDIUM, caller, tactics)
    assert service.ingest_incident(service.create_incident_summary(s_med)) is None

    # Verify campaign count and status are completely unaffected
    assert c.incident_count == 2
    assert c.status == CampaignStatus.ACTIVE_MONITORING


# --- Requirement 5 & 6: Single CRITICAL call does NOT generate report & report requires threshold ---
def test_single_critical_incident_does_not_generate_report():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.FEAR_INTIMIDATION,
        ManipulationCategory.FINANCIAL_REDIRECTION,
    ]
    s_crit = make_test_session("crit_1", 98.0, RiskTier.CRITICAL, "+91 98765 43210", tactics)
    c, _, is_new = service.ingest_incident(service.create_incident_summary(s_crit))

    assert is_new is True
    assert c.status == CampaignStatus.DETECTED
    assert c.incident_count == 1

    # Report does not exist
    assert service.get_report_by_campaign(c.campaign_id) is None

    # Attempting to generate report before threshold raises ValueError
    import pytest
    with pytest.raises(ValueError) as excinfo:
        service.generate_law_enforcement_report(c.campaign_id)
    assert "below the escalation threshold" in str(excinfo.value) or "minimum 3 required" in str(excinfo.value)


# --- Requirement 7, 8, 9: Eligible campaign generates report and transitions to REPORT_GENERATED idempotently ---
def test_eligible_campaign_generates_report_idempotently():
    service = CampaignService()
    tactics = [
        ManipulationCategory.AUTHORITY_IMPERSONATION,
        ManipulationCategory.FEAR_INTIMIDATION,
        ManipulationCategory.FINANCIAL_REDIRECTION,
    ]
    caller = "+91 98765 43210"

    # Add 3 incidents to reach ESCALATION_ELIGIBLE
    for i in range(3):
        s = make_test_session(f"inc_{i}", 85.0 + i, RiskTier.HIGH, caller, tactics)
        service.ingest_incident(service.create_incident_summary(s))

    camp = service.list_campaigns()[0]
    assert camp.status == CampaignStatus.ESCALATION_ELIGIBLE
    assert camp.incident_count == 3

    # Generate report
    report1 = service.generate_law_enforcement_report(camp.campaign_id)
    assert report1 is not None
    assert report1.campaign_id == camp.campaign_id
    assert report1.status == "MOCK_REPORT_GENERATED"
    assert report1.disclaimer == "DEMO ONLY — NO ACTUAL TRANSMISSION TO LAW ENFORCEMENT"
    assert camp.status == CampaignStatus.REPORT_GENERATED

    # Idempotent second call returns identical report
    report2 = service.generate_law_enforcement_report(camp.campaign_id)
    assert report2.report_id == report1.report_id
    assert report2.integrity_hash == report1.integrity_hash
    assert camp.status == CampaignStatus.REPORT_GENERATED


# --- Requirement 10-18: Privacy invariants, content summary, and integrity hash ---
def test_report_privacy_and_content_invariants():
    service = CampaignService()
    raw_number = "+91 98765 43210"
    victim_pii = "Lakshmi Ramanathan, Bank Account: 1234567890"

    # Create 3 sessions with sensitive transcript segments attached to session
    camp = None
    for i in range(3):
        s = make_test_session(
            f"priv_inc_{i}",
            85.0 + (i * 5),
            RiskTier.CRITICAL if i == 2 else RiskTier.HIGH,
            raw_number,
            [
                ManipulationCategory.AUTHORITY_IMPERSONATION,
                ManipulationCategory.FEAR_INTIMIDATION,
                ManipulationCategory.FINANCIAL_REDIRECTION,
            ],
        )
        s.transcript_history.append(
            TranscriptSegment(session_id=f"priv_inc_{i}", text=f"{victim_pii} call turn {i}")
        )
        res = service.ingest_incident(service.create_incident_summary(s))
        camp = res[0]

    report = service.generate_law_enforcement_report(camp.campaign_id)

    # 1. Content verifications
    assert report.incident_count == 3
    assert len(report.linked_incident_ids) == 3
    assert "priv_inc_0" in report.linked_incident_ids
    assert "+91987***10" in report.observed_caller_identifiers
    assert raw_number not in report.observed_caller_identifiers
    assert ManipulationCategory.AUTHORITY_IMPERSONATION in report.dominant_tactics
    assert "FINANCIAL_REDIRECTION" in report.target_categories
    assert report.highest_risk_score == 95.0
    assert report.average_risk_score > 85.0
    assert "escalation threshold" in report.escalation_reason.lower()
    assert report.integrity_hash is not None and len(report.integrity_hash) == 64

    # 2. Strict Privacy assertions on serialized report (Requirement 18)
    serialized = report.model_dump()
    serialized_str = str(serialized)

    assert raw_number not in serialized_str
    assert "1234567890" not in serialized_str
    assert "Lakshmi" not in serialized_str
    assert "transcript" not in serialized_str
    assert "audio" not in serialized_str
    assert "caregiver_contacts" not in serialized_str
    assert "bank_account" not in serialized_str


# --- Requirement 19, 20, 21: REST API /api/campaigns/{id}/report endpoints ---
def test_report_api_endpoints():
    client = TestClient(app)
    campaign_service.clear()

    # 1. 404 for non-existent campaign
    resp_404 = client.post("/api/campaigns/CMP-DOESNOTEXIST/report")
    assert resp_404.status_code == 404

    # 2. Create campaign with only 1 incident
    s1 = make_test_session(
        "api_inc_1",
        85.0,
        RiskTier.HIGH,
        "+91 98765 43210",
        [ManipulationCategory.AUTHORITY_IMPERSONATION, ManipulationCategory.FINANCIAL_REDIRECTION],
    )
    res = campaign_service.ingest_incident(campaign_service.create_incident_summary(s1))
    cid = res[0].campaign_id

    # 3. 409 Conflict when below threshold
    resp_409 = client.post(f"/api/campaigns/{cid}/report")
    assert resp_409.status_code == 409
    assert "minimum 3 required" in resp_409.json()["detail"]

    # 4. Ingest 2 more incidents to reach threshold of 3
    s2 = make_test_session(
        "api_inc_2",
        88.0,
        RiskTier.HIGH,
        "+91 98765 43210",
        [ManipulationCategory.AUTHORITY_IMPERSONATION, ManipulationCategory.FINANCIAL_REDIRECTION],
    )
    s3 = make_test_session(
        "api_inc_3",
        92.0,
        RiskTier.CRITICAL,
        "+91 98765 43210",
        [ManipulationCategory.AUTHORITY_IMPERSONATION, ManipulationCategory.FINANCIAL_REDIRECTION],
    )
    campaign_service.ingest_incident(campaign_service.create_incident_summary(s2))
    campaign_service.ingest_incident(campaign_service.create_incident_summary(s3))

    # 5. POST to generate report succeeds
    resp_post = client.post(f"/api/campaigns/{cid}/report")
    assert resp_post.status_code == 200
    rep_data = resp_post.json()
    assert rep_data["campaign_id"] == cid
    assert rep_data["status"] == "MOCK_REPORT_GENERATED"
    assert rep_data["incident_count"] == 3
    rep_id = rep_data["report_id"]

    # 6. Second POST is idempotent and returns existing report
    resp_post2 = client.post(f"/api/campaigns/{cid}/report")
    assert resp_post2.status_code == 200
    assert resp_post2.json()["report_id"] == rep_id

    # 7. GET /api/campaigns/{cid}/report returns existing report
    resp_get = client.get(f"/api/campaigns/{cid}/report")
    assert resp_get.status_code == 200
    assert resp_get.json()["report_id"] == rep_id
    assert resp_get.json()["disclaimer"] == "DEMO ONLY — NO ACTUAL TRANSMISSION TO LAW ENFORCEMENT"

