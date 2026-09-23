"""Benchmark Scenario Dataset for RAKSHA Offline Evaluation (Phase 8B).

Contains 30 realistic, deterministic conversational scenarios across 7 categories:
1. Clear Scam (5)
2. Multi-Tactic (4)
3. Novel Wording (5)
4. Legitimate Urgency (5)
5. Benign (5)
6. Multi-Segment Progression (3)
7. Downstream Failure Isolation (3)

All conversational text uses natural paraphrased phrasing and intentionally avoids
verbatim copying of detector anchor phrases.
"""

from typing import List
from backend.app.models import ManipulationCategory, SpeakerType
from evaluation.models import EvaluationScenario, EvaluationSegment


# ==============================================================================
# 1. CLEAR SCAM SCENARIOS (5)
# ==============================================================================

CLEAR_SCAM_SCENARIOS: List[EvaluationScenario] = [
    EvaluationScenario(
        scenario_id="clear_scam_fake_bank_otp",
        category="clear_scam",
        description="Fake bank fraud agent urgently requesting an SMS verification passcode.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Good morning, I am calling from the bank fraud protection department. We flagged an unauthorized debit charge of nine hundred dollars on your card.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLEE,
                text="No, I did not make any such charge! What should I do?",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Don't worry, we can cancel it right now. Please read me the 6-digit one-time password OTP you just received on your phone so I can verify your identity.",
                expected_tactics=[ManipulationCategory.INFORMATION_PHISHING],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
        notes="Acute phishing trigger targeting temporary SMS passcode.",
    ),
    EvaluationScenario(
        scenario_id="clear_scam_police_arrest_warrant",
        category="clear_scam",
        description="Impersonator claiming to be law enforcement threatening immediate arrest.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is Officer Miller from the Federal Police Department headquarters.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="An arrest warrant has been issued in your name for criminal fraud, and deputies are being dispatched to your residence.",
                expected_tactics=[ManipulationCategory.FEAR_INTIMIDATION],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FEAR_INTIMIDATION,
        ],
        notes="High authority claim paired with arrest coercion.",
    ),
    EvaluationScenario(
        scenario_id="clear_scam_customs_courier_payment",
        category="clear_scam",
        description="Customs agent demanding settlement via gift cards to release an impounded package.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Calling from customs and border protection narcotics division regarding an international parcel.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Purchase Apple or Target gift cards to verify and safeguard your funds to clear customs inspection.",
                expected_tactics=[ManipulationCategory.FINANCIAL_REDIRECTION],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        notes="Unorthodox gift card payment demand for impounded package.",
    ),
    EvaluationScenario(
        scenario_id="clear_scam_secure_vault_transfer",
        category="clear_scam",
        description="Scammer directing victim to transfer life savings to a 'secure safety locker account'.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Your commercial bank account has been compromised by rogue internal employees.",
                expected_tactics=[ManipulationCategory.FEAR_INTIMIDATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Transfer your savings to the secure government safety locker account immediately to preserve your balance.",
                expected_tactics=[ManipulationCategory.FINANCIAL_REDIRECTION],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        notes="Classic safe-account / government safety locker redirection scam.",
    ),
    EvaluationScenario(
        scenario_id="clear_scam_remote_access_tech_support",
        category="clear_scam",
        description="Fake technician alerting victim to malware and demanding remote software installation.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is Microsoft Windows security alerts. Your personal computer is sending infected virus packets.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Download AnyDesk or TeamViewer so I can secure your workstation and remove the spyware.",
                expected_tactics=[ManipulationCategory.FINANCIAL_REDIRECTION],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        notes="Remote desktop access demand under technical support guise.",
    ),
]


# ==============================================================================
# 2. MULTI-TACTIC SCENARIOS (4)
# ==============================================================================

