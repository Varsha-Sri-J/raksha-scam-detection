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

  // UI Micro-States
  const [lastSpeechTimestamp, setLastSpeechTimestamp] = useState(null)
  const [isProcessingSpeech, setIsProcessingSpeech] = useState(false)
  const [selectedTactic, setSelectedTactic] = useState(null)

  const wsRef = useRef(null)
  const feedEndRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const processingTimerRef = useRef(null)

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

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${protocol}//${window.location.host}/ws/call/${sessionId}`

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (!isMounted) return
        setConnectionStatus('connected')
        setErrorNotification(null)
      }

      ws.onclose = () => {
        if (!isMounted) return
        setConnectionStatus('offline')
        // Auto-reconnect after 2 seconds
        reconnectTimerRef.current = setTimeout(connectWs, 2000)
      }

      ws.onerror = () => {
        if (!isMounted) return
        setConnectionStatus('offline')
        ws.close()
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (!msg || !msg.type) return

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
      if (processingTimerRef.current) {
        clearTimeout(processingTimerRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [sessionId])

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

  // Handle Mock Scam Simulation
  const handleSimulateScam = async () => {
    if (isSimulating) return
    setIsSimulating(true)
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
      setIsSimulating(false)
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
        calleeName="Margaret H."
        callerNumber="+1 (800) 555-0199"
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
              onSimulate={handleSimulateScam}
              onSendTranscript={handleSendTranscript}
              isSimulating={isSimulating}
              disabled={connectionStatus === 'offline'}
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
