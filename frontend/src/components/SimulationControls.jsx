import React, { useState, useEffect, useRef } from 'react'
import { Send, RefreshCw, RotateCcw, Terminal, Mic, Square } from 'lucide-react'

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
}) {
  const [inputText, setInputText] = useState('')
  const [speaker, setSpeaker] = useState('CALLER')
  const [isListening, setIsListening] = useState(false)
  const [interimText, setInterimText] = useState('')
  const [micError, setMicError] = useState(null)

  const recognitionRef = useRef(null)
  const isListeningRef = useRef(false)
  const lastSentTranscriptRef = useRef('')
  const lastSentTimestampRef = useRef(0)

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
        'Browser microphone demo is unavailable in this browser. Use Chrome/Edge/Safari or the manual injection control.'
      )
      return
    }
    if (disabled) {
      setMicError('Cannot start microphone demo while offline.')
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
            // Deduplicate rapid duplicate final emissions from Web Speech engine
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
          setMicError(
            'Microphone permission denied. Please allow microphone access in your browser address bar.'
          )
          stopMic()
        } else if (event.error === 'no-speech') {
          // Normal pause in speaking, do not terminate session
        } else if (event.error === 'network') {
          setMicError('Speech recognition network error. Please check your internet connection.')
          stopMic()
        } else if (event.error !== 'aborted') {
          setMicError(`Speech recognition error: ${event.error}`)
        }
      }

      recognition.onend = () => {
        // If continuous recognition ends unexpectedly while still active, safely restart
        if (isListeningRef.current) {
          try {
            recognition.start()
          } catch (e) {
            // Browser may be closing or transitioning
          }
        } else {
          setIsListening(false)
          setInterimText('')
        }
      }

      recognitionRef.current = recognition
      recognition.start()
    } catch (err) {
      setMicError(`Failed to initialize speech recognition: ${err.message}`)
      stopMic()
    }
  }

  // When session resets, stop any active microphone demo cleanly
  useEffect(() => {
    if (isListeningRef.current) {
      stopMic()
    }
  }, [sessionId])

  // When connection drops, pause mic demo
  useEffect(() => {
    if (disabled && isListeningRef.current) {
      stopMic()
      setMicError('Microphone demo paused: WebSocket disconnected.')
    }
  }, [disabled])

  // Cleanup on unmount
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

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!inputText.trim()) return

    onSendTranscript({
      speaker,
      text: inputText.trim(),
    })
    setInputText('')
  }

  return (
    <div className="simulation-controls-wrapper">
      <div className="simulation-banner-header">
        <div className="simulation-title-group">
          <Terminal size={14} color="var(--accent-amber)" />
          <span className="simulation-title">Test & Simulation Suite</span>
        </div>
        <div className="simulation-tags-group">
          <span className="simulation-env-tag">
            Local Mock STT & Pipeline Injection
          </span>
          <span className="mic-demo-pill">BROWSER MIC DEMO</span>
        </div>
      </div>

      <div className="simulation-actions-bar">
        {/* 1. Run Scam Simulation Button */}
        <button
          type="button"
          className="btn-simulate-scam"
          onClick={onSimulate}
          disabled={isSimulating || isListening || disabled}
          title="Run 5-step mock scam scenario through the RAKSHA streaming pipeline"
        >
          <RefreshCw
            size={14}
            className={isSimulating ? 'simulate-icon spinning' : 'simulate-icon'}
          />
          <span>{isSimulating ? 'Streaming Simulation...' : 'Simulate Scam Scenario'}</span>
        </button>

        {/* 2. Browser Microphone Demo Button */}
        <button
          type="button"
          className={`btn-mic-demo ${isListening ? 'active' : ''}`}
          onClick={isListening ? stopMic : startMic}
          disabled={isSimulating || disabled}
          title={
            isListening
              ? 'Stop browser microphone listening'
              : 'Speak into your microphone to test live speech detection'
          }
        >
          {isListening ? (
            <>
              <span className="mic-pulse-dot" />
              <Square size={13} className="mic-stop-icon" />
              <span>⏹ Stop Browser Mic Demo</span>
            </>
          ) : (
            <>
              <Mic size={14} />
              <span>🎙 Start Browser Mic Demo</span>
            </>
          )}
        </button>

        {/* 3. Reset Demo / New Session Button */}
        <button
          type="button"
          className="btn-reset-session"
          onClick={onResetSession}
          disabled={isSimulating}
          title="Start a fresh demo session with a new unique session ID"
        >
          <RotateCcw size={13} />
          <span>New Session</span>
        </button>

        {/* 4. Manual Utterance Injection Form */}
        <form className="manual-inject-form" onSubmit={handleSubmit}>
          <select
            className="speaker-dropdown"
            value={speaker}
            onChange={(e) => setSpeaker(e.target.value)}
            disabled={isSimulating || disabled}
            aria-label="Speaker identity"
          >
            <option value="CALLER">Caller (Impersonator / Scammer)</option>
            <option value="CALLEE">Callee (Lakshmi R. / Senior)</option>
          </select>

          <input
            type="text"
            className="utterance-input"
            placeholder="Inject test utterance (e.g. 'This is Officer Sharma from Cyber Crime, share your 6-digit OTP')..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={isSimulating || disabled}
          />

          <button
            type="submit"
            className="btn-inject-send"
            disabled={isSimulating || disabled || !inputText.trim()}
          >
            <Send size={13} />
            <span>Inject</span>
          </button>
        </form>
      </div>

      {/* Live Interim Speech Feedback Strip */}
      {isListening && (
        <div className="mic-listening-banner">
          <div className="mic-listening-header">
            <span className="mic-badge">BROWSER MIC DEMO</span>
            <span className="mic-status-tag">
              <span className="pulse-dot-red" /> LISTENING
            </span>
            <span className="mic-speaker-hint">
              Routing speech as: <strong>{speaker === 'CALLER' ? 'Caller (Impersonator)' : 'Callee (Senior)'}</strong>
            </span>
          </div>
          <div className="mic-interim-box">
            <span className="mic-interim-label">Hearing:</span>
            <span className="mic-interim-text">
              {interimText
                ? `"${interimText}"`
                : 'Listening for speech... (speak an Indian scam or benign phrase)'}
            </span>
          </div>
        </div>
      )}

      {/* Microphone Error Notification */}
      {micError && (
        <div className="mic-error-banner">
          <span>{micError}</span>
          <button
            type="button"
            className="btn-dismiss-mic-error"
            onClick={() => setMicError(null)}
          >
            ×
          </button>
        </div>
      )}
    </div>
  )
}