MULTI_TACTIC_SCENARIOS: List[EvaluationScenario] = [
    EvaluationScenario(
        scenario_id="multi_tactic_authority_fear_urgency",
        category="multi_tactic",
        description="Authority claim combined with arrest threats and a strict 15-minute countdown.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="I am a special agent with the national security agency handling your federal case.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="You will be arrested and put in federal prison if you do not comply with our instructions.",
                expected_tactics=[ManipulationCategory.FEAR_INTIMIDATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Within the next 15 minutes your account will be permanently blocked unless you respond.",
                expected_tactics=[ManipulationCategory.URGENCY],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.URGENCY,
        ],
        notes="Tests tri-tactic synergy across authority, fear, and time pressure.",
    ),
    EvaluationScenario(
        scenario_id="multi_tactic_fear_financial_redirect",
        category="multi_tactic",
        description="Asset confiscation threats paired with cash deposit at a Bitcoin kiosk.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="All your bank accounts and property have been frozen and confiscated by court order.",
                expected_tactics=[ManipulationCategory.FEAR_INTIMIDATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Deposit cash at the Bitcoin ATM terminal immediately to protect your remaining funds in federal escrow.",
                expected_tactics=[ManipulationCategory.FINANCIAL_REDIRECTION],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        notes="High-danger co-occurrence of intimidation and crypto redirection.",
    ),
    EvaluationScenario(
        scenario_id="multi_tactic_authority_isolation_phishing",
        category="multi_tactic",
        description="Inspector enforcing secrecy and demanding online banking credentials.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="I am the federal tax inspector handling your arrest warrant and compliance audit.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="You cannot discuss this with anyone, including your family, as this is a sealed matter.",
                expected_tactics=[ManipulationCategory.ISOLATION_SECRECY],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="What is your online banking username and login password so we can audit your records.",
                expected_tactics=[ManipulationCategory.INFORMATION_PHISHING],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.ISOLATION_SECRECY,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
        notes="Dangerous isolation tactic paired with direct credential extraction.",
    ),
    EvaluationScenario(
        scenario_id="multi_tactic_urgency_confusion_phishing",
        category="multi_tactic",
        description="Cognitive overwhelm with legal jargon, time panic, and OTP harvesting.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Your IP address was routed through a darknet syndicate node under penal code protocol.",
                expected_tactics=[ManipulationCategory.CONFUSION_OVERWHELM],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="You must act immediately or face severe penalties within minutes.",
                expected_tactics=[ManipulationCategory.URGENCY],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Tell me the verification number that came to your phone to reverse the transaction.",
                expected_tactics=[ManipulationCategory.INFORMATION_PHISHING],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.CONFUSION_OVERWHELM,
            ManipulationCategory.URGENCY,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
        notes="Overwhelm jargon combined with artificial urgency and OTP theft.",
    ),
]


# ==============================================================================
# 3. NOVEL WORDING SCENARIOS (5)
# ==============================================================================

NOVEL_WORDING_SCENARIOS: List[EvaluationScenario] = [
    EvaluationScenario(
        scenario_id="novel_wording_contraband_parcel",
        category="novel_wording",
        description="Courier alleging illicit contraband found in an intercepted container.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is courier transport security at the maritime docks. A shipping container billed under your tax number was flagged by inspection dogs for hidden contraband.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Unless we resolve this filing before midnight, our legal counsel will submit the manifest to regional magistrates for immediate prosecution.",
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FEAR_INTIMIDATION,
        ],
        notes="Evaluates semantic generalization without using standard arrest/police phrases.",
    ),
    EvaluationScenario(
        scenario_id="novel_wording_protected_vault_transfer",
        category="novel_wording",
        description="Advising customer to re-route capital into an insured reserve vault.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Due to liquidity vulnerabilities in local banking branches, our advisory unit recommends sheltering your balances into a bonded government liquidity vault.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Please wire your liquid assets to the designated treasury settlement routing number right now.",
            ),
        ],
        expected_tactics=[
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        notes="Tests detection of safe-vault redirection using institutional financial vocabulary.",
    ),
    EvaluationScenario(
        scenario_id="novel_wording_remote_diagnostic",
        category="novel_wording",
        description="Support technician requesting remote bridge utility to inspect network adapter.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Our telemetry bridge is seeing abnormal packet fragmentation originating from your laptop network card.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Please initiate our diagnostic screen-sharing client so our technician can inspect your hardware drivers directly.",
            ),
        ],
        expected_tactics=[
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        notes="Tests remote access detection without mentioning TeamViewer or AnyDesk.",
    ),
    EvaluationScenario(
        scenario_id="novel_wording_credential_handshake",
        category="novel_wording",
        description="Caller asking for a digital validation token delivered via SMS.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="To complete the cryptographic handshake with your cellular operator, a temporary digital security string has appeared on your handset.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Please verbalize the digits you see on the screen so we can confirm you are the authorized subscriber.",
            ),
        ],
        expected_tactics=[
            ManipulationCategory.INFORMATION_PHISHING,
        ],
        notes="Tests phishing detection using technical 'handshake token' terminology instead of OTP.",
    ),
    EvaluationScenario(
        scenario_id="novel_wording_indirect_legal_freeze",
        category="novel_wording",
        description="Indirect warning that court magistrates will impound household holdings.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Notice of statutory proceedings. A sworn petition was recorded against your estate regarding unpaid liabilities.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="If this filing goes unanswered before sunset, all household equity and vehicle registrations will be sealed by civil enforcement.",
            ),
        ],
        expected_tactics=[
            ManipulationCategory.FEAR_INTIMIDATION,
        ],
        notes="Tests indirect legal coercion without explicit 'police outside house' anchors.",
    ),
]


