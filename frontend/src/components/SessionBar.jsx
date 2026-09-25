import React from 'react'
import { Phone, User, Clock, ShieldCheck, Key, Users, PhoneOff } from 'lucide-react'

export default function SessionBar({
  sessionId,
  callStatus = 'ACTIVE',
  calleeName = 'Lakshmi R.',
  callerNumber = '+91 98765 43210',
  caregiverName = 'Ananya R. (Daughter)',
  elapsedSeconds = 0,
  riskTier = 'SAFE',
  isIntervened = false,
  onResetSession,
}) {
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }

  const getStatusDisplay = () => {
    if (isIntervened) {
      return (
        <span className="session-status-pill status-intervened">
          <PhoneOff size={11} style={{ marginRight: 4 }} />
          MOCK DISCONNECTED
        </span>
      )
    }

    const tierLower = (riskTier || 'SAFE').toLowerCase()
    return (
      <span className={`session-status-pill status-${tierLower}`}>
        {riskTier === 'CRITICAL' ? 'DEFENSE ENGAGED' : 'MONITORING ACTIVE'}
      </span>
    )
  }

  return (
    <section className="glass-panel session-bar" aria-label="Monitored Session Context">
      <div className="session-meta-group">
        {/* Session Identifier */}
        <div className="meta-item">
          <span className="meta-label">
            <Key size={10} style={{ marginRight: 3, verticalAlign: 'middle' }} />
            SESSION ID
          </span>
          <span className="meta-value font-mono" title={sessionId}>
            {sessionId}
          </span>
        </div>

        {/* Protected User Identity */}
        <div className="meta-item">
          <span className="meta-label">PROTECTED USER</span>
          <span className="meta-value">
            <User size={13} color="var(--accent-cyan)" />
            <strong>{calleeName}</strong>
            <span className="demo-tag" title="Demonstration Senior Profile">Senior Profile</span>
          </span>
        </div>

        {/* Emergency Family Contact */}
        <div className="meta-item">
          <span className="meta-label">EMERGENCY CAREGIVER</span>
          <span className="meta-value">
            <Users size={13} color="#94a3b8" />
            <span>{caregiverName}</span>
          </span>
        </div>

        {/* Inbound Call Caller ID */}
        <div className="meta-item">
          <span className="meta-label">MONITORED CALL</span>
          <span className="meta-value font-mono">
            <Phone size={13} color="var(--accent-rose)" /> {callerNumber}
            <span className="inbound-tag font-mono">INBOUND</span>
          </span>
        </div>

        {/* Call Elapsed Duration */}
        <div className="meta-item">
          <span className="meta-label">CALL DURATION</span>
          <span className="meta-value font-mono">
            <Clock size={13} color="var(--text-muted)" /> {formatDuration(elapsedSeconds)}
          </span>
        </div>
      </div>

      <div className="session-status-group">
        <div className="meta-item status-meta-item">
          <span className="meta-label">CHANNEL DEFENSE</span>
          <div className="defense-status-pill-group">
            {getStatusDisplay()}
            <span className="defense-active-pill">
              <ShieldCheck size={12} color="var(--accent-emerald)" />
              Protected
            </span>
          </div>
        </div>
      </div>
    </section>
  )
}
