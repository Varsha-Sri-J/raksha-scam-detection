import React from 'react'
import { GitCommit, ArrowRight, ShieldAlert, Clock, AlertTriangle } from 'lucide-react'

export const TACTIC_DISPLAY_NAMES = {
  AUTHORITY_IMPERSONATION: 'Authority Impersonation',
  FEAR_INTIMIDATION: 'Fear / Intimidation',
  THREAT_INTIMIDATION: 'Fear / Intimidation',
  URGENCY: 'Urgency & Time Pressure',
  ISOLATION_SECRECY: 'Isolation / Secrecy',
  ISOLATION: 'Isolation / Secrecy',
  FINANCIAL_REDIRECTION: 'Financial Redirection',
  FINANCIAL_EXTRACTION: 'Financial Redirection',
  INFORMATION_PHISHING: 'Information Phishing',
  CREDENTIAL_HARVESTING: 'Information Phishing',
  CONFUSION_OVERWHELM: 'Confusion / Overwhelm',
  RELIEF_FALSE_SALVATION: 'Relief / False Salvation',
  FALSE_SALVATION: 'Relief / False Salvation',
}

export default function AttackChain({ attackChain = [], onSelectTactic = null }) {
  const getDisplayName = (id) => {
    return TACTIC_DISPLAY_NAMES[id] || id.replace(/_/g, ' ')
  }

  const formatStepTime = (timestamp) => {
    if (!timestamp) return null
    return new Date(
      typeof timestamp === 'number' && timestamp < 1e12 ? timestamp * 1000 : timestamp
    ).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  return (
    <div className="glass-panel attack-chain-container" aria-label="Chronological Attack Chain">
      <div className="attack-chain-header">
        <div className="attack-chain-title-group">
          <GitCommit size={15} color="var(--accent-cyan)" />
          <h3 className="attack-chain-heading">Chronological Attack Chain</h3>
          <span className="attack-chain-subtitle">Observed Social Engineering Sequence</span>
        </div>
        <span className="chain-counter-pill font-mono">
          {attackChain.length} {attackChain.length === 1 ? 'Phase Detected' : 'Phases Detected'}
        </span>
      </div>

      {attackChain.length === 0 ? (
        <div className="attack-chain-empty">
          <span className="empty-chain-dot" />
          <span className="empty-chain-text">
            No psychological manipulation tactics detected yet — awaiting audio evidence
          </span>
        </div>
      ) : (
        <div className="attack-chain-track">
          {attackChain.map((node, index) => {
            const isLast = index === attackChain.length - 1
            const displayName = getDisplayName(node.canonicalId)
            const timeString = formatStepTime(node.timestamp)

            return (
              <React.Fragment key={`${node.canonicalId}-${index}`}>
                <div
                  className={`attack-chain-node ${isLast ? 'latest-node' : ''} ${
                    onSelectTactic ? 'clickable-node' : ''
                  }`}
                  onClick={() => {
                    if (onSelectTactic) {
                      onSelectTactic(node)
                    }
                  }}
                  title={
                    onSelectTactic
                      ? `Click to view evidence for ${displayName}`
                      : displayName
                  }
                  role={onSelectTactic ? 'button' : undefined}
                  tabIndex={onSelectTactic ? 0 : undefined}
                >
                  <div className="node-index-badge font-mono">0{index + 1}</div>
                  <div className="node-info">
                    <span className="node-name">{displayName}</span>
                    <div className="node-meta-row">
                      {node.confidence !== null && node.confidence !== undefined && (
                        <span className="node-confidence font-mono">
                          {Math.round(node.confidence * 100)}% Match
                        </span>
                      )}
                      {timeString && (
                        <span className="node-time font-mono">
                          <Clock size={9} style={{ marginRight: 2 }} />
                          {timeString}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {!isLast && (
                  <div className="attack-chain-arrow" aria-hidden="true">
                    <ArrowRight size={13} />
                  </div>
                )}
              </React.Fragment>
            )
          })}
        </div>
      )}
    </div>
  )
}
