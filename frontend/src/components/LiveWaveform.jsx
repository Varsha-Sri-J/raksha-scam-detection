import React, { useEffect, useState } from 'react'
import { Volume2, VolumeX, Mic } from 'lucide-react'

export default function LiveWaveform({ lastActivityTimestamp, isSimulating = false }) {
  const [isActive, setIsActive] = useState(false)

  // Track speech activity window (animates if activity occurred within past 2500ms or simulation running)
  useEffect(() => {
    if (isSimulating) {
      setIsActive(true)
      return
    }

    if (!lastActivityTimestamp) {
      setIsActive(false)
      return
    }

    const elapsed = Date.now() - lastActivityTimestamp
    if (elapsed < 2500) {
      setIsActive(true)
      const timer = setTimeout(() => {
        setIsActive(false)
      }, 2500 - elapsed)
      return () => clearTimeout(timer)
    } else {
      setIsActive(false)
    }
  }, [lastActivityTimestamp, isSimulating])

  // 18 visualizer bars with pseudo-random oscillating heights during activity
  const barCount = 18

  return (
    <div className={`waveform-container ${isActive ? 'active' : 'idle'}`}>
      <div className="waveform-header">
        <div className="waveform-title-group">
          {isActive ? (
            <Volume2 size={14} className="waveform-icon active-icon" />
          ) : (
            <VolumeX size={14} className="waveform-icon idle-icon" />
          )}
          <span className="waveform-title">Inbound Audio Activity</span>
        </div>

        <div className={`activity-status-pill ${isActive ? 'speech-active' : 'speech-idle'}`}>
          <span className="activity-dot" />
          <span>{isActive ? 'SPEECH DETECTED' : 'CHANNEL IDLE / LISTENING'}</span>
        </div>
      </div>

      <div className="waveform-visualizer" aria-label="Visual speech activity indicator">
        {Array.from({ length: barCount }).map((_, i) => {
          // Staggered delays and heights
          const animDelay = (i * 0.08).toFixed(2)
          return (
            <div
              key={i}
              className={`waveform-bar ${isActive ? 'animating' : 'resting'}`}
              style={{
                animationDelay: `${animDelay}s`,
              }}
            />
          )
        })}
      </div>

      <div className="waveform-footer">
        <span className="waveform-caption">
          Visual indicator synchronized with streaming transcript events
        </span>
      </div>
    </div>
  )
}
