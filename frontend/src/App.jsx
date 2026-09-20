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
} from 'lucide-react'

// Manipulation categories taxonomy matching backend
const TACTIC_DEFINITIONS = [
  { id: 'URGENCY', name: 'Urgency & Time Pressure', weight: '75%', desc: 'Imposing artificial deadlines to bypass rational thinking' },
  { id: 'AUTHORITY_IMPERSONATION', name: 'Authority Impersonation', weight: '90%', desc: 'Falsely claiming to be police, bank fraud, or government' },
  { id: 'ISOLATION', name: 'Isolation & Secrecy', weight: '85%', desc: 'Demanding secrecy, preventing calls to family members' },
  { id: 'FINANCIAL_EXTRACTION', name: 'Financial Extraction', weight: '95%', desc: 'Demanding gift cards, crypto, or remote access' },
  { id: 'THREAT_INTIMIDATION', name: 'Threats & Intimidation', weight: '90%', desc: 'Threats of immediate arrest, asset seizure, or harm' },
  { id: 'CREDENTIAL_HARVESTING', name: 'Credential Harvesting', weight: '80%', desc: 'Extracting OTPs, passwords, or identity numbers' },
  { id: 'CONFUSION_OVERWHELM', name: 'Cognitive Overwhelm', weight: '60%', desc: 'Rapid legal jargon and contradictory instructions' },
  { id: 'FALSE_SALVATION', name: 'False Salvation', weight: '70%', desc: 'Posing as the victim’s only ally or protector' },
]

export default function App() {
  const [sessionId, setSessionId] = useState('session-prototype-01')
  const [connected, setConnected] = useState(false)
  const [transcripts, setTranscripts] = useState([])
  const [riskAssessment, setRiskAssessment] = useState({
    overall_score: 0.0,
    risk_tier: 'SAFE',
    triggered_tactics: [],
  })
  const [inputText, setInputText] = useState('')
  const [speaker, setSpeaker] = useState('CALLER')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  const wsRef = useRef(null)
  const feedEndRef = useRef(null)

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

  // WebSocket Connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/call/${sessionId}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
    }

    ws.onclose = () => {
      setConnected(false)
    }

    ws.onerror = () => {
      setConnected(false)
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'SESSION_STATUS' && msg.data?.session) {
          if (msg.data.session.transcript_history) {
            setTranscripts(msg.data.session.transcript_history)
          }
          if (msg.data.session.latest_risk) {
            setRiskAssessment(msg.data.session.latest_risk)
          }
        } else if (msg.type === 'TRANSCRIPT_STREAM' && msg.data?.segment) {
          setTranscripts((prev) => [...prev, msg.data.segment])
        } else if (msg.type === 'RISK_UPDATE' && msg.data?.risk) {
          setRiskAssessment(msg.data.risk)
        }
      } catch (err) {
        console.error('Error parsing WS message:', err)
      }
    }

    return () => {
      ws.close()
    }
  }, [sessionId])

  const handleSendTranscript = (e) => {
    e.preventDefault()
    if (!inputText.trim()) return

    const payload = {
      type: 'TRANSCRIPT_STREAM',
      data: {
        speaker: speaker,
        text: inputText.trim(),
        is_final: true,
      },
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload))
    } else {
      // Fallback to local state if WS is disconnected
      setTranscripts((prev) => [
        ...prev,
        {
          id: String(Date.now()),
          session_id: sessionId,
          speaker: speaker,
          text: inputText.trim(),
          timestamp: Date.now() / 1000,
        },
      ])
    }

    setInputText('')
  }

  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }

  // Gauge calculation (circumference of r=80 is 2 * PI * 80 ≈ 502.65)
  const radius = 80
  const circumference = 2 * Math.PI * radius
  const score = riskAssessment.overall_score || 0.0
  const strokeDashoffset = circumference - (score / 100) * circumference

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
            Phase 1 (Foundation)
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
                className="gauge-progress"
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

          <div className="threat-tier-pill safe">
            {riskAssessment.risk_tier} (Baseline)
          </div>

          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center', maxWidth: 220 }}>
            Phase 1 baseline. Semantic manipulation detection and dynamic scoring activate in Phase 2.
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

          <div className="transcript-feed">
            {transcripts.length === 0 ? (
              <div className="empty-transcript">
                <Radio size={32} opacity={0.3} />
                <p style={{ fontSize: '0.88rem' }}>No audio utterances yet.</p>
                <p style={{ fontSize: '0.75rem' }}>Send a test phrase below to verify live WebSocket pipeline.</p>
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
            {TACTIC_DEFINITIONS.map((tactic) => (
              <div key={tactic.id} className="tactic-card">
                <div className="tactic-header">
                  <span className="tactic-name">{tactic.name}</span>
                  <span className="tactic-status">IDLE (PHASE 2)</span>
                </div>
                <p className="tactic-desc">{tactic.desc}</p>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}