# ==============================================================================
# 4. LEGITIMATE URGENCY SCENARIOS (5)
# ==============================================================================

LEGITIMATE_URGENCY_SCENARIOS: List[EvaluationScenario] = [
    EvaluationScenario(
        scenario_id="legitimate_urgency_hospital_er",
        category="legitimate_urgency",
        description="Doctor calling regarding an injured family member in the emergency room.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hello Mr. Davis, this is Dr. Williams calling from the county hospital trauma department.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Your brother was admitted following an accident. He is conscious and stable, but we need you to come to the front desk right away to sign medical authorization.",
            ),
        ],
        expected_tactics=[],
        notes="Genuine medical urgency. May trigger URGENCY; must not trigger phishing or financial redirection.",
    ),
    EvaluationScenario(
        scenario_id="legitimate_urgency_airport_gate",
        category="legitimate_urgency",
        description="Airline agent giving final boarding call for closing flight gate.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Final boarding announcement for passenger Thompson on flight 812 to Boston.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="The departure jetway door is closing in three minutes, please proceed to gate 14 immediately.",
            ),
        ],
        expected_tactics=[],
        notes="Legitimate travel deadline.",
    ),
    EvaluationScenario(
        scenario_id="legitimate_urgency_water_leak",
        category="legitimate_urgency",
        description="Building superintendent calling about an active plumbing flood.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hi John, this is Marco the building superintendent.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="There is water pouring through the ceiling into apartment 3A below you. Please shut off your main water valve as quickly as possible.",
            ),
        ],
        expected_tactics=[],
        notes="Domestic property emergency requiring immediate action.",
    ),
    EvaluationScenario(
        scenario_id="legitimate_urgency_pharmacy_prescription",
        category="legitimate_urgency",
        description="Pharmacist reminding patient to pick up critical refrigerated insulin before closing.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Good evening, this is City Pharmacy dispensing department.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Your specialized prescription medication must be collected before our store closes at 8 PM tonight or it will spoil.",
            ),
        ],
        expected_tactics=[],
        notes="Time-sensitive medical collection reminder.",
    ),
    EvaluationScenario(
        scenario_id="legitimate_urgency_bank_fraud_alert",
        category="legitimate_urgency",
        description="Genuine bank notification of card block advising customer to visit branch or check app.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is an automated notification from First National Bank security operations.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="A suspicious purchase was blocked on your card. For your security, we will never ask for your PIN or passwords over the phone. Please open our official mobile app to review.",
            ),
        ],
        expected_tactics=[],
        notes="Legitimate fraud notification that explicitly refuses to request credentials.",
    ),
]


# ==============================================================================
# 5. BENIGN SCENARIOS (5)
# ==============================================================================

