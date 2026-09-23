import React from 'react'
import {
  Lock,
  Clock,
  Shield,
  KeyRound,
  Banknote,
  AlertOctagon,
  HelpCircle,
  HeartHandshake,
  ChevronRight,
  Eye,
} from 'lucide-react'

export const CANONICAL_TACTICS = [
  {
    id: 'URGENCY',
    canonicalId: 'URGENCY',
    name: 'Urgency & Time Pressure',
    weight: '75%',
    desc: 'Artificial deadlines to bypass calm and rational thinking',
    icon: Clock,
  },
  {
    id: 'AUTHORITY_IMPERSONATION',
    canonicalId: 'AUTHORITY_IMPERSONATION',
    name: 'Authority Impersonation',
    weight: '90%',
    desc: 'Falsely claiming to represent police, government, or bank fraud dept',
    icon: Shield,
  },
  {
    id: 'ISOLATION_SECRECY',
    aliases: ['ISOLATION'],
    canonicalId: 'ISOLATION_SECRECY',
    name: 'Isolation & Secrecy',
    weight: '85%',
    desc: 'Demanding secrecy, forbidding consultation with family or advisors',
    icon: Lock,
  },
  {
    id: 'FINANCIAL_REDIRECTION',
    aliases: ['FINANCIAL_EXTRACTION'],
    canonicalId: 'FINANCIAL_REDIRECTION',
    name: 'Financial Redirection',
    weight: '95%',
    desc: 'Demanding immediate fund transfer, gift cards, or crypto deposit',
    icon: Banknote,
  },
  {
    id: 'FEAR_INTIMIDATION',
    aliases: ['THREAT_INTIMIDATION'],
    canonicalId: 'FEAR_INTIMIDATION',
    name: 'Threats & Intimidation',
    weight: '90%',
    desc: 'Threats of immediate arrest, asset seizure, or legal consequences',
    icon: AlertOctagon,
  },
  {
    id: 'INFORMATION_PHISHING',
    aliases: ['CREDENTIAL_HARVESTING'],
    canonicalId: 'INFORMATION_PHISHING',
    name: 'Credential Harvesting',
    weight: '80%',
    desc: 'Extracting OTPs, passwords, bank numbers, or identity documents',
    icon: KeyRound,
  },
  {
    id: 'CONFUSION_OVERWHELM',
    canonicalId: 'CONFUSION_OVERWHELM',
    name: 'Cognitive Overwhelm',
    weight: '60%',
    desc: 'Rapid contradictory commands and technical jargon to cause cognitive fatigue',
    icon: HelpCircle,
  },
  {
    id: 'RELIEF_FALSE_SALVATION',
    aliases: ['FALSE_SALVATION'],
    canonicalId: 'RELIEF_FALSE_SALVATION',
    name: 'False Salvation',
    weight: '70%',
    desc: 'Posing as the victim’s only ally or trusted rescuer in an emergency',
    icon: HeartHandshake,
  },
]

export default function TacticMatrix({
  activeTactics = {},
  accumulatedTactics = [],
  onSelectTactic,
}) {
  const getTacticMatch = (tacticDef) => {
    // 1. Direct match on canonicalId in activeTactics
    if (activeTactics[tacticDef.canonicalId]) {
      return activeTactics[tacticDef.canonicalId]
    }
    // 2. Direct match on id in activeTactics
    if (activeTactics[tacticDef.id]) {
      return activeTactics[tacticDef.id]
    }
    // 3. Match on aliases in activeTactics
    if (tacticDef.aliases) {
      for (const alias of tacticDef.aliases) {
        if (activeTactics[alias]) return activeTactics[alias]
      }
    }
    // 4. Check accumulatedTactics array
    const inAccumulated =
      accumulatedTactics.includes(tacticDef.canonicalId) ||
      accumulatedTactics.includes(tacticDef.id) ||
      (tacticDef.aliases && tacticDef.aliases.some((a) => accumulatedTactics.includes(a)))

    if (inAccumulated) {
      return { active: true }
    }

    return null
  }

  const detectedCount = CANONICAL_TACTICS.filter((t) => Boolean(getTacticMatch(t))).length

  return (
    <section className="glass-panel tactics-panel">
      <div className="panel-header tactics-header">
        <div className="panel-title">
          <Lock size={16} color="var(--accent-cyan)" />
          <span>Manipulation Taxonomy</span>
        </div>
        <div className="taxonomy-summary-badge">
          <span className="taxonomy-count-active">{detectedCount}</span>
          <span className="taxonomy-count-total">/ 8 Detected</span>
        </div>
      </div>

      <div className="tactics-list">
        {CANONICAL_TACTICS.map((tactic) => {
          const match = getTacticMatch(tactic)
          const isActive = Boolean(match)
          const confidence =
            match && typeof match === 'object' && match.confidence
              ? Math.round(match.confidence * 100)
              : null
          const Icon = tactic.icon || Lock

          const cardData = {
            ...tactic,
            isActive,
            confidence,
            evidence: match?.evidence || match?.evidence_text || null,
            utterance: match?.utterance || null,
            timestamp: match?.timestamp || null,
          }

          return (
            <div
              key={tactic.canonicalId}
              className={`tactic-card ${isActive ? 'active' : 'idle'} ${
                isActive ? 'clickable' : ''
              }`}
              onClick={() => {
                if (isActive && onSelectTactic) {
                  onSelectTactic(cardData)
                }
              }}
              title={
                isActive
                  ? 'Click to inspect verbatim evidence & classification confidence'
                  : 'Idle manipulation category'
              }
              role={isActive ? 'button' : undefined}
              tabIndex={isActive ? 0 : undefined}
            >
              <div className="tactic-header">
                <div className="tactic-identity">
                  <div className={`tactic-icon-box ${isActive ? 'active' : ''}`}>
                    <Icon size={14} />
                  </div>
                  <span className="tactic-name">{tactic.name}</span>
                </div>

                <div className="tactic-meta-status">
                  <span className={`tactic-status ${isActive ? 'active' : ''}`}>
                    {isActive
                      ? confidence
                        ? `DETECTED ${confidence}%`
                        : 'DETECTED'
                      : 'IDLE'}
                  </span>
                  {isActive && (
                    <Eye size={13} className="inspect-icon" title="View Evidence" />
                  )}
                </div>
              </div>

              <p className="tactic-desc">{tactic.desc}</p>

              {isActive && cardData.evidence && (
                <div className="tactic-evidence-preview">
                  <span className="evidence-snippet">
                    "{cardData.evidence.length > 55
                      ? cardData.evidence.substring(0, 55) + '...'
                      : cardData.evidence}"
                  </span>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
