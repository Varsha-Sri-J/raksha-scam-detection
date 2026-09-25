import React, { useState, useEffect, useRef } from 'react'
import Header from './components/Header'
import SessionBar from './components/SessionBar'
import ThreatGauge from './components/ThreatGauge'
import LiveWaveform from './components/LiveWaveform'
import TranscriptFeed from './components/TranscriptFeed'
import { CANONICAL_TACTICS } from './components/TacticMatrix'
import TacticEvidenceInspector from './components/TacticEvidenceInspector'
import RiskTimeline from './components/RiskTimeline'
import AlertPanel from './components/AlertPanel'
import ResponseStatus from './components/ResponseStatus'
import SimulationControls from './components/SimulationControls'
import AttackChain from './components/AttackChain'
import IncidentSummary from './components/IncidentSummary'
import CinematicBackground from './components/CinematicBackground'
import CampaignIntelligence from './components/CampaignIntelligence'
import { DEMO_SCENARIOS, calculateEvaluationOutcome } from './scenarios'
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
  const [sessionId, setSessionId] = useState(() => {
    if (typeof window !== 'undefined') {
      const urlParam = new URLSearchParams(window.location.search).get('session')
      if (urlParam) return urlParam
    }
    return 'session-prototype-01'
  })
  const [connectionStatus, setConnectionStatus] = useState('connecting')
  const [isSimulating, setIsSimulating] = useState(false)
  const [isLiveCall, setIsLiveCall] = useState(false)
  const [callStartedAt, setCallStartedAt] = useState(() => Date.now())
  const [callEndedAt, setCallEndedAt] = useState(null)
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

  // Attack Chain & Incident Summary (Phase 10D)
  const [attackChain, setAttackChain] = useState([])
  const [isIncidentSummaryOpen, setIsIncidentSummaryOpen] = useState(false)
  const [isListeningMic, setIsListeningMic] = useState(false)

  // Campaign Link Intelligence (Phase 10E)
  const [activeCampaign, setActiveCampaign] = useState(null)

  // Simulation Scenario & Evaluation States (Phase 10E)
  const [activeScenario, setActiveScenario] = useState(null)
  const [evaluationResult, setEvaluationResult] = useState(null)
  const [sessionNotice, setSessionNotice] = useState(null)
  const [isCooldownSuppressed, setIsCooldownSuppressed] = useState(false)

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

  // Derive callEnded state strictly from an actual EXECUTED intervention
  const isCallEnded = Boolean(
    latestIntervention && latestIntervention.status === 'EXECUTED'
  )

  // Freeze the timer at the actual elapsed duration when an intervention execution is received
  useEffect(() => {
    if (isCallEnded && !callEndedAt) {
      const now = Date.now()
      setCallEndedAt(now)
      setElapsedSeconds(Math.max(0, Math.floor((now - callStartedAt) / 1000)))
    }
  }, [isCallEnded, callEndedAt, callStartedAt])

  // Call Duration Timer: ticks while call is active, cleans up immediately when ended
  useEffect(() => {
    if (isCallEnded) {
      return
    }

    setElapsedSeconds(Math.max(0, Math.floor((Date.now() - callStartedAt) / 1000)))

    const timer = setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - callStartedAt) / 1000)))
    }, 1000)

    return () => clearInterval(timer)
  }, [isCallEnded, callStartedAt])

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
                // Hydrate attack chain from accumulated tactics
                const initialChain = sess.latest_risk.accumulated_tactics.map((tId) => ({
                  canonicalId: tId,
                  confidence: null,
                  evidence: null,
                  timestamp: sess.latest_risk.timestamp || Date.now() / 1000,
                }))
                setAttackChain(initialChain)
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

            // Hydrate timer baseline if session has created_at timestamp
            if (sess.created_at && typeof sess.created_at === 'number') {
              const startMs = sess.created_at < 1e12 ? sess.created_at * 1000 : sess.created_at
              setCallStartedAt(startMs)
              const executed = validInterventions.find((i) => i && i.status === 'EXECUTED')
              if (executed) {
                const endTs = executed.timestamp
                const endMs = endTs ? (endTs < 1e12 ? endTs * 1000 : endTs) : Date.now()
                setCallEndedAt(endMs)
                setElapsedSeconds(Math.max(0, Math.floor((endMs - startMs) / 1000)))
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

            // Maintain chronological attack chain based on arrival sequence
            setAttackChain((prev) => {
              const next = [...prev]
              msg.data.tactics.forEach((t) => {
                const canonicalId = t.canonicalId || t.tactic || t
                const existingIdx = next.findIndex((n) => n.canonicalId === canonicalId)
                if (existingIdx === -1) {
                  next.push({
                    canonicalId,
                    confidence: t.confidence ?? null,
                    evidence: t.evidence_text || null,
                    timestamp: t.timestamp || Date.now() / 1000,
                  })
                } else if (t.confidence !== undefined || t.evidence_text) {
                  next[existingIdx] = {
                    ...next[existingIdx],
                    confidence: t.confidence ?? next[existingIdx].confidence,
                    evidence: t.evidence_text || next[existingIdx].evidence,
                    timestamp: t.timestamp || next[existingIdx].timestamp,
                  }
                }
              })
              return next
            })
          }

          // 4. RISK_UPDATE
          else if (msg.type === 'RISK_UPDATE' && msg.data?.risk) {
            const riskData = msg.data.risk
            setRiskAssessment(riskData)

            if (msg.data.cooldown_applied !== undefined) {
              setIsCooldownSuppressed(Boolean(msg.data.cooldown_applied))
            }

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

              // Ensure all accumulated tactics appear in attack chain
              setAttackChain((prev) => {
                const next = [...prev]
                riskData.accumulated_tactics.forEach((tId) => {
                  if (!next.some((n) => n.canonicalId === tId)) {
                    next.push({
                      canonicalId: tId,
                      confidence: null,
                      evidence: null,
                      timestamp: riskData.timestamp || Date.now() / 1000,
                    })
                  }
                })
                return next
              })
            }
          }

          // 5. ALERT_TRIGGERED
          else if (msg.type === 'ALERT_TRIGGERED' && msg.data) {
            setActiveAlert(msg.data)
            setIsCooldownSuppressed(false)

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

          // 7. CAMPAIGN_UPDATE (Phase 10E)
          else if (msg.type === 'CAMPAIGN_UPDATE' && msg.data?.campaign) {
            setActiveCampaign(msg.data.campaign)
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
  const handleResetSession = (forcedSessionId = null) => {
    if (isSimulating) return null

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
    setAttackChain([])
    setIsIncidentSummaryOpen(false)
    setIsListeningMic(false)
    setLastSpeechTimestamp(null)
    setIsProcessingSpeech(false)
    const resetNow = Date.now()
    setCallStartedAt(resetNow)
    setCallEndedAt(null)
    setElapsedSeconds(0)
    setIsSimulating(false)
    setEvaluationResult(null)
    setIsCooldownSuppressed(false)
    setActiveScenario(null)

    // Generate new unique session ID (guard against React event objects)
    const newSessionId =
      typeof forcedSessionId === 'string' && forcedSessionId.trim()
        ? forcedSessionId.trim()
        : generateSessionId()
    sessionIdRef.current = newSessionId
    setSessionId(newSessionId)
    return newSessionId
  }

  // Pre-activation checks for live Browser Mic: ensure no stale simulation state leaks
  const handleBeforeStartMic = () => {
    if (transcripts.length > 0 || peakScore > 0 || attackChain.length > 0) {
      handleResetSession()
      setSessionNotice('NEW TEST SESSION')
      setTimeout(() => setSessionNotice(null), 2500)
    }
  }

  // Pre-activation checks for manual injection: ensure clean session
  const handleBeforeManualInput = () => {
    if (transcripts.length > 0 || peakScore > 0 || attackChain.length > 0) {
      handleResetSession()
      setSessionNotice('NEW TEST SESSION')
      setTimeout(() => setSessionNotice(null), 2500)
    }
  }

  // Handle Manual Transcript Injection
  const handleSendTranscript = ({ speaker, text }) => {
    if (!text.trim()) return

    // If session has existing finished simulation or threat data, clean reset first
    if (transcripts.length > 0 && (peakScore > 0 || attackChain.length > 0)) {
      handleResetSession()
      setSessionNotice('NEW TEST SESSION')
      setTimeout(() => setSessionNotice(null), 2500)
    }

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
          session_id: sessionIdRef.current,
          speaker,
          text: text.trim(),
          timestamp: Date.now() / 1000,
          is_final: true,
        },
      ])
    }
  }

  // Handle Mock Scam / Scenario Simulation
  const handleSimulateScenario = async (scenario) => {
    if (isSimulating) return
    setErrorNotification(null)

    // Requirement 3: Every simulation MUST start clean
    // Tear down previous session and generate fresh session ID
    if (wsRef.current) {
      wsRef.current.onopen = null
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      wsRef.current.onmessage = null
      wsRef.current.close()
      wsRef.current = null
    }

    const newSessionId = generateSessionId()
    sessionIdRef.current = newSessionId

    // Clear all previous simulation telemetry and downstream protection state
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
    setAttackChain([])
    setIsIncidentSummaryOpen(false)
    setIsListeningMic(false)
    setLastSpeechTimestamp(null)
    setIsProcessingSpeech(false)
    const simNow = Date.now()
    setCallStartedAt(simNow)
    setCallEndedAt(null)
    setElapsedSeconds(0)
    setIsSimulating(true)
    setActiveScenario(scenario)
    setEvaluationResult(null)
    setIsCooldownSuppressed(false)

    // Trigger fresh WebSocket connection for the new session
    setSessionId(newSessionId)

    // Allow socket to connect before simulation starts streaming
    await new Promise((r) => setTimeout(r, 150))

    try {
      const res = await fetch(`/api/sessions/${newSessionId}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chunks: scenario.chunks,
          delay_seconds: 0.65,
          callee_id: scenario.calleeId || 'Lakshmi R.',
          caregiver_contacts: scenario.caregivers || [
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
        if (sessionIdRef.current === newSessionId) {
          setErrorNotification(data.detail || 'Simulation request failed')
        }
      } else {
        const data = await res.json()
        const finalTier = data?.latest_risk?.risk_tier || 'SAFE'
        const outcome = calculateEvaluationOutcome(scenario.groundTruth, finalTier)
        setEvaluationResult({
          scenarioName: scenario.name,
          groundTruth: scenario.groundTruth,
          finalTier,
          outcome,
        })
      }
    } catch (err) {
      if (sessionIdRef.current === newSessionId) {
        setErrorNotification('Could not connect to simulation API')
      }
    } finally {
      if (sessionIdRef.current === newSessionId) {
        setIsSimulating(false)
      }
    }
  }

  const peakScore = Math.max(
    0,
    ...riskHistory.map((p) => (typeof p.score === 'number' ? p.score : 0)),
    typeof riskAssessment?.overall_score === 'number' ? riskAssessment.overall_score : 0
  )

  const hasIncidentData =
    attackChain.length > 0 ||
    peakScore > 0 ||
    Boolean(latestCaregiver) ||
    Boolean(latestUserWarning) ||
    Boolean(latestIntervention)

  return (
    <div className="app-container">
      {/* 0. Ambient Cinematic Liquid Metal Background */}
      <CinematicBackground riskTier={riskAssessment?.risk_tier || 'SAFE'} />

      {/* 1. Header with Connection & Mode Indicators */}
      <Header
        connectionStatus={connectionStatus}
        mode={currentMode}
        isListening={isListeningMic}
        isSimulating={isSimulating}
        hasIncidentData={hasIncidentData}
        onOpenIncidentSummary={() => setIsIncidentSummaryOpen(true)}
      />

      {/* 2. Call Session Context Bar */}
      <SessionBar
        sessionId={sessionId}
        callStatus="ACTIVE"
        calleeName="Lakshmi R."
        callerNumber="+91 98765 43210"
        caregiverName="Ananya R. (Daughter)"
        elapsedSeconds={elapsedSeconds}
        riskTier={riskAssessment?.risk_tier || 'SAFE'}
        isIntervened={Boolean(latestIntervention && latestIntervention.status === 'EXECUTED')}
        onResetSession={handleResetSession}
      />

      {/* Priority Alert Banner (when ALERT_TRIGGERED) */}
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

      {/* 3. Primary Command Center Grid: THREAT | TRANSCRIPT | PROTECTION */}
      <main className="dashboard-grid">
        {/* Left Column: THREAT (Gauge + Timeline) */}
        <div className="left-column">
          <ThreatGauge
            riskAssessment={riskAssessment}
            detectedCount={detectedTacticsCount}
            peakScore={peakScore}
          />
          <RiskTimeline
            history={riskHistory}
            currentScore={riskAssessment?.overall_score || 0}
          />
        </div>

        {/* Center Column: TRANSCRIPT (Live Waveform + Internal Scrolling Feed) */}
        <div className="center-column">
          <section className="glass-panel transcript-panel">
            <LiveWaveform
              lastActivityTimestamp={lastSpeechTimestamp}
              isSimulating={isSimulating}
              isListening={isListeningMic}
              mode={currentMode}
            />
            <TranscriptFeed
              transcripts={transcripts}
              isProcessing={isProcessingSpeech}
              scrollAnchorRef={feedEndRef}
            />
          </section>
        </div>

        {/* Right Column: PROTECTION */}
        <div className="right-column">
          <ResponseStatus
            riskTier={riskAssessment?.risk_tier || 'SAFE'}
            riskScore={riskAssessment?.overall_score || 0}
            hasAlert={Boolean(activeAlert)}
            mode={currentMode}
            transcriptsCount={transcripts.length}
            detectedCount={detectedTacticsCount}
            explanation={riskAssessment?.explanation || ''}
            caregiverRecord={latestCaregiver}
            userWarningRecord={latestUserWarning}
            interventionRecord={latestIntervention}
            calleeName="Lakshmi R."
            cooldownSuppressed={isCooldownSuppressed}
          />
        </div>
      </main>

      {/* 4. ATTACK CHAIN (Chronological Progression Track) */}
      <AttackChain
        attackChain={attackChain}
        onSelectTactic={(node) => {
          const tacticInfo = activeTactics[node.canonicalId] || {}
          setSelectedTactic({
            tactic: node.canonicalId,
            id: node.canonicalId,
            name: node.canonicalId,
            confidence: node.confidence ?? tacticInfo.confidence,
            evidence: node.evidence || tacticInfo.evidence,
            timestamp: node.timestamp,
          })
        }}
      />

      {/* 5. COMPACT TEST BENCH (Collapsible Docked Controls) */}
      <SimulationControls
        sessionId={sessionId}
        onSimulate={handleSimulateScenario}
        onResetSession={handleResetSession}
        onSendTranscript={handleSendTranscript}
        isSimulating={isSimulating}
        disabled={connectionStatus !== 'connected'}
        onListeningChange={setIsListeningMic}
        beforeStartMic={handleBeforeStartMic}
        beforeManualInput={handleBeforeManualInput}
        sessionNotice={sessionNotice}
        activeScenarioName={activeScenario?.name}
      />

      {/* 6. CAMPAIGN LINK INTELLIGENCE & ESCALATION (Phase 10E) */}
      <CampaignIntelligence
        campaign={activeCampaign}
        caregiverStatus={latestCaregiver?.status}
        onCampaignUpdate={setActiveCampaign}
      />

      {/* Dismissible Tactic Evidence Inspector Modal */}
      {selectedTactic && (
        <TacticEvidenceInspector
          tactic={selectedTactic}
          onClose={() => setSelectedTactic(null)}
        />
      )}

      {/* Incident Summary Modal */}
      <IncidentSummary
        isOpen={isIncidentSummaryOpen}
        onClose={() => setIsIncidentSummaryOpen(false)}
        onResetSession={handleResetSession}
        sessionId={sessionId}
        peakScore={peakScore}
        finalTier={riskAssessment?.risk_tier || 'SAFE'}
        attackChain={attackChain}
        caregiverRecord={latestCaregiver}
        userWarningRecord={latestUserWarning}
        interventionRecord={latestIntervention}
        elapsedSeconds={elapsedSeconds}
        evaluationResult={evaluationResult}
      />
    </div>
  )
}
