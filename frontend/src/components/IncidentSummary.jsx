import React from 'react'
import { X, ShieldAlert, CheckCircle2, Clock, Phone, AlertTriangle, MessageSquare, Bell, PhoneOff } from 'lucide-react'
import { TACTIC_DISPLAY_NAMES } from './AttackChain'

export default function IncidentSummary({
  isOpen = false,
  onClose,
  onResetSession,
  sessionId,
  peakScore = 0,
  finalTier = 'SAFE',
  attackChain = [],
  caregiverRecord = null,
  userWarningRecord = null,
  interventionRecord = null,
  elapsedSeconds = 0,
  evaluationResult = null,
}) {
  if (!isOpen) return null

  const formatDuration = (secs) => {
    const mins = Math.floor(secs / 60)
    const rem = secs % 60
    return `${String(mins).padStart(2, '0')}:${String(rem).padStart(2, '0')}`
  }

  const getTierClass = (tier) => {
    const t = (tier || 'SAFE').toLowerCase()
    return `tier-${t}`
  }

  return (
    <div className="inspector-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="summary-title">
      <div className="glass-panel incident-summary-modal" onClick={(e) => e.stopPropagation()}>
        <div className="incident-summary-header">
          <div className="summary-title-group">
            <ShieldAlert size={20} color="var(--accent-rose)" />
            <div>
              <h3 id="summary-title" className="summary-title">
                Incident Summary Report
              </h3>
              <span className="summary-session-id font-mono">
                SESSION: {sessionId} · DURATION: {formatDuration(elapsedSeconds)}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="inspector-close-btn"
            onClick={onClose}
            aria-label="Close incident summary"
          >
            <X size={18} />
          </button>
        </div>

        <div className="incident-summary-body">
          {/* Executive Metrics Overview */}
          <div className="summary-metrics-grid">
            <div className="summary-metric-card">
              <span className="metric-label">PEAK THREAT SCORE</span>
              <div className="metric-value-row">
                <span className={`metric-number ${getTierClass(finalTier)}`}>
                  {Math.round(peakScore)}
                </span>
                <span className="metric-max">/ 100</span>
              </div>
            </div>

            <div className="summary-metric-card">
              <span className="metric-label">FINAL RISK TIER</span>
              <span className={`summary-tier-badge ${getTierClass(finalTier)}`}>
                {finalTier}
              </span>
            </div>

            <div className="summary-metric-card">
              <span className="metric-label">TACTICS IDENTIFIED</span>
              <span className="metric-number-plain font-mono">
                {attackChain.length}
              </span>
            </div>
          </div>

          {/* DEMO / EVALUATION Outcome */}
          {evaluationResult && (
            <div className="summary-section">
              <div className="summary-section-heading-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <h4 className="summary-section-heading" style={{ margin: 0 }}>DEMO / EVALUATION</h4>
                <span className={`evaluation-outcome-badge outcome-${evaluationResult.outcome.toLowerCase().replace(' ', '-')}`}>
                  {evaluationResult.outcome}
                </span>
              </div>
              <div className="summary-evaluation-grid font-mono">
                <div className="eval-item">
                  <span className="eval-label">SCENARIO:</span>
                  <span className="eval-val">{evaluationResult.scenarioName}</span>
                </div>
                <div className="eval-item">
                  <span className="eval-label">GROUND TRUTH:</span>
                  <span className="eval-val">{evaluationResult.groundTruth}</span>
                </div>
                <div className="eval-item">
                  <span className="eval-label">FINAL TIER:</span>
                  <span className="eval-val">{evaluationResult.finalTier}</span>
                </div>
                <div className="eval-item">
                  <span className="eval-label">OUTCOME:</span>
                  <span className="eval-val">{evaluationResult.outcome}</span>
                </div>
              </div>
            </div>
          )}

          {/* Observed Psychological Tactics */}
          <div className="summary-section">
            <h4 className="summary-section-heading">Observed Attack Progression</h4>
            {attackChain.length === 0 ? (
              <p className="summary-empty-note">No malicious tactics were detected during this session.</p>
            ) : (
              <div className="summary-tactics-list">
                {attackChain.map((item, idx) => (
                  <div key={idx} className="summary-tactic-row">
                    <span className="tactic-step-number font-mono">0{idx + 1}</span>
                    <span className="summary-tactic-name">
                      {TACTIC_DISPLAY_NAMES[item.canonicalId] || item.canonicalId}
                    </span>
                    {item.confidence && (
                      <span className="summary-confidence-tag font-mono">
                        {Math.round(item.confidence * 100)}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Protective Actions Ledger */}
          <div className="summary-section">
            <h4 className="summary-section-heading">Safeguards & Defense Ledger</h4>
            <div className="summary-actions-ledger">
              {/* Caregiver Alert */}
              <div className="ledger-item">
                <div className="ledger-icon-box">
                  <MessageSquare size={14} />
                </div>
                <div className="ledger-info">
                  <span className="ledger-title">Family Protection Alert (Ananya R.)</span>
                  <span className="ledger-detail font-mono">
                    {caregiverRecord
                      ? `${(caregiverRecord.provider || 'mock').toUpperCase()} SMS — ${caregiverRecord.status}`
                      : 'NOT TRIGGERED'}
                  </span>
                </div>
                <span className={`ledger-status-pill ${caregiverRecord?.status === 'SENT' ? 'sent' : 'neutral'}`}>
                  {caregiverRecord?.status || 'IDLE'}
                </span>
              </div>

              {/* Protected User Warning */}
              <div className="ledger-item">
                <div className="ledger-icon-box">
                  <Bell size={14} />
                </div>
                <div className="ledger-info">
                  <span className="ledger-title">Protected User Advisory (Lakshmi R.)</span>
                  <span className="ledger-detail font-mono">
                    {userWarningRecord
                      ? `${(userWarningRecord.provider || 'mock').toUpperCase()} VOICE — ${userWarningRecord.status}`
                      : 'NOT TRIGGERED'}
                  </span>
                </div>
                <span className={`ledger-status-pill ${userWarningRecord?.status === 'DELIVERED' ? 'delivered' : 'neutral'}`}>
                  {userWarningRecord?.status || 'IDLE'}
                </span>
              </div>

              {/* Intervention */}
              <div className="ledger-item">
                <div className="ledger-icon-box">
                  <PhoneOff size={14} />
                </div>
                <div className="ledger-info">
                  <span className="ledger-title">Telephony Intercept (DISCONNECT)</span>
                  <span className="ledger-detail font-mono">
                    {interventionRecord
                      ? `${(interventionRecord.provider || 'mock').toUpperCase()} — ${interventionRecord.status}`
                      : 'NOT TRIGGERED'}
                  </span>
                </div>
                <span className={`ledger-status-pill ${interventionRecord?.status === 'EXECUTED' ? 'executed' : 'neutral'}`}>
                  {interventionRecord?.status || 'IDLE'}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="incident-summary-footer">
          <button type="button" className="btn-summary-dismiss" onClick={onClose}>
            Close Report
          </button>
          {onResetSession && (
            <button
              type="button"
              className="btn-summary-reset"
              onClick={() => {
                onClose()
                onResetSession()
              }}
            >
              Start Fresh Session
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
