import React from 'react'
import { Phone, User, Clock, ShieldCheck, Key } from 'lucide-react'

export default function SessionBar({
  sessionId,
  callStatus = 'ACTIVE',
  calleeName = 'Lakshmi R.',
  callerNumber = '+91 98765 43210',
  elapsedSeconds = 0,
  mode = 'STANDBY',
}) {
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }

  const getStatusBadge = () => {
    const statusLower = (callStatus || 'ACTIVE').toLowerCase()
    return (
      <span className={`session-status-pill status-${statusLower}`}>
        {callStatus}
      </span>
    )
  }

  return (
    <section className="glass-panel session-bar">
      <div className="session-meta-group">
        <div className="meta-item">
          <span className="meta-label">
            <Key size={11} style={{ marginRight: 4, verticalAlign: 'middle' }} />
            Session ID
          </span>
          <span className="meta-value font-mono" title={sessionId}>
            {sessionId}
          </span>
        </div>

        <div className="meta-item">
          <span className="meta-label">Monitored Call</span>
          <span className="meta-value">
            <Phone size={14} color="var(--accent-rose)" /> {callerNumber}
            <span className="inbound-tag">INBOUND</span>
          </span>
        </div>

        <div className="meta-item">
          <span className="meta-label">Protected Callee</span>
          <span className="meta-value">
            <User size={14} color="var(--accent-cyan)" /> {calleeName}
            <span className="demo-tag" title="Demonstration Senior Profile">Demo Profile</span>
          </span>
        </div>

        <div className="meta-item">
          <span className="meta-label">Call Duration</span>
          <span className="meta-value">
            <Clock size={14} color="var(--text-muted)" /> {formatDuration(elapsedSeconds)}
          </span>
        </div>
      </div>

      <div className="session-status-group">
        <div className="meta-item" style={{ textAlign: 'right' }}>
          <span className="meta-label">Channel Status</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
            {getStatusBadge()}
            <span className="defense-active-pill">
              <ShieldCheck size={13} color="var(--accent-emerald)" />
              Active Defense
            </span>
          </div>
        </div>
      </div>
    </section>
  )
}
