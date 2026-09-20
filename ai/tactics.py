from dataclasses import dataclass
from typing import Dict, List
from backend.app.models import ManipulationCategory


@dataclass(frozen=True)
class TacticDefinition:
    category: ManipulationCategory
    name: str
    description: str
    severity_weight: float  # 0.0 to 1.0 multiplier for risk engine
    anchor_phrases: List[str]


# Manipulation Tactics Taxonomy for Semantic Matching (Phase 2)
TACTIC_REGISTRY: Dict[ManipulationCategory, TacticDefinition] = {
    ManipulationCategory.URGENCY: TacticDefinition(
        category=ManipulationCategory.URGENCY,
        name="Urgency & Time Pressure",
        description="Inducing panic by imposing an artificial, immediate deadline to bypass rational thinking.",
        severity_weight=0.75,
        anchor_phrases=[
            "You must act immediately or face penalties",
            "There is a warrant active right now",
            "Within the next 15 minutes your account will be permanently blocked",
            "Do not delay, every second counts",
        ],
    ),
    ManipulationCategory.AUTHORITY_IMPERSONATION: TacticDefinition(
        category=ManipulationCategory.AUTHORITY_IMPERSONATION,
        name="Authority Impersonation",
        description="Falsely claiming to be law enforcement, government officials, or bank fraud departments.",
        severity_weight=0.90,
        anchor_phrases=[
            "This is Officer Miller from the Federal Police Department",
            "Calling from the Central Bank fraud investigation team",
            "This is the cybercrime division investigating your identity",
            "I am the tax inspector handling your arrest warrant",
        ],
    ),
    ManipulationCategory.ISOLATION: TacticDefinition(
        category=ManipulationCategory.ISOLATION,
        name="Isolation & Secrecy",
        description="Coercing the victim into secrecy, cutting off family members, or demanding continuous line presence.",
        severity_weight=0.85,
        anchor_phrases=[
            "Do not hang up this call or we will dispatch officers",
            "You cannot discuss this with anyone, including your family",
            "This is a confidential national security matter",
            "Go into a private room where no one can hear you",
        ],
    ),
    ManipulationCategory.FINANCIAL_EXTRACTION: TacticDefinition(
        category=ManipulationCategory.FINANCIAL_EXTRACTION,
        name="Financial Extraction & Unorthodox Payments",
        description="Demanding funds via gift cards, crypto kiosks, wire transfers, or remote access tools.",
        severity_weight=0.95,
        anchor_phrases=[
            "Purchase Apple or Target gift cards to verify your funds",
            "Transfer your savings to the secure government safety locker account",
            "Download AnyDesk or TeamViewer so I can secure your workstation",
            "Deposit cash at the Bitcoin ATM terminal immediately",
        ],
    ),
    ManipulationCategory.THREAT_INTIMIDATION: TacticDefinition(
        category=ManipulationCategory.THREAT_INTIMIDATION,
        name="Threats & Intimidation",
        description="Direct coercion using threats of arrest, asset forfeiture, deportation, or harm.",
        severity_weight=0.90,
        anchor_phrases=[
            "Police are already outside your house to take you into custody",
            "Your passport and citizenship will be revoked immediately",
            "All your bank accounts and property have been frozen",
            "You will go to prison for money laundering and fraud",
        ],
    ),
    ManipulationCategory.CREDENTIAL_HARVESTING: TacticDefinition(
        category=ManipulationCategory.CREDENTIAL_HARVESTING,
        name="Credential & Identity Harvesting",
        description="Extracting sensitive authentication data, OTPs, CVVs, or identity numbers.",
        severity_weight=0.80,
        anchor_phrases=[
            "Read me the 6-digit one-time password you just received",
            "Confirm your full Social Security number and date of birth",
            "Provide the 3-digit security code on the back of your card",
            "What is your online banking username and login password",
        ],
    ),
    ManipulationCategory.CONFUSION_OVERWHELM: TacticDefinition(
        category=ManipulationCategory.CONFUSION_OVERWHELM,
        name="Cognitive Overwhelm",
        description="Flooding the victim with rapid legal jargon, confusing citations, or contradictory steps.",
        severity_weight=0.60,
        anchor_phrases=[
            "Section 420 of the penal code clause 8 mandates immediate compliance",
            "Your IP address was routed through a darknet syndicate node",
            "The ledger mismatch requires real-time forensic cache validation",
        ],
    ),
    ManipulationCategory.FALSE_SALVATION: TacticDefinition(
        category=ManipulationCategory.FALSE_SALVATION,
        name="False Salvation",
        description="Positioning the scammer as the victim's sole ally or protector against imminent disaster.",
        severity_weight=0.70,
        anchor_phrases=[
            "I am the only person trying to protect you from being arrested",
            "Work with me and I will ensure your name is cleared today",
            "If you follow my instructions carefully, you will not get in trouble",
        ],
    ),
}
