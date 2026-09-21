import React, { useState, useEffect, useRef } from 'react'
import {
  Shield,
  Phone,
  Radio,
  Activity,
  AlertTriangle,
  Send,
  RefreshCw,
  Clock,
  User,
  CheckCircle2,
  Lock,
  X,
} from 'lucide-react'

// Manipulation categories taxonomy matching backend canonical categories & aliases
const TACTIC_DEFINITIONS = [
  {
    id: 'URGENCY',
    canonicalId: 'URGENCY',
    name: 'Urgency & Time Pressure',
    weight: '75%',
    desc: 'Imposing artificial deadlines to bypass rational thinking',
  },
  {
    id: 'AUTHORITY_IMPERSONATION',
    canonicalId: 'AUTHORITY_IMPERSONATION',
    name: 'Authority Impersonation',
    weight: '90%',
    desc: 'Falsely claiming to be police, bank fraud, or government',
  },
  {
    id: 'ISOLATION',
    canonicalId: 'ISOLATION_SECRECY',
    name: 'Isolation & Secrecy',
    weight: '85%',
    desc: 'Demanding secrecy, preventing calls to family members',
  },
  {
    id: 'FINANCIAL_EXTRACTION',
    canonicalId: 'FINANCIAL_REDIRECTION',
    name: 'Financial Extraction',
    weight: '95%',
    desc: 'Demanding gift cards, crypto, or remote access',
  },
  {
    id: 'THREAT_INTIMIDATION',
    canonicalId: 'FEAR_INTIMIDATION',
    name: 'Threats & Intimidation',
    weight: '90%',
    desc: 'Threats of immediate arrest, asset seizure, or harm',
  },
  {
    id: 'CREDENTIAL_HARVESTING',
    canonicalId: 'INFORMATION_PHISHING',
    name: 'Credential Harvesting',
    weight: '80%',
    desc: 'Extracting OTPs, passwords, or identity numbers',
  },
  {
    id: 'CONFUSION_OVERWHELM',
    canonicalId: 'CONFUSION_OVERWHELM',
    name: 'Cognitive Overwhelm',
    weight: '60%',
    desc: 'Rapid legal jargon and contradictory instructions',
  },
  {
    id: 'FALSE_SALVATION',
    canonicalId: 'RELIEF_FALSE_SALVATION',
    name: 'False Salvation',
    weight: '70%',
    desc: 'Posing as the victim’s only ally or protector',
  },
]