BENIGN_SCENARIOS: List[EvaluationScenario] = [
    EvaluationScenario(
        scenario_id="benign_family_dinner",
        category="benign",
        description="Grandchild chatting with grandmother about weekend dinner plans.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hi Grandma, how are you feeling today?",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLEE,
                text="I'm doing well dear! Just watering the garden plants.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="We are so excited to see you for Sunday dinner. Mom is baking your favorite peach cobbler.",
            ),
        ],
        expected_tactics=[],
        notes="Wholesome family dialogue with zero scam pressure.",
    ),
    EvaluationScenario(
        scenario_id="benign_dentist_reschedule",
        category="benign",
        description="Dental clinic rescheduling a routine teeth cleaning appointment.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Good morning, this is Sarah from Lakeview Dental Clinic.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="We have an opening for your routine cleaning this Thursday at two in the afternoon if you would like to move your appointment up.",
            ),
        ],
        expected_tactics=[],
        notes="Routine medical scheduling.",
    ),
    EvaluationScenario(
        scenario_id="benign_food_delivery",
        category="benign",
        description="Delivery driver asking for building door buzzer access.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hello, this is your grocery delivery courier outside your apartment complex.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="The front gate seems closed, could you please enter your buzzer code on the intercom?",
            ),
        ],
        expected_tactics=[],
        notes="Normal delivery interaction.",
    ),
    EvaluationScenario(
        scenario_id="benign_customer_support_order",
        category="benign",
        description="Retail representative sharing package tracking number.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Thank you for reaching out to Mountain Hardware customer care.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Your replacement hiking boots shipped this morning via standard postal mail and should arrive on Friday.",
            ),
        ],
        expected_tactics=[],
        notes="Benign e-commerce customer support.",
    ),
    EvaluationScenario(
        scenario_id="benign_gardening_weather",
        category="benign",
        description="Casual conversation regarding garden care and sunny weather.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hey Peter, it looks like the weekend forecast will be sunny and warm.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="I was thinking we could finish mulching the rose bushes and trimming the hedges out back.",
            ),
        ],
        expected_tactics=[],
        notes="Completely neutral outdoor hobby conversation.",
    ),
]


# ==============================================================================
# 6. MULTI-SEGMENT PROGRESSION SCENARIOS (3)
# ==============================================================================

