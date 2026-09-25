import React from 'react'
import { AlertTriangle, ShieldAlert, X, ShieldX, ShieldCheck } from 'lucide-react'

export default function AlertPanel({ alert, onDismiss }) {
  if (!alert) return null

  const tier = (alert.risk_tier || 'HIGH').toUpperCase()
  const score = alert.overall_score !== undefined ? Math.round(alert.overall_score) : null

  const hasCaregiver = Array.isArray(alert.caregiver_notifications) && alert.caregiver_notifications.length > 0
  const hasWarning = Boolean(alert.user_warning)
  const hasIntervention = Boolean(alert.intervention)

  return (
    <div className="alert-panel-wrapper" role="alert" aria-live="assertive">
      <div className="alert-panel-card">
        <div className="alert-icon-container">
          <ShieldAlert size={26} className="alert-pulse-icon" />
        </div>

        <div className="alert-content-group">
          <div className="alert-heading-row">
            <span className="alert-badge-critical font-mono">
              {tier} RISK DETECTED
            </span>
            {score !== null && (
              <span className="alert-score-badge font-mono">
                Score: {score} / 100
              </span>
            )}
            <span className="alert-session-ref font-mono">
              SESSION: {alert.session_id}
            </span>
          </div>

          <h4 className="alert-title-text">
            Active Psychological Coercion or Scam Identified
          </h4>

          {/* Prominent Why RAKSHA Acted section */}
          <div className="alert-rationale-box">
            <span className="rationale-tag">WHY RAKSHA ACTED:</span>
            <p className="alert-explanation">
              {alert.explanation ||
                'High-confidence indicators of malicious social engineering or impersonation have been detected on this call.'}
            </p>
          </div>

          {alert.latest_evidence && (
            <div className="alert-evidence-container">
              <span className="evidence-header font-mono">TRIGGER EVIDENCE:</span>
              <span className="evidence-quote font-mono">
                "{alert.latest_evidence}"
              </span>
            </div>
          )}

          {/* Triggered Downstream Actions Strip */}
          {(hasCaregiver || hasWarning || hasIntervention) && (
            <div className="alert-actions-summary-row">
              <span className="actions-summary-label">DISPATCHED RESPONSES:</span>
              <div className="actions-summary-pills">
                {hasCaregiver && (
                  <span className="alert-action-chip sent">
                    MOCK SMS — SENT (Family Contact)
                  </span>
                )}
                {hasWarning && (
                  <span className="alert-action-chip delivered">
                    MOCK WARNING — DELIVERED (Callee Advisory)
                  </span>
                )}
                {hasIntervention && (
                  <span className="alert-action-chip executed">
                    MOCK — EXECUTED (Line Disconnect)
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Non-technical safety guidance */}
          <div className="alert-safety-guidance">
            <ShieldX size={13} color="#f87171" />
            <span>
              CRITICAL SAFETY RULE: Never share one-time passwords (OTPs), bank PINs, passwords, or transfer funds under urgency.
            </span>
          </div>
        </div>

        <button
          type="button"
          className="alert-dismiss-btn"
          onClick={onDismiss}
          title="Dismiss this alert banner"
          aria-label="Dismiss alert"
        >
          <X size={15} />
          <span>Dismiss</span>
        </button>
      </div>
    </div>
  )
}
