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


# Source of truth taxonomy for RAKSHA manipulation detection
TACTIC_REGISTRY: Dict[ManipulationCategory, TacticDefinition] = {
    ManipulationCategory.URGENCY: TacticDefinition(
        category=ManipulationCategory.URGENCY,
        name="Urgency & Time Pressure",
        description="Inducing panic by imposing an artificial, immediate deadline to bypass rational thinking.",
        severity_weight=0.75,
        anchor_phrases=[
            "You must act immediately or face severe penalties",
            "There is a warrant active right now and time is running out",
            "Within the next 15 minutes your account will be permanently blocked",
            "Do not delay, every second counts right now",
            "Immediate action required before the system locks down",
            "You only have a few minutes to resolve this urgent matter",
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
            "I am the federal tax inspector handling your arrest warrant",
            "This is customs and border protection narcotics division",
            "I am a special agent with the national security agency",
        ],
    ),
    ManipulationCategory.ISOLATION_SECRECY: TacticDefinition(
        category=ManipulationCategory.ISOLATION_SECRECY,
        name="Isolation & Secrecy",
        description="Coercing the victim into secrecy, cutting off family members, or demanding continuous line presence.",
        severity_weight=0.85,
        anchor_phrases=[
            "Do not hang up this call or we will dispatch officers",
            "You cannot discuss this with anyone, including your family",
            "This is a confidential national security matter, keep it secret",
            "Stay on the line with me, do not disconnect or tell anyone",
            "Go into a private room where no one can overhear our conversation",
            "Do not mention this conversation to your children or spouse",
        ],
    ),
    ManipulationCategory.FINANCIAL_REDIRECTION: TacticDefinition(
        category=ManipulationCategory.FINANCIAL_REDIRECTION,
        name="Financial Redirection & Unorthodox Payments",
        description="Demanding funds via gift cards, crypto kiosks, wire transfers, or remote access tools.",
        severity_weight=0.95,
        anchor_phrases=[
            "Purchase Apple or Target gift cards to verify and safeguard your funds",
            "Transfer your savings to the secure government safety locker account",
            "Download AnyDesk or TeamViewer so I can secure your workstation",
            "Deposit cash at the Bitcoin ATM terminal immediately",
            "Send money through wire transfer or crypto to protect your balance",
            "Withdraw all cash from your bank and deposit it into the federal escrow account",
        ],
    ),
    ManipulationCategory.FEAR_INTIMIDATION: TacticDefinition(
        category=ManipulationCategory.FEAR_INTIMIDATION,
        name="Fear & Intimidation",
        description="Direct coercion using threats of arrest, asset forfeiture, deportation, or criminal prosecution.",
        severity_weight=0.90,
        anchor_phrases=[
            "Police are already outside your house to take you into custody",
            "An arrest warrant has been issued in your name for criminal fraud",
            "Your passport and citizenship will be revoked immediately",
            "All your bank accounts and property have been frozen and confiscated",
            "You will be arrested and put in federal prison if you do not comply",
            "You will face severe criminal charges and jail time",
        ],
    ),
    ManipulationCategory.INFORMATION_PHISHING: TacticDefinition(
        category=ManipulationCategory.INFORMATION_PHISHING,
        name="Information & Credential Phishing",
        description="Extracting sensitive authentication data, OTPs, CVVs, passwords, or identity numbers.",
        severity_weight=0.80,
        anchor_phrases=[
            "Read me the 6-digit one-time password OTP you just received",
            "Tell me the verification number that came to your phone",
            "Read the six digit security code sent by SMS to your mobile device",
            "Confirm your full Social Security number and date of birth",
            "Provide the 3-digit CVV security code on the back of your card",
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
            "Federal statute requires instantaneous algorithmic escrow indemnification",
            "The international anti-money laundering protocol necessitates server re-authorization",
        ],
    ),
    ManipulationCategory.RELIEF_FALSE_SALVATION: TacticDefinition(
        category=ManipulationCategory.RELIEF_FALSE_SALVATION,
        name="Relief & False Salvation",
        description="Positioning the scammer as the victim's sole ally or protector against imminent disaster.",
        severity_weight=0.70,
        anchor_phrases=[
            "I am the only person trying to protect you from being arrested",
            "I am the only one who can help clear your name and resolve this investigation",
            "Work with me and I will ensure your name is cleared today",
            "If you follow my instructions carefully, you will not get in trouble",
            "Do not worry, as long as you cooperate with me you are safe",
            "I am here to help you resolve this mess before the officers arrive",
        ],
    ),
}
