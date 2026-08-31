import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const currencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

export default function CaseGraph({ nodes, edges }) {
  const containerRef = useRef(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(entry.contentRect.width)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const graphData = useMemo(
    () => ({
      nodes: nodes.map((n) => ({ id: n.id, label: n.label })),
      links: edges.map((e) => ({
        source: e.source,
        target: e.target,
        amount: e.amount,
        timestamp: e.timestamp,
      })),
    }),
    [nodes, edges],
  )

  return (
    <div className="case-graph" ref={containerRef}>
      {width > 0 && (
        <ForceGraph2D
          width={width}
          height={380}
          graphData={graphData}
          nodeRelSize={5}
          linkDirectionalArrowLength={7}
          linkDirectionalArrowRelPos={1}
          linkDirectionalArrowColor={() => '#2DD4BF'}
          linkCurvature={0.25}
          linkColor={() => 'rgba(91, 98, 114, 0.6)'}
          linkLabel={(link) => `${link.source.id ?? link.source} → ${link.target.id ?? link.target}: ${currencyFormatter.format(link.amount)}`}
          nodeLabel={(node) => node.label}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const radius = 6
            ctx.beginPath()
            ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false)
            ctx.fillStyle = '#2DD4BF'
            ctx.fill()

            const fontSize = 11 / globalScale
            ctx.font = `${fontSize}px 'JetBrains Mono', ui-monospace, monospace`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            ctx.fillStyle = '#8B92A5'
            ctx.fillText(node.label, node.x, node.y + radius + 2)
          }}
          cooldownTicks={80}
        />
      )}
    </div>
  )
}
