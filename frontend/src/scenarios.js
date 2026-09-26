/**
 * Deterministic Demo Simulation Scenarios and Evaluation Model for RAKSHA.
 *
 * Provides the final 5-call sequential demo flow:
 * 01 — Family Call (BENIGN -> SAFE)
 * 02 — Suspicious Payment Call (SUSPICIOUS / MEDIUM -> MEDIUM)
 * 03 — Cybercrime / OTP Scam (Language: English, SCAM -> CRITICAL)
 * 04 — Cybercrime / OTP Scam (Language: Hindi/Hinglish, SCAM -> CRITICAL)
 * 05 — Bank / OTP Scam (Language: Telugu/Teluglish, SCAM -> CRITICAL)
 *
 * Campaign Correlation:
 * Calls 03, 04, and 05 represent similar social-engineering patterns (Authority Impersonation,
 * Fear/Arrest, Urgency, Isolation, OTP Phishing) from distinct caller numbers, demonstrating
 * natural 3-call syndicate linking into ESCALATION ELIGIBLE.
 */

export const DEMO_SCENARIOS = [
  {
    id: '01_family_call',
    number: '01',
    name: '01 — Family Call',
    label: '01 — Family Call',
    category: 'BENIGN',
    type: 'BENIGN',
    language: 'English',
    groundTruth: 'BENIGN',
    expectedTier: 'SAFE',
    description: 'Ordinary Indian family conversation checking on lunch, dinner, groceries, and evening arrival',
    callerId: '+91 98765 11111',
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
      'Hi Ammamma, did you have lunch?',
      'I will come home around six this evening.',
      'Do you need me to pick up anything on the way?',
      'Okay, I will get the vegetables and some curd.',
      'This weekend we will all have dinner together.',
    ],
  },
  {
    id: '02_suspicious_payment',
    number: '02',
    name: '02 — Suspicious Payment Call',
    label: '02 — Suspicious Payment Call',
    category: 'SUSPICIOUS',
    type: 'SUSPICIOUS / MEDIUM',
    language: 'English',
    groundTruth: 'SCAM',
    expectedTier: 'MEDIUM',
    description: 'Unexpected UPI payment inquiry escalating to time pressure to authorize cancellation',
    callerId: '+91 98765 22222',
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
      'Hello, I am calling regarding a payment that appears to have been initiated from your account.',
      'We need to verify whether this transaction was authorized.',
      'Please open your UPI app while I explain what you need to check.',
      'There is a verification request showing on your screen.',
      'You only have a few minutes to resolve this urgent matter and cancel the debit.',
    ],
  },
  {
    id: '03_cybercrime_otp_en',
    number: '03',
    name: '03 — Cybercrime / OTP Scam',
    label: '03 — Cybercrime / OTP Scam',
    category: 'SCAM — ENGLISH',
    type: 'SCAM',
    language: 'English',
    groundTruth: 'SCAM',
    expectedTier: 'HIGH / CRITICAL',
    description: 'Officer Sharma impersonation, arrest warrant intimidation, isolation, and acute OTP extraction',
    callerId: '+91 98765 00001',
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
    id: '04_cybercrime_otp_hi',
    number: '04',
    name: '04 — Cybercrime / OTP Scam',
    label: '04 — Cybercrime / OTP Scam',
    category: 'SCAM — HINDI',
    type: 'SCAM',
    language: 'Hindi/Hinglish',
    groundTruth: 'SCAM',
    expectedTier: 'HIGH / CRITICAL',
    description: 'Mumbai Cyber Crime Branch impersonation in natural Hindi/Hinglish with account freeze and OTP extraction',
    callerId: '+91 98765 00002',
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
      'Namaste, this is Officer Sharma from Mumbai Cyber Crime branch investigating your identity.',
      'Aapke bank account par illegal money laundering charges hain. All your bank accounts will be frozen and confiscated.',
      'You only have fifteen minutes to resolve this urgent matter before police arrest.',
      'Stay on the line with me, call disconnect mat karna aur do not tell anyone or your family.',
      'Aapke phone par SMS aaya hai, read me the six digit OTP verification code right now.',
    ],
  },
  {
    id: '05_bank_otp_te',
    number: '05',
    name: '05 — Bank / OTP Scam',
    label: '05 — Bank / OTP Scam',
    category: 'SCAM — TELUGU',
    type: 'SCAM',
    language: 'Telugu/Teluglish',
    groundTruth: 'SCAM',
    expectedTier: 'HIGH / CRITICAL',
    description: 'Bank security department impersonation in Telugu/Teluglish with account freeze and OTP extraction',
    callerId: '+91 98765 00003',
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
      'Namaskaram, this is the bank fraud investigation department calling about your account.',
      'Mee account nundi illegal money laundering transactions jarigayi. All your bank accounts will be frozen immediately.',
      'Immediate action required before the system locks down, within fifteen minutes arrest warrant issue avutundi.',
      'Line lo undandi, do not hang up this call and do not discuss this with your family.',
      'Mee mobile ki SMS vachindi, read the six digit OTP verification code to me right now.',
    ],
  },
  // --- Additional Historical & Specialized Scenarios ---
  {
    id: 'bank_alert',
    number: '06',
    name: 'Legitimate Bank Alert',
    label: 'Legitimate Bank Alert',
    category: 'ADDITIONAL',
    type: 'BENIGN',
    language: 'English',
    groundTruth: 'BENIGN',
    expectedTier: 'LOW',
    description: 'Official bank security notification advising app/branch verification without requesting credentials',
    callerId: '+91 98765 33333',
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
      'Hello, this is an official alert from your bank branch security desk.',
      'We noticed a card transaction that you may not recognize on your account statement.',
      'Please open your official bank app and verify the recent transaction history.',
      'If you did not authorize this, you can safely block the card directly through the app.',
      'Remember that the bank will never ask you to disclose your PIN or password over the phone.',
    ],
  },
  {
    id: 'courier_scam',
    number: '07',
    name: 'Courier / Digital Payment Scam',
    label: 'Courier / Digital Payment Scam',
    category: 'ADDITIONAL',
    type: 'SCAM',
    language: 'English',
    groundTruth: 'SCAM',
    expectedTier: 'HIGH',
    description: 'Detained parcel delivery scam with delivery clearance fee, line isolation, and UPI transfer demand',
    callerId: '+91 98765 44444',
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
      'This is the courier dispatch service regarding a parcel linked to your mobile number.',
      'There is an outstanding delivery verification charge that needs to be cleared immediately.',
      'If you do not complete the verification today, the parcel will be returned to origin.',
      'Stay on the line with me, do not disconnect while we complete the verification.',
      'Send money through wire transfer or UPI to complete the delivery clearance right now.',
    ],
  },
]

/**
 * Deterministic evaluation outcome mapping per requirement:
 * SCAM + MEDIUM/HIGH/CRITICAL = TRUE POSITIVE
 * SCAM + SAFE/LOW = FALSE NEGATIVE
 * BENIGN + SAFE/LOW = TRUE NEGATIVE
 * BENIGN + MEDIUM/HIGH/CRITICAL = FALSE POSITIVE
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
