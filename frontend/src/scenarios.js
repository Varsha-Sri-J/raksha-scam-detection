/**
 * Deterministic Demo Simulation Scenarios and Evaluation Model for RAKSHA.
 * 
 * Provides:
 * A. Cybercrime Scam (SCAM)
 * B. Benign Conversation (BENIGN)
 * C. Legitimate Urgent Call (BENIGN)
 * D. Novel Scam Wording (SCAM)
 * 
 * Evaluation Logic:
 * SCAM + HIGH/CRITICAL = TRUE POSITIVE
 * SCAM + SAFE/LOW = FALSE NEGATIVE
 * BENIGN + SAFE/LOW = TRUE NEGATIVE
 * BENIGN + HIGH/CRITICAL = FALSE POSITIVE
 */

export const DEMO_SCENARIOS = [
  {
    id: 'cybercrime',
    name: 'Cybercrime Scam',
    label: 'Cybercrime Scam',
    groundTruth: 'SCAM',
    description: 'Officer Sharma impersonation, arrest warrant coercion, family isolation, and acute OTP phishing',
    calleeId: 'Lakshmi R.',
    caregivers: [
      {
        name: 'Ananya R.',
        phone_number: '+91 91234 56789',
        relationship: 'Daughter',
        enabled: true,
      },
    ],
    chunks: [
      'This is Officer Sharma from the Cyber Crime Department.',
      'An arrest warrant and account freeze have been issued against your bank account for money laundering.',
      'You must resolve this urgent matter within fifteen minutes before police officers arrive at your residence.',
      'Do not disconnect this line and do not tell your family or anyone about this investigation.',
      'Read me the six digit OTP verification code that was just sent to your mobile phone.',
    ],
  },
  {
    id: 'benign',
    name: 'Benign Conversation',
    label: 'Benign Conversation',
    groundTruth: 'BENIGN',
    description: 'Wholesome family dialogue discussing dinner, peach cobbler, groceries, and weekend visit',
    calleeId: 'Lakshmi R.',
    caregivers: [
      {
        name: 'Ananya R.',
        phone_number: '+91 91234 56789',
        relationship: 'Daughter',
        enabled: true,
      },
    ],
    chunks: [
      'Hi Grandma, how are you feeling today?',
      'We are so excited to see you for Sunday dinner. Mom is baking your favorite peach cobbler.',
      "I can pick you up around five o'clock so you don't have to drive in the dark.",
      'Let me know if there are any grocery items you want me to bring along.',
    ],
  },
  {
    id: 'legitimate_urgent',
    name: 'Legitimate Urgent Call',
    label: 'Legitimate Urgent Call',
    groundTruth: 'BENIGN',
    description: 'Bank security automated notification of card block; explicitly refuses phone credentials',
    calleeId: 'Lakshmi R.',
    caregivers: [
      {
        name: 'Ananya R.',
        phone_number: '+91 91234 56789',
        relationship: 'Daughter',
        enabled: true,
      },
    ],
    chunks: [
      'This is an automated notification from First National Bank security operations.',
      'A suspicious purchase was blocked on your card for your protection.',
      'For your security, we will never ask for your PIN or passwords over the phone.',
      'Please open our official mobile app or visit your local branch to review your account.',
    ],
  },
  {
    id: 'novel_scam',
    name: 'Novel Scam Wording',
    label: 'Novel Scam Wording',
    groundTruth: 'SCAM',
    description: 'Customs contraband parcel seizure, court affidavit, liquidity vault redirection & handshake token',
    calleeId: 'Lakshmi R.',
    caregivers: [
      {
        name: 'Ananya R.',
        phone_number: '+91 91234 56789',
        relationship: 'Daughter',
        enabled: true,
      },
    ],
    chunks: [
      'This is courier transport security at the international cargo terminal.',
      'A parcel addressed in your name was intercepted with illicit contraband and fake identity documents.',
      'Our compliance director is filing a criminal affidavit with federal magistrates within twenty minutes unless this is clarified.',
      'To prevent your primary liquid bank assets from being impounded under court seizure, wire them to the verified secure treasury vault right now.',
      'Read out the six-digit verification code sent to your handset so we can authorize the protective deposit.',
    ],
  },
]

/**
 * Deterministic evaluation outcome mapping per requirement:
 * SCAM + HIGH/CRITICAL = TRUE POSITIVE
 * SCAM + SAFE/LOW = FALSE NEGATIVE
 * BENIGN + SAFE/LOW = TRUE NEGATIVE
 * BENIGN + HIGH/CRITICAL = FALSE POSITIVE
 */
export function calculateEvaluationOutcome(groundTruth, finalTier) {
  const upperTier = (finalTier || 'SAFE').toUpperCase()
  const isHighOrCritical = upperTier === 'HIGH' || upperTier === 'CRITICAL'
  const isSafeOrLow = upperTier === 'SAFE' || upperTier === 'LOW'

  if (groundTruth === 'SCAM') {
    if (isHighOrCritical || upperTier === 'MEDIUM') {
      return 'TRUE POSITIVE'
    }
    return 'FALSE NEGATIVE'
  } else {
    // BENIGN
    if (isSafeOrLow) {
      return 'TRUE NEGATIVE'
    }
    return 'FALSE POSITIVE'
  }
}
