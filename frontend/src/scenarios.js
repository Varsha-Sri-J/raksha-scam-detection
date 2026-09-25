/**
 * Deterministic Demo Simulation Scenarios and Evaluation Model for RAKSHA.
 * 
 * Provides 5 realistic Indian conversational scenarios covering the full risk spectrum:
 * 1. Family Call (BENIGN -> SAFE)
 * 2. Legitimate Bank Alert (BENIGN -> LOW)
 * 3. Suspicious Payment Call (SCAM -> MEDIUM)
 * 4. Courier / Digital Payment Scam (SCAM -> HIGH)
 * 5. Cybercrime / OTP Scam (SCAM -> CRITICAL)
 * 
 * Evaluation Logic:
 * SCAM + MEDIUM/HIGH/CRITICAL = TRUE POSITIVE
 * SCAM + SAFE/LOW = FALSE NEGATIVE
 * BENIGN + SAFE/LOW = TRUE NEGATIVE
 * BENIGN + MEDIUM/HIGH/CRITICAL = FALSE POSITIVE
 */

export const DEMO_SCENARIOS = [
  {
    id: 'family_call',
    name: 'Family Call',
    label: 'Family Call',
    groundTruth: 'BENIGN',
    description: 'Ordinary Indian family conversation checking on lunch, dinner, groceries, and evening arrival',
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
    id: 'bank_alert',
    name: 'Legitimate Bank Alert',
    label: 'Legitimate Bank Alert',
    groundTruth: 'BENIGN',
    description: 'Official bank security notification advising app/branch verification without requesting credentials',
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
    id: 'suspicious_payment',
    name: 'Suspicious Payment Call',
    label: 'Suspicious Payment Call',
    groundTruth: 'SCAM',
    description: 'Unexpected UPI payment inquiry escalating to time pressure to authorize cancellation',
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
    id: 'courier_scam',
    name: 'Courier / Digital Payment Scam',
    label: 'Courier / Digital Payment Scam',
    groundTruth: 'SCAM',
    description: 'Detained parcel delivery scam with delivery clearance fee, line isolation, and UPI transfer demand',
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
  {
    id: 'cybercrime_otp',
    name: 'Cybercrime / OTP Scam',
    label: 'Cybercrime / OTP Scam',
    groundTruth: 'SCAM',
    description: 'Officer Sharma impersonation, arrest warrant intimidation, isolation, and acute OTP extraction',
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
