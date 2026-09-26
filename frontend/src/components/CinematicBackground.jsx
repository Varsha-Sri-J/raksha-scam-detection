import React from 'react'

/**
 * CinematicBackground Component — Ultra-Performant Native Compositing
 *
 * Provides the dark liquid-metal & molten silver aesthetic using hardware-accelerated
 * CSS gradients and lightweight static vector elements.
 *
 * Performance Guarantees:
 * - Zero heavy SVG filters (no feTurbulence, feDisplacementMap, or feSpecularLighting)
 * - Zero CPU repaint triggers during browser scroll
 * - Isolated GPU composite layer via transform: translateZ(0) and contain: strict
 * - pointer-events: none, fully decoupled from page layout and scrolling
 */
export default function CinematicBackground({ riskTier = 'SAFE' }) {
  const isCritical = riskTier === 'CRITICAL'
  const isHigh = riskTier === 'HIGH'

  return (
    <div
      className={`cinematic-liquid-metal ${isCritical ? 'is-critical' : isHigh ? 'is-high' : ''}`}
      aria-hidden="true"
    >
      {/* 1. Deep Space Void with Molten Silver Glow Mesh */}
      <div className="liquid-mesh-layer" />

      {/* 2. Soft Ambient Fluid Reflections */}
      <div className="liquid-ambient-reflection reflection-1" />
      <div className="liquid-ambient-reflection reflection-2" />
      <div className="liquid-ambient-reflection reflection-3" />

      {/* 3. Subtle Perimeter Vignette */}
      <div className="liquid-edge-vignette" />

      {/* 4. Critical Threat Edge Atmosphere (Only upon High / Critical Threat) */}
      {(isCritical || isHigh) && <div className="liquid-critical-edge-glow" />}
    </div>
  )
}
