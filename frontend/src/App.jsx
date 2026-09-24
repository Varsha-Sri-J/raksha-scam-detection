import React, { useState, useEffect, useRef } from 'react'
import Header from './components/Header'
import SessionBar from './components/SessionBar'
import ThreatGauge from './components/ThreatGauge'
import LiveWaveform from './components/LiveWaveform'
import TranscriptFeed from './components/TranscriptFeed'
import TacticMatrix, { CANONICAL_TACTICS } from './components/TacticMatrix'
import TacticEvidenceInspector from './components/TacticEvidenceInspector'
import RiskTimeline from './components/RiskTimeline'
import AlertPanel from './components/AlertPanel'
import ResponseStatus from './components/ResponseStatus'
import SimulationControls from './components/SimulationControls'
import { X } from 'lucide-react'

function generateSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `session-${crypto.randomUUID().slice(0, 8)}`
  }
  const rand = Math.random().toString(36).substring(2, 8)
  const time = Date.now().toString(36).slice(-4)
  return `session-${time}-${rand}`
}

export default function App() {
  const [sessionId, setSessionId] = useState('session-prototype-01')
  const [connectionStatus, setConnectionStatus] = useState('connecting')
  const [isSimulating, setIsSimulating] = useState(false)
  const [isLiveCall, setIsLiveCall] = useState(false)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)

  // Core Data States
  const [transcripts, setTranscripts] = useState([])
  const [riskAssessment, setRiskAssessment] = useState({
    overall_score: 0.0,
    risk_tier: 'SAFE',
    explanation: 'Baseline safe state. Monitoring call stream.',
    accumulated_tactics: [],
  })
  const [activeTactics, setActiveTactics] = useState({})
  const [riskHistory, setRiskHistory] = useState([])
  const [activeAlert, setActiveAlert] = useState(null)
  const [errorNotification, setErrorNotification] = useState(null)

  // Protection Execution States (Phase 10C)
  const [latestCaregiver, setLatestCaregiver] = useState(null)
  const [latestUserWarning, setLatestUserWarning] = useState(null)
  const [latestIntervention, setLatestIntervention] = useState(null)

  // UI Micro-States
  const [lastSpeechTimestamp, setLastSpeechTimestamp] = useState(null)
  const [isProcessingSpeech, setIsProcessingSpeech] = useState(false)
  const [selectedTactic, setSelectedTactic] = useState(null)

  const wsRef = useRef(null)
  const feedEndRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const processingTimerRef = useRef(null)
  const sessionIdRef = useRef(sessionId)

  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  // Call Duration Timer
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // Determine Operating Mode
  const currentMode = isSimulating ? 'SIMULATION' : isLiveCall ? 'LIVE_CALL' : 'STANDBY'

  // Count detected canonical tactics
  const detectedTacticsCount = CANONICAL_TACTICS.filter((t) => {
    if (activeTactics[t.canonicalId] || activeTactics[t.id]) return true
    if (t.aliases && t.aliases.some((a) => activeTactics[a])) return true
    if (riskAssessment?.accumulated_tactics) {
      if (
        riskAssessment.accumulated_tactics.includes(t.canonicalId) ||
        riskAssessment.accumulated_tactics.includes(t.id)
      ) {
        return true
      }
      if (t.aliases && t.aliases.some((a) => riskAssessment.accumulated_tactics.includes(a))) {
        return true
      }
    }
    return false
  }).length

  // WebSocket Connection with Auto-Reconnect
  useEffect(() => {
    let isMounted = true

    const connectWs = () => {
      if (!isMounted) return
      setConnectionStatus('connecting')

      // Ensure any existing socket is cleanly closed and detached
      if (wsRef.current && wsRef.current.readyState < WebSocket.CLOSING) {
        wsRef.current.onopen = null
        wsRef.current.onclose = null
        wsRef.current.onerror = null
        wsRef.current.onmessage = null
        wsRef.current.close()
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${protocol}//${window.location.host}/ws/call/${sessionId}`

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (!isMounted || wsRef.current !== ws) return
        setConnectionStatus('connected')
        setErrorNotification(null)
      }

      ws.onclose = () => {
        if (!isMounted || wsRef.current !== ws) return
        setConnectionStatus('offline')
        // Auto-reconnect after 2 seconds
        reconnectTimerRef.current = setTimeout(connectWs, 2000)
      }

      ws.onerror = () => {
        if (!isMounted || wsRef.current !== ws) return
        setConnectionStatus('offline')
        ws.close()
      }

      ws.onmessage = (event) => {
        if (!isMounted || wsRef.current !== ws) return
        try {
          const msg = JSON.parse(event.data)
          if (!msg || !msg.type) return

          // Guard against stale cross-session message leakage
          if (msg.data?.session_id && msg.data.session_id !== sessionIdRef.current) {
            return
          }
          if (msg.data?.session?.session_id && msg.data.session.session_id !== sessionIdRef.current) {
            return
          }

          // 1. SESSION_STATUS
          if (msg.type === 'SESSION_STATUS' && msg.data?.session) {
            const sess = msg.data.session
            if (sess.transcript_history && Array.isArray(sess.transcript_history)) {
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
              // Initialize risk history point
              if (sess.latest_risk.overall_score !== undefined) {
                setRiskHistory([
                  {
                    timestamp: sess.latest_risk.timestamp || Date.now() / 1000,
                    score: sess.latest_risk.overall_score,
                    tier: sess.latest_risk.risk_tier,
                  },
                ])
              }
            }

            // Phase 10C: Hydrate protection state from SESSION_STATUS history defensively
            const validNotifs = (sess.notification_history || []).filter(
              (n) => n && n.notification_id
            )
            if (validNotifs.length > 0) {
              const sorted = [...validNotifs].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
              setLatestCaregiver(sorted[0] || null)
            } else {
              setLatestCaregiver(null)
            }

            const validWarnings = (sess.user_warning_history || []).filter(
              (w) => w && w.warning_id
            )
            if (validWarnings.length > 0) {
              const sorted = [...validWarnings].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
              setLatestUserWarning(sorted[0] || null)
            } else {
              setLatestUserWarning(null)
            }

            const validInterventions = (sess.intervention_history || []).filter(
              (i) => i && i.intervention_id
            )
            if (validInterventions.length > 0) {
              const sorted = [...validInterventions].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
              setLatestIntervention(sorted[0] || null)
            } else {
              setLatestIntervention(null)
            }
          }

          // 2. TRANSCRIPT_UPDATE / TRANSCRIPT_STREAM
          else if (
            (msg.type === 'TRANSCRIPT_UPDATE' || msg.type === 'TRANSCRIPT_STREAM') &&
            msg.data?.segment
          ) {
            const newSeg = msg.data.segment
            setLastSpeechTimestamp(Date.now())
            setIsProcessingSpeech(true)

            if (processingTimerRef.current) {
              clearTimeout(processingTimerRef.current)
            }
            processingTimerRef.current = setTimeout(() => {
              setIsProcessingSpeech(false)
            }, 1800)

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
                  evidence_text: t.evidence_text,
                  utterance: msg.data.utterance || null,
                  timestamp: t.timestamp || Date.now() / 1000,
                }
              })
              return next
            })
          }

          // 4. RISK_UPDATE
          else if (msg.type === 'RISK_UPDATE' && msg.data?.risk) {
            const riskData = msg.data.risk
            setRiskAssessment(riskData)

            // Add point to chronological risk history
            setRiskHistory((prev) => {
              const newPt = {
                timestamp: riskData.timestamp || Date.now() / 1000,
                score: riskData.overall_score,
                tier: riskData.risk_tier,
              }
              return [...prev, newPt]
            })

            // Mark accumulated tactics
            if (riskData.accumulated_tactics) {
              setActiveTactics((prev) => {
                const next = { ...prev }
                riskData.accumulated_tactics.forEach((t) => {
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

            // Phase 10C: Ingest downstream protection execution records defensively
            if (Array.isArray(msg.data.caregiver_notifications)) {
              const validNotifs = msg.data.caregiver_notifications.filter(
                (n) => n && n.notification_id
              )
              if (validNotifs.length > 0) {
                const latest = [...validNotifs].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))[0]
                setLatestCaregiver(latest)
              }
            }
            if (msg.data.user_warning && msg.data.user_warning.warning_id) {
              setLatestUserWarning(msg.data.user_warning)
            }
            if (msg.data.intervention && msg.data.intervention.intervention_id) {
              setLatestIntervention(msg.data.intervention)
            }
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
        reconnectTimerRef.current = null
      }
      if (processingTimerRef.current) {
        clearTimeout(processingTimerRef.current)
        processingTimerRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.onopen = null
        wsRef.current.onclose = null
        wsRef.current.onerror = null
        wsRef.current.onmessage = null
        wsRef.current.close()
      }
    }
  }, [sessionId])

  // Handle Reset Demo / Fresh Session
  const handleResetSession = () => {
    if (isSimulating) return

    // Immediately tear down any active socket callbacks and connection
    if (wsRef.current) {
      wsRef.current.onopen = null
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      wsRef.current.onmessage = null
      wsRef.current.close()
      wsRef.current = null
    }

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (processingTimerRef.current) {
      clearTimeout(processingTimerRef.current)
      processingTimerRef.current = null
    }

    // Reset all UI states to clean baseline
    setTranscripts([])
    setRiskAssessment({
      overall_score: 0.0,
      risk_tier: 'SAFE',
      explanation: 'Baseline safe state. Monitoring call stream.',
      accumulated_tactics: [],
    })
    setActiveTactics({})
    setRiskHistory([])
    setActiveAlert(null)
    setLatestCaregiver(null)
    setLatestUserWarning(null)
    setLatestIntervention(null)
    setErrorNotification(null)
    setSelectedTactic(null)
    setLastSpeechTimestamp(null)
    setIsProcessingSpeech(false)
    setElapsedSeconds(0)
    setIsSimulating(false)

    // Generate new unique session ID
    const newSessionId = generateSessionId()
    sessionIdRef.current = newSessionId
    setSessionId(newSessionId)
  }

  // Handle Manual Transcript Injection
  const handleSendTranscript = ({ speaker, text }) => {
    if (!text.trim()) return

    const payload = {
      type: 'TRANSCRIPT_UPDATE',
      data: {
        speaker,
        text: text.trim(),
        is_final: true,
      },
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload))
    } else {
      // Offline fallback
      setTranscripts((prev) => [
        ...prev,
        {
          id: String(Date.now()),
          session_id: sessionId,
          speaker,
          text: text.trim(),
          timestamp: Date.now() / 1000,
          is_final: true,
        },
      ])
    }
  }

  // Fictional Indian 5-turn scam scenario for simulation
  const INDIAN_SCAM_CHUNKS = [
    'This is Officer Sharma from the Cyber Crime Department.',
    'An arrest warrant and account freeze have been issued against your bank account for money laundering.',
    'You must resolve this urgent matter within fifteen minutes before police officers arrive at your residence.',
    'Do not disconnect this line and do not tell your family or anyone about this investigation.',
    'Read me the six digit OTP verification code that was just sent to your mobile phone.',
  ]

  // Handle Mock Scam Simulation
  const handleSimulateScam = async () => {
    if (isSimulating || connectionStatus !== 'connected') return
    setIsSimulating(true)
    setErrorNotification(null)

    const targetSessionId = sessionId

    try {
      const res = await fetch(`/api/sessions/${targetSessionId}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chunks: INDIAN_SCAM_CHUNKS,
          delay_seconds: 0.6,
          callee_id: 'Lakshmi R.',
          caregiver_contacts: [
            {
              name: 'Ananya R.',
              phone_number: '+91 91234 56789',
              relationship: 'Daughter',
              enabled: true,
            },
          ],
        }),
      })
      if (!res.ok) {
        const data = await res.json()
        if (sessionIdRef.current === targetSessionId) {
          setErrorNotification(data.detail || 'Simulation request failed')
        }
      }
    } catch (err) {
      if (sessionIdRef.current === targetSessionId) {
        setErrorNotification('Could not connect to simulation API')
      }
    } finally {
      if (sessionIdRef.current === targetSessionId) {
        setIsSimulating(false)
      }
    }
  }

  return (
    <div className="app-container">
      {/* 1. Header with Connection & Mode Indicators */}
      <Header connectionStatus={connectionStatus} mode={currentMode} />

      {/* 2. Call Session Context Bar */}
      <SessionBar
        sessionId={sessionId}
        callStatus="ACTIVE"
        calleeName="Lakshmi R."
        callerNumber="+91 98765 43210"
        elapsedSeconds={elapsedSeconds}
        mode={currentMode}
      />

      {/* 3. Priority Alert Banner (when ALERT_TRIGGERED) */}
      {activeAlert && (
        <AlertPanel alert={activeAlert} onDismiss={() => setActiveAlert(null)} />
      )}

      {/* Error Banner */}
      {errorNotification && (
        <div className="error-banner">
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

      {/* 4. Main 3-Column Cyber Defense Intelligence Grid */}
      <main className="dashboard-grid">
        {/* Left Column: Hero Threat Gauge & Risk Timeline */}
        <div className="left-column">
          <ThreatGauge
            riskAssessment={riskAssessment}
            detectedCount={detectedTacticsCount}
          />
          <RiskTimeline
            history={riskHistory}
            currentScore={riskAssessment?.overall_score || 0}
          />
        </div>

        {/* Center Column: Live Waveform, Transcript Feed & Simulation Suite */}
        <div className="center-column">
          <section className="glass-panel transcript-panel">
            {/* Audio Speech Activity Visualizer */}
            <LiveWaveform
              lastActivityTimestamp={lastSpeechTimestamp}
              isSimulating={isSimulating}
            />

            {/* Live Dual-Speaker Transcript Feed */}
            <TranscriptFeed
              transcripts={transcripts}
              isProcessing={isProcessingSpeech}
              scrollAnchorRef={feedEndRef}
            />

            {/* Test & Simulation Controls */}
            <SimulationControls
              sessionId={sessionId}
              onSimulate={handleSimulateScam}
              onResetSession={handleResetSession}
              onSendTranscript={handleSendTranscript}
              isSimulating={isSimulating}
              disabled={connectionStatus !== 'connected'}
            />
          </section>
        </div>

        {/* Right Column: Manipulation Taxonomy Matrix */}
        <div className="right-column">
          <TacticMatrix
            activeTactics={activeTactics}
            accumulatedTactics={riskAssessment?.accumulated_tactics || []}
            onSelectTactic={(tacticData) => setSelectedTactic(tacticData)}
          />
        </div>
      </main>

      {/* 5. Protection Actions & Caregiver Response Status */}
      <ResponseStatus
        riskTier={riskAssessment?.risk_tier || 'SAFE'}
        hasAlert={Boolean(activeAlert)}
        mode={currentMode}
        caregiverRecord={latestCaregiver}
        userWarningRecord={latestUserWarning}
        interventionRecord={latestIntervention}
      />

      {/* 6. Dismissible Tactic Evidence Inspector Modal */}
      {selectedTactic && (
        <TacticEvidenceInspector
          tactic={selectedTactic}
          onClose={() => setSelectedTactic(null)}
        />
      )}
    </div>
  )
}