export default function App() {
  const [sessionId, setSessionId] = useState('session-prototype-01')
  const [connected, setConnected] = useState(false)
  const [transcripts, setTranscripts] = useState([])
  const [riskAssessment, setRiskAssessment] = useState({
    overall_score: 0.0,
    risk_tier: 'SAFE',
    explanation: 'Baseline safe state.',
    accumulated_tactics: [],
  })
  const [activeTactics, setActiveTactics] = useState({})
  const [activeAlert, setActiveAlert] = useState(null)
  const [errorNotification, setErrorNotification] = useState(null)
  const [simulating, setSimulating] = useState(false)
  const [inputText, setInputText] = useState('')
  const [speaker, setSpeaker] = useState('CALLER')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  const wsRef = useRef(null)
  const feedEndRef = useRef(null)
  const reconnectTimerRef = useRef(null)

  // Timer
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // Auto-scroll transcript
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcripts])

  // WebSocket Connection with Auto-Reconnect
  useEffect(() => {
    let isMounted = true

    const connectWs = () => {
      if (!isMounted) return

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${protocol}//${window.location.host}/ws/call/${sessionId}`

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (!isMounted) return
        setConnected(true)
        setErrorNotification(null)
      }

      ws.onclose = () => {
        if (!isMounted) return
        setConnected(false)
        // Auto-reconnect after 2 seconds
        reconnectTimerRef.current = setTimeout(connectWs, 2000)
      }

      ws.onerror = () => {
        if (!isMounted) return
        setConnected(false)
        ws.close()
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (!msg || !msg.type) return

          // 1. SESSION_STATUS
          if (msg.type === 'SESSION_STATUS' && msg.data?.session) {
            const sess = msg.data.session
            if (sess.transcript_history) {
              setTranscripts(sess.transcript_history)
            }
            if (sess.latest_risk) {
              setRiskAssessment(sess.latest_risk)
              if (sess.latest_risk.accumulated_tactics) {
                const initTactics = {}
                sess.latest_risk.accumulated_tactics.forEach((t) => {
                  initTactics[t] = { active: true }
                })
                setActiveTactics(initTactics)
              }
            }
          }
          // 2. TRANSCRIPT_UPDATE / TRANSCRIPT_STREAM
          else if (
            (msg.type === 'TRANSCRIPT_UPDATE' || msg.type === 'TRANSCRIPT_STREAM') &&
            msg.data?.segment
          ) {
            const newSeg = msg.data.segment
            setTranscripts((prev) => {
              const existingIdx = prev.findIndex((s) => s.id && s.id === newSeg.id)
              if (existingIdx >= 0) {
                const updated = [...prev]
                updated[existingIdx] = newSeg
                return updated
              }
              return [...prev, newSeg]
            })
          }
          // 3. TACTIC_DETECTED
          else if (msg.type === 'TACTIC_DETECTED' && msg.data?.tactics) {
            setActiveTactics((prev) => {
              const next = { ...prev }
              msg.data.tactics.forEach((t) => {
                const key = t.tactic || t
                next[key] = {
                  active: true,
                  confidence: t.confidence,
                  evidence: t.evidence_text,
                  timestamp: t.timestamp || Date.now() / 1000,
                }
              })
              return next
            })
          }
          // 4. RISK_UPDATE
          else if (msg.type === 'RISK_UPDATE' && msg.data?.risk) {
            setRiskAssessment(msg.data.risk)
            if (msg.data.risk.accumulated_tactics) {
              setActiveTactics((prev) => {
                const next = { ...prev }
                msg.data.risk.accumulated_tactics.forEach((t) => {
                  if (!next[t]) {
                    next[t] = { active: true }
                  }
                })
                return next
              })
            }
          }
          // 5. ALERT_TRIGGERED
          else if (msg.type === 'ALERT_TRIGGERED' && msg.data) {
            setActiveAlert(msg.data)
          }
          // 6. ERROR
          else if (msg.type === 'ERROR' && msg.data?.error) {
            setErrorNotification(msg.data.error)
          }
        } catch (err) {
          console.error('Error parsing WS message:', err)
        }
      }
    }

    connectWs()

    return () => {
      isMounted = false
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [sessionId])

  const handleSendTranscript = (e) => {
    e.preventDefault()
    if (!inputText.trim()) return

    const payload = {
      type: 'TRANSCRIPT_UPDATE',
      data: {
        speaker: speaker,
        text: inputText.trim(),
        is_final: true,
      },
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload))
    } else {
      // Local fallback if disconnected
      setTranscripts((prev) => [
        ...prev,
        {
          id: String(Date.now()),
          session_id: sessionId,
          speaker: speaker,
          text: inputText.trim(),
          timestamp: Date.now() / 1000,
          is_final: true,
        },
      ])
    }

    setInputText('')
  }

  const handleSimulateScam = async () => {
    if (simulating) return
    setSimulating(true)
    setErrorNotification(null)
    try {
      const res = await fetch(`/api/sessions/${sessionId}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delay_seconds: 0.6 }),
      })
      if (!res.ok) {
        const data = await res.json()
        setErrorNotification(data.detail || 'Simulation request failed')
      }
    } catch (err) {
      setErrorNotification('Could not connect to simulation API')
    } finally {
      setSimulating(false)
    }
  }

  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }

  // Threat Gauge calculation
  const radius = 80
  const circumference = 2 * Math.PI * radius
  const score = riskAssessment.overall_score || 0.0
  const strokeDashoffset = circumference - (score / 100) * circumference
  const riskTier = (riskAssessment.risk_tier || 'SAFE').toLowerCase()

  return (
    <div className="app-container">
      {/* Header */}
      <header className="glass-panel header">
        <div className="brand">
          <div className="brand-icon">
            <Shield size={22} />
          </div>
          <div>
            <h1 className="brand-title">RAKSHA</h1>
            <p className="brand-subtitle">Real-Time Scam & Manipulation Defense</p>
          </div>
        </div>

        <div className="status-badge-container">
          <div className={`status-badge ${connected ? 'online' : 'offline'}`}>
            <span className="pulse-dot" />
            <span>{connected ? 'CORE WS CONNECTED' : 'WS CONNECTING / OFFLINE'}</span>
          </div>
        </div>
      </header>

      {/* Call Session Overview Bar */}
      <section className="glass-panel session-bar">
        <div className="session-meta-group">
          <div className="meta-item">
            <span className="meta-label">Session ID</span>
            <span className="meta-value">{sessionId}</span>
          </div>
          <div className="meta-item">
            <span className="meta-label">Monitored Call</span>
            <span className="meta-value">
              <Phone size={14} color="var(--accent-rose)" /> +1 (800) 555-0199
            </span>
          </div>
          <div className="meta-item">
            <span className="meta-label">Protected Callee</span>
            <span className="meta-value">
              <User size={14} color="var(--accent-cyan)" /> Margaret H. (Senior)
            </span>
          </div>
          <div className="meta-item">
            <span className="meta-label">Call Duration</span>
            <span className="meta-value">
              <Clock size={14} color="var(--text-muted)" /> {formatDuration(elapsedSeconds)}
            </span>
          </div>
        </div>

        <div className="meta-item">
          <span className="meta-label">System Phase</span>
          <span className="meta-value" style={{ color: 'var(--accent-cyan)' }}>
            Phase 4 (Live Stream)
          </span>
        </div>
      </section>

      {/* Main 3-Column Layout */}
      <main className="dashboard-grid">
        {/* Left Column: Risk Gauge */}
        <section className="glass-panel threat-panel">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Activity size={18} color="var(--accent-cyan)" />
            <h2 style={{ fontSize: '1rem', fontWeight: 600 }}>Risk Engine</h2>
          </div>

          <div className="threat-gauge-wrapper">
            <svg className="gauge-svg" viewBox="0 0 200 200">
              <circle className="gauge-bg" cx="100" cy="100" r={radius} />
              <circle
                className={`gauge-progress ${riskTier}`}
                cx="100"
                cy="100"
                r={radius}
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
              />
            </svg>
            <div className="gauge-value-container">
              <span className="gauge-number">{score.toFixed(0)}</span>
              <span className="gauge-label">Threat Score</span>
            </div>
          </div>

          <div className={`threat-tier-pill ${riskTier}`}>
            {riskAssessment.risk_tier || 'SAFE'}
          </div>

          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center', maxWidth: 240, minHeight: 36 }}>
            {riskAssessment.explanation || 'Baseline safe state.'}
          </p>
        </section>

        {/* Center Column: Live Transcript Stream */}
        <section className="glass-panel transcript-panel">
          <div className="panel-header">
            <div className="panel-title">
              <Radio size={16} color="var(--accent-cyan)" />
              <span>Live Call Audio Transcript</span>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {transcripts.length} utterances
            </span>
          </div>

          {/* Active Alert Banner */}
          {activeAlert && (
            <div className="alert-banner" style={{ margin: '12px 16px 0' }}>
              <div className="alert-banner-content">
                <AlertTriangle className="alert-icon" size={20} />
                <div className="alert-text-group">
                  <span className="alert-title">
                    {activeAlert.risk_tier} Risk Alert (Score: {activeAlert.overall_score?.toFixed(0)})
                  </span>
                  <span className="alert-desc">{activeAlert.explanation}</span>
                  {activeAlert.latest_evidence && (
                    <span className="alert-evidence">"{activeAlert.latest_evidence}"</span>
                  )}
                </div>
              </div>
              <button
                type="button"
                className="alert-dismiss"
                onClick={() => setActiveAlert(null)}
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Error Notification Banner */}
          {errorNotification && (
            <div className="error-banner" style={{ margin: '12px 16px 0' }}>
              <span>{errorNotification}</span>
              <button
                type="button"
                className="error-dismiss"
                onClick={() => setErrorNotification(null)}
              >
                <X size={14} />
              </button>
            </div>
          )}

          <div className="transcript-feed">
            {transcripts.length === 0 ? (
              <div className="empty-transcript">
                <Radio size={32} opacity={0.3} />
                <p style={{ fontSize: '0.88rem' }}>No audio utterances yet.</p>
                <p style={{ fontSize: '0.75rem' }}>Inject a test utterance below or click "Simulate Scam" to test real-time detection.</p>
              </div>
            ) : (
              transcripts.map((t, idx) => (
                <div
                  key={t.id || idx}
                  className={`transcript-bubble ${t.speaker === 'CALLER' ? 'caller' : 'callee'}`}
                >
                  <div className="bubble-meta">
                    <span className={`speaker-tag ${t.speaker === 'CALLER' ? 'caller' : 'callee'}`}>
                      {t.speaker === 'CALLER' ? 'CALLER / SCAMMER' : 'CALLEE / PROTECTED'}
                    </span>
                    <span className="bubble-time">
                      {new Date((t.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </span>
                  </div>
                  <div className="bubble-text">{t.text}</div>
                </div>
              ))
            )}
            <div ref={feedEndRef} />
          </div>

          <form className="transcript-input-bar" onSubmit={handleSendTranscript}>
            <select
              className="speaker-select"
              value={speaker}
              onChange={(e) => setSpeaker(e.target.value)}
            >
              <option value="CALLER">Caller (Inbound)</option>
              <option value="CALLEE">Callee (Protected)</option>
            </select>
            <input
              type="text"
              className="transcript-input"
              placeholder="Inject test utterance (e.g., 'This is officer Miller from the police')..."
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
            />
            <button type="submit" className="btn-send">
              <Send size={14} />
              <span>Send</span>
            </button>
            <button
              type="button"
              className="btn-simulate"
              onClick={handleSimulateScam}
              disabled={simulating}
              title="Run Mock STT scam scenario through backend pipeline"
            >
              <RefreshCw size={13} className={simulating ? 'pulse-dot' : ''} />
              <span>{simulating ? 'Simulating...' : 'Simulate Scam'}</span>
            </button>
          </form>
        </section>

        {/* Right Column: Tactics Taxonomy Monitor */}
        <section className="glass-panel tactics-panel">
          <div className="panel-header">
            <div className="panel-title">
              <Lock size={16} color="var(--accent-cyan)" />
              <span>Manipulation Taxonomy</span>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              8 Categories
            </span>
          </div>

          <div className="tactics-list">
            {TACTIC_DEFINITIONS.map((tactic) => {
              const match =
                activeTactics[tactic.canonicalId] ||
                activeTactics[tactic.id] ||
                (riskAssessment.accumulated_tactics &&
                  (riskAssessment.accumulated_tactics.includes(tactic.canonicalId) ||
                    riskAssessment.accumulated_tactics.includes(tactic.id)))
              const isActive = Boolean(match)
              const confidence =
                match && typeof match === 'object' && match.confidence
                  ? Math.round(match.confidence * 100)
                  : null

              return (
                <div
                  key={tactic.id}
                  className={`tactic-card ${isActive ? 'active' : ''}`}
                >
                  <div className="tactic-header">
                    <span className="tactic-name">{tactic.name}</span>
                    <span className={`tactic-status ${isActive ? 'active' : ''}`}>
                      {isActive
                        ? confidence
                          ? `DETECTED (${confidence}%)`
                          : 'DETECTED'
                        : 'IDLE'}
                    </span>
                  </div>
                  <p className="tactic-desc">{tactic.desc}</p>
                </div>
              )
            })}
          </div>
        </section>
      </main>
    </div>
  )
}
