import React, { useEffect, useRef } from 'react'
import { Radio, Mic, User, PhoneCall, Sparkles } from 'lucide-react'

export default function TranscriptFeed({
  transcripts = [],
  isProcessing = false,
  scrollAnchorRef,
}) {
  const localFeedEndRef = useRef(null)
  const targetRef = scrollAnchorRef || localFeedEndRef

  useEffect(() => {
    targetRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcripts, isProcessing, targetRef])

  return (
    <div className="transcript-feed-container">
      <div className="panel-header transcript-header">
        <div className="panel-title">
          <Radio size={16} color="var(--accent-cyan)" />
          <span>Live Call Audio Transcript</span>
        </div>
        <div className="transcript-counter-badge">
          <span className="count-number">{transcripts.length}</span>
          <span className="count-label">Utterances</span>
        </div>
      </div>

      <div className="transcript-feed">
        {transcripts.length === 0 ? (
          <div className="empty-transcript">
            <Radio size={36} opacity={0.3} color="var(--accent-cyan)" />
            <p className="empty-title">Waiting for speech input...</p>
            <p className="empty-subtitle">
              Audio stream from monitored call will appear here in real time.
              You can also click <strong>"Simulate Scam"</strong> or inject test utterances below.
            </p>
          </div>
        ) : (
          transcripts.map((segment, idx) => {
            const isCaller = segment.speaker === 'CALLER'
            const timeString = segment.timestamp
              ? new Date(segment.timestamp * 1000).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })
              : ''

            return (
              <div
                key={segment.id || `seg-${idx}`}
                className={`transcript-bubble ${isCaller ? 'caller' : 'callee'}`}
              >
                <div className="bubble-meta">
                  <div className="speaker-identity">
                    {isCaller ? (
                      <PhoneCall size={12} className="meta-speaker-icon caller-icon" />
                    ) : (
                      <User size={12} className="meta-speaker-icon callee-icon" />
                    )}
                    <span className={`speaker-tag ${isCaller ? 'caller' : 'callee'}`}>
                      {isCaller ? 'CALLER / UNKNOWN' : 'CALLEE / PROTECTED'}
                    </span>
                  </div>
                  {timeString && <span className="bubble-time">{timeString}</span>}
                </div>
                <div className="bubble-text">{segment.text}</div>
              </div>
            )
          })
        )}

        {/* Processing Indicator */}
        {isProcessing && (
          <div className="processing-indicator">
            <Sparkles size={13} className="sparkle-spin" />
            <span>Analyzing speech semantics & psychological tactics...</span>
          </div>
        )}

        <div ref={targetRef} />
      </div>
    </div>
  )
}