PROGRESSION_SCENARIOS: List[EvaluationScenario] = [
    EvaluationScenario(
        scenario_id="progression_friendly_to_coercive_otp",
        category="progression",
        description="Gradual multi-turn escalation from friendly customer service to urgent OTP extraction.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Good afternoon, thank you for being a valued customer with our telecommunications company.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Calling from the Central Bank fraud investigation team regarding a questionable debit.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Do not delay, every second counts right now to stop the money from leaving.",
                expected_tactics=[ManipulationCategory.URGENCY],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="You will face severe criminal charges and jail time if you refuse to protect your balance.",
                expected_tactics=[ManipulationCategory.FEAR_INTIMIDATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Read me the 6-digit one-time password OTP you just received to verify your consent.",
                expected_tactics=[ManipulationCategory.INFORMATION_PHISHING],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.URGENCY,
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
        notes="5-step progression testing evidence accumulation and risk tier escalation.",
    ),
    EvaluationScenario(
        scenario_id="progression_routine_inquiry_to_arrest_threat",
        category="progression",
        description="Progression from routine identity check to law enforcement arrest coercion.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hello, I am calling to confirm delivery coordinates for official correspondence.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is Officer Miller from the Federal Police Department investigating financial discrepancies.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Stay on the line with me, do not disconnect or tell anyone about this conversation.",
                expected_tactics=[ManipulationCategory.ISOLATION_SECRECY],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Police are already outside your house to take you into custody if you hang up.",
                expected_tactics=[ManipulationCategory.FEAR_INTIMIDATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Withdraw all cash from your bank and deposit it into the federal escrow account immediately.",
                expected_tactics=[ManipulationCategory.FINANCIAL_REDIRECTION],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.ISOLATION_SECRECY,
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        notes="5-turn escalation testing authority, isolation, intimidation, and financial extortion.",
    ),
    EvaluationScenario(
        scenario_id="progression_tech_help_to_wire_transfer",
        category="progression",
        description="Progression from laptop assistance to severe bank hazard and crypto ATM demand.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hello, thank you for calling consumer tech support today.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is the cybercrime division investigating your identity and hacked personal network.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Immediate action required before the system locks down all personal files.",
                expected_tactics=[ManipulationCategory.URGENCY],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="I am the only person trying to protect you from being arrested and losing everything.",
                expected_tactics=[ManipulationCategory.RELIEF_FALSE_SALVATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Deposit cash at the Bitcoin ATM terminal immediately to secure your assets.",
                expected_tactics=[ManipulationCategory.FINANCIAL_REDIRECTION],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.URGENCY,
            ManipulationCategory.RELIEF_FALSE_SALVATION,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        notes="5-step progression testing false salvation and crypto redirection.",
    ),
]


# ==============================================================================
# 7. DOWNSTREAM FAILURE ISOLATION SCENARIOS (3)
# ==============================================================================

DOWNSTREAM_FAILURE_SCENARIOS: List[EvaluationScenario] = [
    EvaluationScenario(
        scenario_id="downstream_failure_sms_error",
        category="downstream_failure",
        description="High scam scenario where caregiver SMS delivery fails.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is Officer Miller from the Federal Police Department.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Police are already outside your house to take you into custody.",
                expected_tactics=[ManipulationCategory.FEAR_INTIMIDATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Withdraw all cash from your bank and deposit it into the federal escrow account.",
                expected_tactics=[ManipulationCategory.FINANCIAL_REDIRECTION],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        caregiver_should_fail=True,
        notes="Verifies upstream risk engine, protection engine, and alert execution remain intact when SMS fails.",
    ),
    EvaluationScenario(
        scenario_id="downstream_failure_warning_error",
        category="downstream_failure",
        description="High scam scenario where protected-user voice warning delivery fails.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is customs and border protection narcotics division.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="An arrest warrant has been issued in your name for criminal fraud.",
                expected_tactics=[ManipulationCategory.FEAR_INTIMIDATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Within the next 15 minutes your account will be permanently blocked.",
                expected_tactics=[ManipulationCategory.URGENCY],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Purchase Apple or Target gift cards to verify and safeguard your funds.",
                expected_tactics=[ManipulationCategory.FINANCIAL_REDIRECTION],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.URGENCY,
            ManipulationCategory.FINANCIAL_REDIRECTION,
        ],
        warning_should_fail=True,
        notes="Verifies upstream risk and protection remain intact when user voice warning fails.",
    ),
    EvaluationScenario(
        scenario_id="downstream_failure_intervention_error",
        category="downstream_failure",
        description="Critical scam scenario where call disconnect intervention fails.",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Calling from the Central Bank fraud investigation team.",
                expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Police are already outside your house to take you into custody.",
                expected_tactics=[ManipulationCategory.FEAR_INTIMIDATION],
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Read me the 6-digit one-time password OTP you just received immediately.",
                expected_tactics=[ManipulationCategory.INFORMATION_PHISHING],
            ),
        ],
        expected_tactics=[
            ManipulationCategory.AUTHORITY_IMPERSONATION,
            ManipulationCategory.FEAR_INTIMIDATION,
            ManipulationCategory.INFORMATION_PHISHING,
        ],
        intervention_should_fail=True,
        notes="Verifies critical risk and protection state remain intact when disconnect intervention fails.",
    ),
]


# ==============================================================================
# ALL BENCHMARK SCENARIOS (30 TOTAL)
# ==============================================================================

ALL_EVALUATION_SCENARIOS: List[EvaluationScenario] = (
    CLEAR_SCAM_SCENARIOS
    + MULTI_TACTIC_SCENARIOS
    + NOVEL_WORDING_SCENARIOS
    + LEGITIMATE_URGENCY_SCENARIOS
    + BENIGN_SCENARIOS
    + PROGRESSION_SCENARIOS
    + DOWNSTREAM_FAILURE_SCENARIOS
)


def get_all_scenarios() -> List[EvaluationScenario]:
    """Retrieve the complete deterministic benchmark dataset."""
    return list(ALL_EVALUATION_SCENARIOS)


def get_scenarios_by_category(category: str) -> List[EvaluationScenario]:
    """Filter benchmark scenarios by category."""
    return [s for s in ALL_EVALUATION_SCENARIOS if s.category == category]
