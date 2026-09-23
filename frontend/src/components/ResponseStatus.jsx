import React from 'react'
import { ShieldCheck, Bell, MessageSquare, PhoneOff, AlertCircle } from 'lucide-react'

export default function ResponseStatus({ riskTier = 'SAFE', hasAlert = false, mode = 'STANDBY' }) {
  const isHighRisk = riskTier === 'HIGH' || riskTier === 'CRITICAL' || hasAlert
  const capabilityTag = mode === 'SIMULATION' ? 'MOCK READY' : mode === 'LIVE_CALL' ? 'READY' : 'AVAILABLE'

  return (
    <div className="glass-panel response-status-panel">
      <div className="panel-header">
        <div className="panel-title">
          <ShieldCheck size={16} color="var(--accent-cyan)" />
          <span>Active Defense & Response Status</span>
        </div>
        <span className="live-guard-chip">
          <span className="live-guard-dot" />
          PROTECTION ENGAGED
        </span>
      </div>

      {/* Current Operational Status */}
      <div className="status-grid">
        <div className="status-metric-card">
          <div className="status-metric-header">
            <span className="status-metric-label">Semantic Analysis</span>
            <span className="operational-dot active" />
          </div>
          <span className="status-metric-value">Active (Local/Cloud)</span>
          <span className="status-metric-desc">Zero-lag streaming classifier</span>
        </div>

        <div className="status-metric-card">
          <div className="status-metric-header">
            <span className="status-metric-label">Threat Engine</span>
            <span className="operational-dot active" />
          </div>
          <span className="status-metric-value">Scoring Live</span>
          <span className="status-metric-desc">Cumulative psychological decay</span>
        </div>

        <div className={`status-metric-card ${isHighRisk ? 'warning-active' : ''}`}>
          <div className="status-metric-header">
            <span className="status-metric-label">Alert Trigger</span>
            <span className={`operational-dot ${isHighRisk ? 'triggered' : 'standby'}`} />
          </div>
          <span className="status-metric-value">
            {isHighRisk ? 'TRIGGERED (HIGH)' : 'Monitoring Normal'}
          </span>
          <span className="status-metric-desc">Instant UI & WebSocket dispatch</span>
        </div>
      </div>

      {/* Automated Protection & Safeguard Capabilities */}
      <div className="future-actions-section">
        <div className="future-actions-header">
          <AlertCircle size={13} color="var(--accent-cyan)" />
          <span>Automated Caregiver Interventions</span>
          <span className="phase7-badge">{capabilityTag}</span>
        </div>

        <div className="future-actions-list">
          <div className="future-action-item" title="Automated SMS to registered emergency family contacts (Live Twilio SMS / Mock delivery)">
            <div className="future-action-icon">
              <MessageSquare size={14} />
            </div>
            <div className="future-action-info">
              <span className="future-action-title">Caregiver SMS Alert</span>
              <span className="future-action-desc">Direct text dispatch with call transcript summary (Live Twilio / Mock)</span>
            </div>
            <span className="phase-tag">{capabilityTag}</span>
          </div>

          <div className="future-action-item" title="Injected AI voice warning into protected callee stream (Live Twilio Conference / Mock guard)">
            <div className="future-action-icon">
              <Bell size={14} />
            </div>
            <div className="future-action-info">
              <span className="future-action-title">Audio Guard Whisper</span>
              <span className="future-action-desc">Discreet audio advisory injected to protected listener (Live Conference / Mock)</span>
            </div>
            <span className="phase-tag">{capabilityTag}</span>
          </div>

          <div className="future-action-item" title="Emergency telephony disconnect via Twilio REST API on critical risk (Mock disconnect in simulation)">
            <div className="future-action-icon">
              <PhoneOff size={14} />
            </div>
            <div className="future-action-info">
              <span className="future-action-title">Emergency Call Terminate</span>
              <span className="future-action-desc">Immediate carrier-level line severance (Live Twilio / Mock)</span>
            </div>
            <span className="phase-tag">{capabilityTag}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
