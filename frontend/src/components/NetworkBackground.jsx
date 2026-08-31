import { useEffect, useRef, useState } from 'react'
import { fetchCaseDetail } from '../api/caseDetail'

// Ambient decoration only -- never a data source of record. Sampled from a
// handful of already-loaded cases purely for visual texture behind the table.
const STR_READY_SAMPLE = 8
const OTHER_SAMPLE = 8
const MAX_NODES = 60
const MIN_VIEWPORT_WIDTH = 900
const STORAGE_KEY = 'networkBgEnabled'

function seededRandom(seed) {
  const x = Math.sin(seed * 999.7) * 43758.5453
  return x - Math.floor(x)
}

async function sampleGraph(cases) {
  const strReady = cases.filter((c) => c.risk_tier === 'str_ready').slice(0, STR_READY_SAMPLE)
  const others = cases.filter((c) => c.risk_tier !== 'str_ready').slice(0, OTHER_SAMPLE)
  const targets = [...strReady, ...others]
  if (targets.length === 0) return { nodes: [], edges: [] }

  const results = await Promise.allSettled(targets.map((c) => fetchCaseDetail(c.case_id)))

  const nodeMap = new Map()
  const edges = []

  for (const result of results) {
    if (result.status !== 'fulfilled' || !result.value) continue
    const detail = result.value
    const isStrReady = detail.risk_tier === 'str_ready'
    for (const node of detail.nodes ?? []) {
      const existing = nodeMap.get(node.id)
      if (!existing) {
        nodeMap.set(node.id, { id: node.id, strReady: isStrReady })
      } else if (isStrReady) {
        existing.strReady = true
      }
    }
    for (const edge of detail.edges ?? []) {
      edges.push({ source: edge.source, target: edge.target })
    }
  }

  let nodes = [...nodeMap.values()]
  if (nodes.length > MAX_NODES) nodes = nodes.slice(0, MAX_NODES)
  const nodeIds = new Set(nodes.map((n) => n.id))
  const filteredEdges = edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))

  return { nodes, edges: filteredEdges }
}

// One-time force-relaxation to get an organic layout, then frozen -- the
// render loop only adds a cheap trig offset per frame, never recomputes this.
function computeLayout(nodes, edges, width, height) {
  const positions = new Map()
  nodes.forEach((n, i) => {
    positions.set(n.id, {
      x: width * (0.08 + seededRandom(i * 2) * 0.84),
      y: height * (0.08 + seededRandom(i * 2 + 1) * 0.84),
    })
  })

  const ids = nodes.map((n) => n.id)
  for (let iter = 0; iter < 120; iter++) {
    for (let i = 0; i < ids.length; i++) {
      const a = positions.get(ids[i])
      for (let j = i + 1; j < ids.length; j++) {
        const b = positions.get(ids[j])
        let dx = a.x - b.x
        let dy = a.y - b.y
        let distSq = dx * dx + dy * dy
        if (distSq < 1) distSq = 1
        const dist = Math.sqrt(distSq)
        const force = 1400 / distSq
        dx /= dist
        dy /= dist
        a.x += dx * force
        a.y += dy * force
        b.x -= dx * force
        b.y -= dy * force
      }
    }
    for (const e of edges) {
      const a = positions.get(e.source)
      const b = positions.get(e.target)
      if (!a || !b) continue
      const dx = b.x - a.x
      const dy = b.y - a.y
      a.x += dx * 0.03
      a.y += dy * 0.03
      b.x -= dx * 0.03
      b.y -= dy * 0.03
    }
  }

  positions.forEach((p) => {
    p.x = Math.min(width - 12, Math.max(12, p.x))
    p.y = Math.min(height - 12, Math.max(12, p.y))
  })

  return positions
}

function readStoredPreference() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === null ? true : stored === 'true'
  } catch {
    return true
  }
}

export default function NetworkBackground({ cases }) {
  const canvasRef = useRef(null)
  const [enabled, setEnabled] = useState(readStoredPreference)
  const [wideEnough, setWideEnough] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= MIN_VIEWPORT_WIDTH,
  )
  const [reducedMotion] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )
  const [graph, setGraph] = useState(null)

  const active = enabled && wideEnough && !reducedMotion

  useEffect(() => {
    function onResize() {
      setWideEnough(window.innerWidth >= MIN_VIEWPORT_WIDTH)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  // Sampling is keyed off `cases` (the full loaded list), not the current
  // page -- pagination never re-triggers this fetch or re-layout.
  useEffect(() => {
    if (!active || cases.length === 0) {
      setGraph(null)
      return
    }
    let cancelled = false
    sampleGraph(cases).then((result) => {
      if (!cancelled) setGraph(result)
    })
    return () => {
      cancelled = true
    }
  }, [active, cases])

  useEffect(() => {
    if (!active || !graph || graph.nodes.length === 0) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    let width = window.innerWidth
    let height = window.innerHeight
    canvas.width = width
    canvas.height = height

    const positions = computeLayout(graph.nodes, graph.edges, width, height)
    const phases = graph.nodes.map((_, i) => seededRandom(i * 7.3) * Math.PI * 2)

    function handleResize() {
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = width
      canvas.height = height
    }
    window.addEventListener('resize', handleResize)

    let hidden = false
    function handleVisibility() {
      hidden = document.hidden
    }
    document.addEventListener('visibilitychange', handleVisibility)

    let frameId
    function draw(t) {
      frameId = requestAnimationFrame(draw)
      if (hidden) return

      ctx.clearRect(0, 0, width, height)

      ctx.strokeStyle = 'rgba(91, 98, 114, 0.5)'
      ctx.lineWidth = 1
      for (const e of graph.edges) {
        const a = positions.get(e.source)
        const b = positions.get(e.target)
        if (!a || !b) continue
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
      }

      graph.nodes.forEach((n, i) => {
        const p = positions.get(n.id)
        if (!p) return
        const x = p.x + Math.sin(t / 4000 + phases[i]) * 3
        const y = p.y + Math.cos(t / 4500 + phases[i]) * 3

        if (n.strReady) {
          const pulse = 0.5 + 0.5 * Math.sin(t / 1000 + phases[i])
          ctx.fillStyle = `rgba(239, 68, 68, ${0.35 + pulse * 0.35})`
          ctx.beginPath()
          ctx.arc(x, y, 3 + pulse * 1.5, 0, Math.PI * 2)
          ctx.fill()
        } else {
          ctx.fillStyle = 'rgba(45, 212, 191, 0.4)'
          ctx.beginPath()
          ctx.arc(x, y, 2.5, 0, Math.PI * 2)
          ctx.fill()
        }
      })
    }
    frameId = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(frameId)
      window.removeEventListener('resize', handleResize)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [active, graph])

  function toggle() {
    setEnabled((prev) => {
      const next = !prev
      try {
        localStorage.setItem(STORAGE_KEY, String(next))
      } catch {
        /* ignore -- purely a nice-to-have preference */
      }
      return next
    })
  }

  return (
    <>
      {active && <canvas ref={canvasRef} className="network-bg-canvas" aria-hidden="true" />}
      {wideEnough && !reducedMotion && (
        <button type="button" className="network-bg-toggle" onClick={toggle}>
          Background: {enabled ? 'On' : 'Off'}
        </button>
      )}
    </>
  )
}
