import React from 'react'
import { AlertTriangle, ShieldAlert, X, ShieldX } from 'lucide-react'

export default function AlertPanel({ alert, onDismiss }) {
  if (!alert) return null

  const tier = (alert.risk_tier || 'HIGH').toUpperCase()
  const score = alert.overall_score !== undefined ? Math.round(alert.overall_score) : null

  return (
    <div className="alert-panel-wrapper" role="alert" aria-live="assertive">
      <div className="alert-panel-card">
        <div className="alert-icon-container">
          <ShieldAlert size={28} className="alert-pulse-icon" />
        </div>

        <div className="alert-content-group">
          <div className="alert-heading-row">
            <span className="alert-badge-critical">
              {tier} RISK DETECTED
            </span>
            {score !== null && (
              <span className="alert-score-badge">
                Score: {score} / 100
              </span>
            )}
            <span className="alert-session-ref">
              Session {alert.session_id}
            </span>
          </div>

          <h4 className="alert-title-text">
            Active Psychological Coercion or Scam Identified
          </h4>

          <p className="alert-explanation">
            {alert.explanation ||
              'High-confidence indicators of malicious social engineering or impersonation have been detected on this call.'}
          </p>

          {alert.latest_evidence && (
            <div className="alert-evidence-container">
              <span className="evidence-header">TRIGGER EVIDENCE:</span>
              <span className="evidence-quote font-mono">
                "{alert.latest_evidence}"
              </span>
            </div>
          )}

          {/* Static informational safety recommendation */}
          <div className="alert-safety-guidance">
            <ShieldX size={14} color="#fca5a5" />
            <span>
              CRITICAL SAFETY RULE: Never share one-time passwords (OTPs), bank PINs, passwords, or gift card codes over the phone.
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
          <X size={16} />
          <span>Dismiss</span>
        </button>
      </div>
    </div>
  )
}
