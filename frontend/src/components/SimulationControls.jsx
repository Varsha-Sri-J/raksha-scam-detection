import React, { useState, useEffect, useRef } from 'react'
import { Send, RefreshCw, RotateCcw, Terminal, Mic, Square, Edit3, X, ChevronDown } from 'lucide-react'
import { DEMO_SCENARIOS } from '../scenarios'

// Browser Web Speech API feature detection
const SpeechRecognition =
  typeof window !== 'undefined'
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null
const isSpeechRecognitionSupported = Boolean(SpeechRecognition)

export default function SimulationControls({
  sessionId,
  onSimulate,
  onResetSession,
  onSendTranscript,
  isSimulating = false,
  disabled = false,
  onListeningChange = null,
  beforeStartMic = null,
  beforeManualInput = null,
  sessionNotice = null,
  activeScenarioName = null,
}) {
  const [inputText, setInputText] = useState('')
  const [speaker, setSpeaker] = useState('CALLER')
  const [isListening, setIsListening] = useState(false)
  const [interimText, setInterimText] = useState('')
  const [micError, setMicError] = useState(null)
  const [showManualModal, setShowManualModal] = useState(false)
  const [showScenarioMenu, setShowScenarioMenu] = useState(false)
  const [selectedScenario, setSelectedScenario] = useState(null)

  const dropdownRef = useRef(null)
  const recognitionRef = useRef(null)
  const isListeningRef = useRef(false)
  const lastSentTranscriptRef = useRef('')
  const lastSentTimestampRef = useRef(0)

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowScenarioMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Notify parent if mic listening state changes
  useEffect(() => {
    if (onListeningChange) {
      onListeningChange(isListening)
    }
  }, [isListening, onListeningChange])

  // Stop microphone listening cleanly
  const stopMic = () => {
    isListeningRef.current = false
    setIsListening(false)
    setInterimText('')
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop()
      } catch (e) {
        // Ignore errors when already stopped
      }
    }
  }

  // Start browser Web Speech API recognition
  const startMic = () => {
    if (!isSpeechRecognitionSupported) {
      setMicError(
        'Browser microphone is unavailable in this browser. Please use Chrome/Edge or manual injection.'
      )
      return
    }
    if (disabled) {
      setMicError('Cannot start microphone while offline.')
      return
    }
    setMicError(null)
    setInterimText('')

    try {
      const recognition = new SpeechRecognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-IN'

      recognition.onstart = () => {
        isListeningRef.current = true
        setIsListening(true)
        setMicError(null)
      }

      recognition.onresult = (event) => {
        let interim = ''
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const transcript = event.results[i][0].transcript
          if (event.results[i].isFinal) {
            const trimmed = transcript.trim()
            const now = Date.now()
            if (
              trimmed &&
              (trimmed !== lastSentTranscriptRef.current || now - lastSentTimestampRef.current > 1500)
            ) {
              lastSentTranscriptRef.current = trimmed
              lastSentTimestampRef.current = now
              onSendTranscript({
                speaker,
                text: trimmed,
              })
            }
          } else {
            interim += transcript
          }
        }
        setInterimText(interim)
      }

      recognition.onerror = (event) => {
        if (event.error === 'not-allowed' || event.error === 'permission-denied') {
          setMicError('Microphone access denied in browser.')
          stopMic()
        } else if (event.error !== 'no-speech' && event.error !== 'aborted') {
          setMicError(`Speech error: ${event.error}`)
        }
      }

      recognition.onend = () => {
        if (isListeningRef.current) {
          try {
            recognition.start()
          } catch (e) {}
        } else {
          setIsListening(false)
          setInterimText('')
        }
      }

      recognitionRef.current = recognition
      recognition.start()
    } catch (err) {
      setMicError(`Failed to initialize microphone: ${err.message}`)
      stopMic()
    }
  }

  useEffect(() => {
    if (isListeningRef.current) {
      stopMic()
    }
  }, [sessionId])

  useEffect(() => {
    if (disabled && isListeningRef.current) {
      stopMic()
      setMicError('Microphone paused: disconnected.')
    }
  }, [disabled])

  useEffect(() => {
    return () => {
      isListeningRef.current = false
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch (e) {}
      }
    }
  }, [])

  const handlePrimarySimulateClick = () => {
    setShowScenarioMenu(false)
    const scenarioToRun =
      selectedScenario ||
      DEMO_SCENARIOS[Math.floor(Math.random() * DEMO_SCENARIOS.length)]
    onSimulate(scenarioToRun)
  }

  const handleSelectScenario = (sc) => {
    setSelectedScenario(sc)
    setShowScenarioMenu(false)
    onSimulate(sc)
  }

  const handleStartMicClick = () => {
    if (beforeStartMic) {
      beforeStartMic()
    }
    startMic()
  }

  const handleToggleManualModal = () => {
    if (!showManualModal && beforeManualInput) {
      beforeManualInput()
    }
    setShowManualModal((prev) => !prev)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!inputText.trim()) return

    onSendTranscript({
      speaker,
      text: inputText.trim(),
    })
    setInputText('')
    setShowManualModal(false)
  }

  return (
    <section className="demo-dock" aria-label="Demo Operations Dock">
      {/* Session Notification Toast */}
      {sessionNotice && (
        <div className="session-notice-toast">
          {sessionNotice}
        </div>
      )}

      {/* Floating Modal / Popover for Manual Injection */}
      {showManualModal && (
        <div className="manual-injection-popover" role="dialog" aria-label="Manual Utterance Injection">
          <div className="popover-header">
            <span className="popover-title">Manual Utterance Injection</span>
            <button
              type="button"
              className="popover-close-btn"
              onClick={() => setShowManualModal(false)}
              aria-label="Close dialog"
            >
              <X size={13} />
            </button>
          </div>

          <form className="popover-form" onSubmit={handleSubmit}>
            <div className="popover-form-row">
              <select
                className="popover-speaker-select font-mono"
                value={speaker}
                onChange={(e) => setSpeaker(e.target.value)}
                disabled={isSimulating || disabled}
                aria-label="Speaker"
              >
                <option value="CALLER">Caller (Scam)</option>
                <option value="CALLEE">Callee (Lakshmi R.)</option>
              </select>

              <input
                type="text"
                className="popover-input"
                placeholder="e.g. Read me the six digit OTP verification code..."
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                disabled={isSimulating || disabled}
                autoFocus
              />

              <button
                type="submit"
                className="popover-btn-inject"
                disabled={isSimulating || disabled || !inputText.trim()}
              >
                <Send size={11} />
                <span>Inject</span>
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Sleek Dock Bar */}
      <div className="demo-dock-bar glass-panel">
        <div className="dock-badge font-mono">
          <Terminal size={11} color="#10b981" />
          <span>DEMO</span>
        </div>

        <div className="dock-buttons">
          {/* Primary: Simulation with Compact Dropdown Selector */}
          <div className="sim-split-group" ref={dropdownRef}>
            <button
              type="button"
              className={`btn-dock btn-dock-primary ${isSimulating ? 'active-sim' : ''}`}
              onClick={handlePrimarySimulateClick}
              disabled={isSimulating || isListening || disabled}
              title="1-Click: Run simulation scenario (random selection if not chosen)"
            >
              <RefreshCw
                size={12}
                className={isSimulating ? 'dock-spin' : ''}
              />
              <span>
                {isSimulating
                  ? `Simulating ${activeScenarioName || selectedScenario?.name || 'Scenario'}...`
                  : '▶ SIMULATION'}
              </span>
            </button>

            <button
              type="button"
              className={`btn-dock btn-dock-dropdown ${showScenarioMenu ? 'active' : ''}`}
              onClick={() => setShowScenarioMenu((prev) => !prev)}
              disabled={isSimulating || isListening || disabled}
              aria-label="Select simulation scenario"
              title="Select specific scenario"
            >
              <ChevronDown size={11} />
            </button>

            {showScenarioMenu && (
              <div className="scenario-dropdown-menu glass-panel" role="menu">
                <div className="scenario-dropdown-header">
                  <span>SELECT SCENARIO</span>
                </div>
                {DEMO_SCENARIOS.map((sc) => (
                  <button
                    key={sc.id}
                    type="button"
                    className={`scenario-menu-item ${selectedScenario?.id === sc.id ? 'selected' : ''}`}
                    onClick={() => handleSelectScenario(sc)}
                  >
                    <div className="scenario-item-main">
                      <span className="scenario-item-name">{sc.name}</span>
                      <span className={`scenario-truth-pill truth-${sc.groundTruth.toLowerCase()}`}>
                        {sc.groundTruth}
                      </span>
                    </div>
                    <span className="scenario-item-desc">{sc.description}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Secondary: Browser Mic */}
          <button
            type="button"
            className={`btn-dock btn-dock-secondary btn-dock-mic ${isListening ? 'active' : ''}`}
            onClick={isListening ? stopMic : handleStartMicClick}
            disabled={isSimulating || disabled}
            title={
              isListening
                ? 'Stop browser microphone listening'
                : 'Start microphone audio detection via Web Speech API'
            }
          >
            {isListening ? (
              <>
                <span className="mic-pulse-dot" />
                <Square size={10} />
                <span>■ STOP MIC</span>
              </>
            ) : (
              <>
                <Mic size={12} />
                <span>🎙 BROWSER MIC</span>
              </>
            )}
          </button>

          {/* Secondary: Manual Injection Trigger */}
          <button
            type="button"
            className={`btn-dock btn-dock-secondary ${showManualModal ? 'active' : ''}`}
            onClick={handleToggleManualModal}
            disabled={isSimulating || disabled}
            title="Open manual transcript injection dialog"
          >
            <Edit3 size={11} />
            <span>✎ MANUAL INPUT</span>
          </button>

          {/* Subtle Secondary: Reset Session */}
          <button
            type="button"
            className="btn-dock btn-dock-subtle"
            onClick={() => onResetSession && onResetSession()}
            disabled={isSimulating}
            title="Generate clean session ID and reset all metrics"
          >
            <RotateCcw size={11} />
            <span>RESET SESSION</span>
          </button>
        </div>
      </div>

      {/* Live Interim Speech Feedback Banner when microphone is listening */}
      {isListening && (
        <div className="mic-listening-banner">
          <div className="mic-listening-header">
            <span className="mic-badge font-mono">LOCAL SPEECH RECOGNITION</span>
            <span className="mic-status-tag font-mono">
              <span className="pulse-dot-red" /> MIC ACTIVE
            </span>
            <span className="mic-speaker-hint">
              Attributed as: <strong>{speaker === 'CALLER' ? 'Caller (Scam)' : 'Callee (Senior)'}</strong>
            </span>
          </div>
          <div className="mic-interim-box">
            <span className="mic-interim-label font-mono">Heard:</span>
            <span className="mic-interim-text">
              {interimText
                ? `"${interimText}"`
                : 'Listening for speech... (speak a scam or benign phrase into your mic)'}
            </span>
          </div>
        </div>
      )}

      {/* Microphone Error Notification */}
      {micError && (
        <div className="mic-error-banner" role="alert">
          <span>{micError}</span>
          <button
            type="button"
            className="btn-dismiss-mic-error"
            onClick={() => setMicError(null)}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}
    </section>
  )
}
