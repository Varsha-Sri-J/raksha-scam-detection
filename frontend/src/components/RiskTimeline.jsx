import React from 'react'
import { Activity, Clock } from 'lucide-react'

export default function RiskTimeline({ history = [], currentScore = 0 }) {
  // SVG dimensions and padding
  const viewWidth = 500
  const viewHeight = 88
  const padLeft = 24
  const padRight = 10
  const padTop = 8
  const padBottom = 16

  const plotWidth = viewWidth - padLeft - padRight
  const plotHeight = viewHeight - padTop - padBottom

  const getY = (score) => {
    const clamped = Math.max(0, Math.min(100, score))
    return padTop + ((100 - clamped) / 100) * plotHeight
  }

  // Ensure we have at least one visual point representing current state
  const dataPoints = [...history]
  if (dataPoints.length === 0 && currentScore > 0) {
    dataPoints.push({ timestamp: Date.now() / 1000, score: currentScore })
  }

  // Calculate coordinates
  const points = dataPoints.map((pt, idx) => {
    const x =
      dataPoints.length <= 1
        ? padLeft + plotWidth / 2
        : padLeft + (idx / (dataPoints.length - 1)) * plotWidth
    const y = getY(pt.score)
    return { x, y, score: pt.score, timestamp: pt.timestamp }
  })

  // Build SVG Path strings
  let linePath = ''
  let areaPath = ''

  if (points.length === 0) {
    // Baseline flatline at 0
    const baselineY = getY(0)
    linePath = `M ${padLeft} ${baselineY} L ${padLeft + plotWidth} ${baselineY}`
  } else if (points.length === 1) {
    const pt = points[0]
    linePath = `M ${padLeft} ${pt.y} L ${padLeft + plotWidth} ${pt.y}`
    areaPath = `M ${padLeft} ${getY(0)} L ${padLeft} ${pt.y} L ${padLeft + plotWidth} ${pt.y} L ${
      padLeft + plotWidth
    } ${getY(0)} Z`
  } else {
    linePath = points.reduce((acc, pt, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${pt.x} ${pt.y}`, '')
    const firstPt = points[0]
    const lastPt = points[points.length - 1]
    const baselineY = getY(0)
    areaPath = `${linePath} L ${lastPt.x} ${baselineY} L ${firstPt.x} ${baselineY} Z`
  }

  const latestPt = points.length > 0 ? points[points.length - 1] : null

  return (
    <div className="risk-timeline-container">
      <div className="timeline-header">
        <div className="timeline-title-group">
          <Activity size={12} color="var(--accent-cyan)" />
          <span className="timeline-title">Risk Timeline</span>
        </div>
        <span className="timeline-points-counter font-mono">
          {dataPoints.length} {dataPoints.length === 1 ? 'pt' : 'pts'}
        </span>
      </div>

      <div className="timeline-chart-wrapper">
        <svg
          className="timeline-svg"
          viewBox={`0 0 ${viewWidth} ${viewHeight}`}
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id="riskAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ef4444" stopOpacity="0.30" />
              <stop offset="50%" stopColor="#f59e0b" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.04" />
            </linearGradient>
            <linearGradient id="riskLineGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#10b981" />
              <stop offset="55%" stopColor="#f59e0b" />
              <stop offset="100%" stopColor="#ef4444" />
            </linearGradient>
          </defs>

          {/* Background Grid Lines for Risk Tiers */}
          <line
            x1={padLeft}
            y1={getY(25)}
            x2={padLeft + plotWidth}
            y2={getY(25)}
            className="grid-line"
          />
          <line
            x1={padLeft}
            y1={getY(50)}
            x2={padLeft + plotWidth}
            y2={getY(50)}
            className="grid-line"
          />
          <line
            x1={padLeft}
            y1={getY(75)}
            x2={padLeft + plotWidth}
            y2={getY(75)}
            className="grid-line"
          />

          {/* Y-Axis Tier Labels */}
          <text x={padLeft - 4} y={getY(75) + 3} className="axis-text axis-crit">
            75
          </text>
          <text x={padLeft - 4} y={getY(50) + 3} className="axis-text axis-med">
            50
          </text>
          <text x={padLeft - 4} y={getY(25) + 3} className="axis-text axis-low">
            25
          </text>
          <text x={padLeft - 4} y={getY(0) + 3} className="axis-text axis-safe">
            0
          </text>

          {/* Shaded Area Fill */}
          {areaPath && <path d={areaPath} fill="url(#riskAreaGrad)" />}

          {/* Progression Line */}
          <path
            d={linePath}
            fill="none"
            stroke="url(#riskLineGrad)"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Individual Data Points */}
          {points.map((pt, i) => (
            <circle
              key={i}
              cx={pt.x}
              cy={pt.y}
              r={i === points.length - 1 ? 4 : 2.5}
              className={`timeline-dot ${i === points.length - 1 ? 'latest' : ''}`}
            />
          ))}

          {/* Latest Point Pulse Ring */}
          {latestPt && (
            <circle
              cx={latestPt.x}
              cy={latestPt.y}
              r={7}
              className="pulse-ring"
            />
          )}
        </svg>

        {points.length === 0 && (
          <div className="timeline-empty-hint">
            <span>Awaiting risk calculation updates...</span>
          </div>
        )}
      </div>

      <div className="timeline-footer">
        <span className="timeline-axis-label">
          <Clock size={10} style={{ marginRight: 3 }} />
          Utterance Progression
        </span>
        <span className="timeline-current-score font-mono">
          Current: <strong>{currentScore.toFixed(0)}</strong> / 100
        </span>
      </div>
    </div>
  )
}
