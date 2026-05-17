/**
 * ForceGraph — Neo4j-style force-directed graph for user→resource access maps.
 *
 * Architecture:
 *  - Physics simulation runs in a requestAnimationFrame loop
 *  - SVG nodes/edges are created imperatively (no React re-renders per frame)
 *  - Only the tooltip uses React state (low-frequency updates)
 *  - Supports: node drag, viewport pan (background drag), scroll zoom, hover tooltips
 */
import { useEffect, useRef, useState } from 'react'
import type { IdentityGraphNode, IdentityGraphEdge, IdentityUser } from '../../api/types'

// ── Visual constants ──────────────────────────────────────────────────────────

const USER_R = 26
const RES_R = 22
const USER_COLOR   = '#6366f1'
const ADMIN_COLOR  = '#ef4444'
const RES_COLOR    = '#0ea5e9'
const GROUP_COLOR  = '#10b981'
const EDGE_COLOR   = 'rgba(99,102,241,0.28)'
const ADMIN_EDGE   = 'rgba(239,68,68,0.45)'

// ── Physics constants ─────────────────────────────────────────────────────────

const K_REPULSE    = 5500   // node-node repulsion
const K_SPRING     = 0.032  // edge spring strength
const SPRING_REST  = 210    // natural edge length (px)
const K_CENTER     = 0.008  // pull toward canvas centre
const DAMPING      = 0.80
const ALPHA_DECAY  = 0.9935
const MIN_ALPHA    = 0.004

// ── Types ─────────────────────────────────────────────────────────────────────

interface SimNode extends IdentityGraphNode {
  x: number; y: number
  vx: number; vy: number
  fx: number | null; fy: number | null
  r: number
  edgeCount: number
}

interface TooltipData {
  node: SimNode
  user?: IdentityUser
  /** for resource nodes: unique roles granted to this resource */
  roles: string[]
  /** for resource nodes: how many users can access it */
  connectedUsers: number
  /** cursor position in container coords */
  cx: number; cy: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function isAdminRole(role: string) {
  return /admin|owner|maintain|billing/i.test(role)
}

function initials(label: string): string {
  const parts = label.split(/[\s@._\-/]+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return label.slice(0, 2).toUpperCase()
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

// ── Simulation tick ───────────────────────────────────────────────────────────

function tick(
  nodes: SimNode[],
  edgeMap: Map<string, string[]>,
  nodeMap: Map<string, SimNode>,
  W: number, H: number, alpha: number,
) {
  // Repulsion (all pairs)
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i]
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j]
      const dx = b.x - a.x || 0.01
      const dy = b.y - a.y || 0.01
      const dist2 = dx * dx + dy * dy + 1
      const dist  = Math.sqrt(dist2)
      const f  = (K_REPULSE * alpha) / dist2
      const fx = (f * dx) / dist
      const fy = (f * dy) / dist
      if (a.fx === null) { a.vx -= fx; a.vy -= fy }
      if (b.fx === null) { b.vx += fx; b.vy += fy }
    }
  }

  // Spring attraction (edges)
  for (const [srcId, targets] of edgeMap) {
    const src = nodeMap.get(srcId)
    if (!src) continue
    for (const tgtId of targets) {
      const tgt = nodeMap.get(tgtId)
      if (!tgt) continue
      const dx   = tgt.x - src.x
      const dy   = tgt.y - src.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const f    = K_SPRING * (dist - SPRING_REST) * alpha
      const fx   = (f * dx) / dist
      const fy   = (f * dy) / dist
      if (src.fx === null) { src.vx += fx; src.vy += fy }
      if (tgt.fx === null) { tgt.vx -= fx; tgt.vy -= fy }
    }
  }

  // Centering force
  const cx = W / 2, cy = H / 2
  for (const n of nodes) {
    if (n.fx !== null) continue
    n.vx += (cx - n.x) * K_CENTER * alpha
    n.vy += (cy - n.y) * K_CENTER * alpha
  }

  // Integrate positions
  const pad = 50
  for (const n of nodes) {
    if (n.fx !== null) {
      n.x = n.fx; n.y = n.fy!
    } else {
      n.vx *= DAMPING; n.vy *= DAMPING
      n.x = Math.max(pad, Math.min(W - pad, n.x + n.vx))
      n.y = Math.max(pad, Math.min(H - pad, n.y + n.vy))
    }
  }
}

// ── Tooltip (React) ───────────────────────────────────────────────────────────

function NodeTooltip({ data, containerW, containerH, platform }: {
  data: TooltipData
  containerW: number
  containerH: number
  platform?: string
}) {
  const TW = 248
  let left = data.cx + 18
  let top  = data.cy - 12
  if (left + TW > containerW - 8) left = data.cx - TW - 18
  if (top + 220 > containerH)     top  = containerH - 230
  if (top < 4) top = 4

  const { node: n, user: u } = data
  const isUser  = n.type === 'user'
  const isGroup = n.type === 'group'
  const mainColor = isUser ? (n.is_admin ? ADMIN_COLOR : USER_COLOR) : isGroup ? GROUP_COLOR : RES_COLOR

  return (
    <div style={{
      position: 'absolute', left, top, width: TW, zIndex: 60,
      background: 'var(--surface)',
      border: `1px solid ${mainColor}44`,
      borderRadius: 12,
      boxShadow: `0 4px 6px rgba(0,0,0,0.1), 0 12px 28px rgba(0,0,0,0.22), 0 0 0 1px ${mainColor}22`,
      padding: '14px 16px',
      pointerEvents: 'none',
      backdropFilter: 'blur(8px)',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <div style={{
          width: 40, height: 40, borderRadius: isUser ? '50%' : 10, flexShrink: 0,
          background: `${mainColor}1a`,
          border: `2px solid ${mainColor}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '0.75rem', fontWeight: 800, color: mainColor,
          letterSpacing: '0.02em',
        }}>
          {initials(n.label)}
        </div>
        <div style={{ minWidth: 0 }}>
          <p style={{
            fontWeight: 700, fontSize: '0.875rem', color: 'var(--text)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            lineHeight: 1.3,
          }}>
            {n.label}
          </p>
          {isUser && n.email && (
            <p style={{
              fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 2,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {n.email}
            </p>
          )}
          {!isUser && n.label !== n.platform_id && (
            <p style={{
              fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 2,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {n.platform_id}
            </p>
          )}
        </div>
      </div>

      {/* Badges row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 10 }}>
        {isUser && n.is_admin && <Badge label="Admin" bg={`${ADMIN_COLOR}20`} color={ADMIN_COLOR} />}
        {isUser && u?.is_active === false && <Badge label="Inactive" />}
        {isUser && u?.is_external && <Badge label="External" bg="rgba(245,158,11,0.15)" color="#f59e0b" />}
        {isGroup && <Badge label="Group" bg={`${GROUP_COLOR}18`} color={GROUP_COLOR} />}
        {!isUser && !isGroup && (
          platform === 'jira'
            ? <Badge label="Project" bg={`${RES_COLOR}18`} color={RES_COLOR} />
            : <Badge label="Resource" bg={`${RES_COLOR}18`} color={RES_COLOR} />
        )}
      </div>

      {/* Stats */}
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 6,
        borderTop: '1px solid var(--border)', paddingTop: 10,
      }}>
        {isUser ? (
          <>
            <StatRow
              label="Open findings"
              value={u?.finding_count ?? 0}
              valueColor={(u?.finding_count ?? 0) > 0 ? 'var(--sev-high)' : undefined}
            />
            <StatRow label="Resources accessed" value={u?.resource_count ?? n.edgeCount} />
            {u?.is_admin !== undefined && (
              <StatRow label="Account type" value={n.is_admin ? 'Privileged' : 'Standard'} valueColor={n.is_admin ? ADMIN_COLOR : undefined} />
            )}
          </>
        ) : (
          <>
            <StatRow label="Users with access" value={data.connectedUsers} />
            {data.roles.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', flexShrink: 0, paddingTop: 2 }}>Roles</span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, justifyContent: 'flex-end', flex: 1 }}>
                  {data.roles.slice(0, 5).map((r) => (
                    <span key={r} style={{
                      padding: '1px 7px', borderRadius: 20, fontSize: '0.625rem', fontWeight: 600,
                      background: isAdminRole(r) ? `${ADMIN_COLOR}18` : `${USER_COLOR}15`,
                      color: isAdminRole(r) ? ADMIN_COLOR : USER_COLOR,
                    }}>
                      {r}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Badge({ label, bg = 'var(--surface-2)', color = 'var(--text-muted)' }: {
  label: string; bg?: string; color?: string
}) {
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 20, fontSize: '0.625rem', fontWeight: 700,
      background: bg, color,
    }}>
      {label}
    </span>
  )
}

function StatRow({ label, value, valueColor }: {
  label: string; value: number | string; valueColor?: string
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>{label}</span>
      <span style={{
        fontSize: '0.8125rem', fontWeight: 700,
        fontVariantNumeric: 'tabular-nums',
        color: valueColor ?? 'var(--text)',
      }}>
        {value}
      </span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  nodes: IdentityGraphNode[]
  edges: IdentityGraphEdge[]
  users: IdentityUser[]
  platform?: string
}

const NS = 'http://www.w3.org/2000/svg'
const HEIGHT = 540

export default function ForceGraph({ nodes, edges, users, platform }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef       = useRef<SVGSVGElement>(null)
  const vpRef        = useRef<SVGGElement>(null)       // zoom/pan viewport group
  const edgeLayerRef = useRef<SVGGElement>(null)
  const nodeLayerRef = useRef<SVGGElement>(null)

  const [tooltip, setTooltip] = useState<TooltipData | null>(null)
  const [dims, setDims]       = useState({ w: 800, h: HEIGHT })

  // Mutable simulation state stored in a ref (never causes re-renders)
  const simRef = useRef({
    nodes:    [] as SimNode[],
    nodeMap:  new Map<string, SimNode>(),
    edgeMap:  new Map<string, string[]>(),
    // per-resource maps for tooltip data
    resRoles: new Map<string, string[]>(),     // resource id → unique roles
    resUsers: new Map<string, Set<string>>(),  // resource id → user ids
    alpha:    1,
    nodeElems: new Map<string, SVGGElement>(),
    edgeElems: new Map<string, SVGPathElement>(),
    dragging:  null as string | null,
    xf: { tx: 0, ty: 0, k: 1 },  // viewport transform
    panning:   false,
    panStart:  { mx: 0, my: 0, tx: 0, ty: 0 },
  })

  // User lookup by platform_id
  const userMapRef = useRef(new Map<string, IdentityUser>())
  useEffect(() => {
    userMapRef.current = new Map(users.map((u) => [u.platform_id, u]))
  }, [users])

  // Track container size
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      setDims({ w: el.clientWidth || 800, h: HEIGHT })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // ── Main simulation effect ────────────────────────────────────────────────
  useEffect(() => {
    const svg       = svgRef.current
    const vp        = vpRef.current
    const edgeLyr   = edgeLayerRef.current
    const nodeLyr   = nodeLayerRef.current
    const container = containerRef.current
    if (!svg || !vp || !edgeLyr || !nodeLyr || !container) return

    const sim = simRef.current
    const W   = container.clientWidth  || 800
    const H   = HEIGHT

    // ── Reset ──────────────────────────────────────────────────────────────
    while (edgeLyr.firstChild) edgeLyr.removeChild(edgeLyr.firstChild)
    while (nodeLyr.firstChild) nodeLyr.removeChild(nodeLyr.firstChild)
    sim.nodeElems.clear(); sim.edgeElems.clear()
    sim.xf = { tx: 0, ty: 0, k: 1 }
    vp.setAttribute('transform', 'translate(0,0) scale(1)')

    if (nodes.length === 0) return

    // ── Build edge / role / user maps ─────────────────────────────────────
    const edgeMap  = new Map<string, string[]>()
    const resRoles = new Map<string, string[]>()
    const resUsers = new Map<string, Set<string>>()
    const edgeCnt  = new Map<string, number>()

    for (const e of edges) {
      if (!edgeMap.has(e.source)) edgeMap.set(e.source, [])
      edgeMap.get(e.source)!.push(e.target)

      if (!resRoles.has(e.target)) resRoles.set(e.target, [])
      const rl = resRoles.get(e.target)!
      if (e.role && !rl.includes(e.role)) rl.push(e.role)

      if (!resUsers.has(e.target)) resUsers.set(e.target, new Set())
      resUsers.get(e.target)!.add(e.source)

      edgeCnt.set(e.source, (edgeCnt.get(e.source) ?? 0) + 1)
      edgeCnt.set(e.target, (edgeCnt.get(e.target) ?? 0) + 1)
    }

    sim.edgeMap  = edgeMap
    sim.resRoles = resRoles
    sim.resUsers = resUsers

    // ── Initialise SimNodes ───────────────────────────────────────────────
    const userNodes = nodes.filter((n) => n.type === 'user')
    const resNodes  = nodes.filter((n) => n.type !== 'user')

    sim.nodes = nodes.map((n) => {
      const isU  = n.type === 'user'
      const arr  = isU ? userNodes : resNodes
      const idx  = arr.indexOf(n)
      const tot  = arr.length
      const span = Math.min(H * 0.75, tot * 64)
      const yOff = tot > 1 ? (span / (tot - 1)) * idx - span / 2 : 0

      return {
        ...n,
        x: (isU ? W * 0.28 : W * 0.72) + (Math.random() - 0.5) * 60,
        y: H / 2 + yOff + (Math.random() - 0.5) * 24,
        vx: 0, vy: 0,
        fx: null, fy: null,
        r: isU ? USER_R : RES_R,
        edgeCount: edgeCnt.get(n.id) ?? 0,
      }
    })
    sim.nodeMap = new Map(sim.nodes.map((n) => [n.id, n]))
    sim.alpha   = 1

    // ── Create SVG edge elements ──────────────────────────────────────────
    for (const e of edges) {
      const isAdmin = isAdminRole(e.role)
      const path = document.createElementNS(NS, 'path')
      path.setAttribute('fill', 'none')
      path.setAttribute('stroke', isAdmin ? ADMIN_EDGE : EDGE_COLOR)
      path.setAttribute('stroke-width', isAdmin ? '2' : '1.5')
      edgeLyr.appendChild(path)
      sim.edgeElems.set(`${e.source}--${e.target}`, path)
    }

    // ── Create SVG node elements ──────────────────────────────────────────
    for (const n of sim.nodes) {
      const isU  = n.type === 'user'
      const isGr = n.type === 'group'
      const col  = isU ? (n.is_admin ? ADMIN_COLOR : USER_COLOR) : isGr ? GROUP_COLOR : RES_COLOR

      const g = document.createElementNS(NS, 'g')
      g.style.cursor = 'grab'

      // Glow ring (shown on hover)
      const glow = document.createElementNS(NS, 'circle')
      glow.setAttribute('r', String(n.r + 10))
      glow.style.fill = `${col}18`
      glow.setAttribute('opacity', '0')
      glow.style.transition = 'opacity 0.15s'

      // Shadow circle for depth
      const shadow = document.createElementNS(NS, 'circle')
      shadow.setAttribute('r', String(n.r + 1))
      shadow.style.fill = 'rgba(0,0,0,0.25)'
      shadow.setAttribute('transform', 'translate(0,2)')

      // Main circle
      const circle = document.createElementNS(NS, 'circle')
      circle.setAttribute('r', String(n.r))
      circle.style.fill   = `${col}1e`
      circle.style.stroke = col
      circle.setAttribute('stroke-width', '2.5')

      // Admin star / resource square indicator
      if (n.is_admin && isU) {
        const star = document.createElementNS(NS, 'circle')
        star.setAttribute('r', '5')
        star.setAttribute('cx', String(n.r - 4))
        star.setAttribute('cy', String(-n.r + 4))
        star.style.fill   = ADMIN_COLOR
        star.style.stroke = 'var(--surface-1, #0f1117)'
        star.setAttribute('stroke-width', '1.5')
        g.appendChild(star)
      }

      // Initials text
      const initTxt = document.createElementNS(NS, 'text')
      initTxt.setAttribute('text-anchor', 'middle')
      initTxt.setAttribute('dominant-baseline', 'central')
      initTxt.style.fill         = col
      initTxt.style.fontSize     = isU ? '11px' : '10px'
      initTxt.style.fontWeight   = '800'
      initTxt.style.fontFamily   = 'system-ui, sans-serif'
      initTxt.style.pointerEvents = 'none'
      initTxt.textContent = initials(n.label)

      // Label below node
      const lbl = document.createElementNS(NS, 'text')
      lbl.setAttribute('y', String(n.r + 15))
      lbl.setAttribute('text-anchor', 'middle')
      lbl.style.fill         = 'var(--text, #e2e8f0)'
      lbl.style.fontSize     = '10px'
      lbl.style.fontFamily   = 'system-ui, sans-serif'
      lbl.style.pointerEvents = 'none'
      lbl.textContent = truncate(n.label, 18)

      g.appendChild(glow)
      g.appendChild(shadow)
      g.appendChild(circle)
      g.appendChild(initTxt)
      g.appendChild(lbl)
      nodeLyr.appendChild(g)
      sim.nodeElems.set(n.id, g)

      // ── Hover events ────────────────────────────────────────────────────
      g.addEventListener('mouseenter', (evt) => {
        const me = evt as MouseEvent
        glow.setAttribute('opacity', '1')
        circle.setAttribute('stroke-width', '3.5')

        const cRect = container.getBoundingClientRect()
        const u = isU ? userMapRef.current.get(n.platform_id) : undefined
        setTooltip({
          node: n, user: u,
          roles:          resRoles.get(n.id) ?? [],
          connectedUsers: resUsers.get(n.id)?.size ?? 0,
          cx: me.clientX - cRect.left,
          cy: me.clientY - cRect.top,
        })
      })

      g.addEventListener('mousemove', (evt) => {
        const me = evt as MouseEvent
        const cRect = container.getBoundingClientRect()
        setTooltip((prev) =>
          prev ? { ...prev, cx: me.clientX - cRect.left, cy: me.clientY - cRect.top } : prev
        )
      })

      g.addEventListener('mouseleave', () => {
        if (sim.dragging !== n.id) {
          glow.setAttribute('opacity', '0')
          circle.setAttribute('stroke-width', '2.5')
          setTooltip(null)
        }
      })

      // ── Drag events ─────────────────────────────────────────────────────
      g.addEventListener('mousedown', (evt) => {
        evt.stopPropagation()
        sim.dragging = n.id
        g.style.cursor = 'grabbing'

        const onMove = (mme: MouseEvent) => {
          const cRect = container.getBoundingClientRect()
          const { tx, ty, k } = sim.xf
          n.fx = (mme.clientX - cRect.left - tx) / k
          n.fy = (mme.clientY - cRect.top  - ty) / k
          n.x  = n.fx; n.y = n.fy
          setTooltip((prev) =>
            prev ? {
              ...prev,
              cx: mme.clientX - cRect.left,
              cy: mme.clientY - cRect.top,
            } : prev
          )
        }

        const onUp = () => {
          sim.dragging = null
          n.fx = null; n.fy = null
          g.style.cursor = 'grab'
          glow.setAttribute('opacity', '0')
          circle.setAttribute('stroke-width', '2.5')
          setTooltip(null)
          window.removeEventListener('mousemove', onMove)
          window.removeEventListener('mouseup', onUp)
        }

        window.addEventListener('mousemove', onMove)
        window.addEventListener('mouseup', onUp)
      })
    }

    // ── Zoom ───────────────────────────────────────────────────────────────
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const cRect  = container.getBoundingClientRect()
      const mx     = e.clientX - cRect.left
      const my     = e.clientY - cRect.top
      const { tx, ty, k } = sim.xf
      const factor = e.deltaY < 0 ? 1.13 : 0.88
      const newK   = Math.max(0.15, Math.min(5, k * factor))
      sim.xf.k  = newK
      sim.xf.tx = mx - (mx - tx) * (newK / k)
      sim.xf.ty = my - (my - ty) * (newK / k)
    }

    // ── Pan ────────────────────────────────────────────────────────────────
    const onSvgDown = (e: MouseEvent) => {
      if (sim.dragging) return
      sim.panning = true
      sim.panStart = { mx: e.clientX, my: e.clientY, tx: sim.xf.tx, ty: sim.xf.ty }
      svg.style.cursor = 'grabbing'
    }
    const onWinMove = (e: MouseEvent) => {
      if (!sim.panning || sim.dragging) return
      sim.xf.tx = sim.panStart.tx + (e.clientX - sim.panStart.mx)
      sim.xf.ty = sim.panStart.ty + (e.clientY - sim.panStart.my)
    }
    const onWinUp = () => {
      sim.panning = false
      svg.style.cursor = 'default'
    }

    svg.addEventListener('wheel',     onWheel,   { passive: false })
    svg.addEventListener('mousedown', onSvgDown)
    window.addEventListener('mousemove', onWinMove)
    window.addEventListener('mouseup',   onWinUp)

    // ── Animation loop ─────────────────────────────────────────────────────
    let rafId: number

    const frame = () => {
      // Physics
      if (sim.alpha > MIN_ALPHA) {
        tick(sim.nodes, sim.edgeMap, sim.nodeMap, W, H, sim.alpha)
        sim.alpha *= ALPHA_DECAY
      }

      // Update edge paths
      for (const e of edges) {
        const path = sim.edgeElems.get(`${e.source}--${e.target}`)
        if (!path) continue
        const src = sim.nodeMap.get(e.source)
        const tgt = sim.nodeMap.get(e.target)
        if (!src || !tgt) continue

        // Quadratic bezier with slight perpendicular offset for clarity
        const dx  = tgt.x - src.x
        const dy  = tgt.y - src.y
        const len = Math.sqrt(dx * dx + dy * dy) || 1
        const off = len > 100 ? 28 : 12   // curve tightens for short edges
        const cpx = (src.x + tgt.x) / 2 - (dy / len) * off
        const cpy = (src.y + tgt.y) / 2 + (dx / len) * off

        // Trim endpoints to node radius so line starts/ends at circle border
        const a1  = Math.atan2(cpy - src.y, cpx - src.x)
        const a2  = Math.atan2(tgt.y - cpy, tgt.x - cpx)
        const sx  = src.x + Math.cos(a1) * src.r
        const sy  = src.y + Math.sin(a1) * src.r
        const ex  = tgt.x - Math.cos(a2) * tgt.r
        const ey  = tgt.y - Math.sin(a2) * tgt.r

        path.setAttribute('d', `M${sx.toFixed(1)},${sy.toFixed(1)} Q${cpx.toFixed(1)},${cpy.toFixed(1)} ${ex.toFixed(1)},${ey.toFixed(1)}`)
      }

      // Update node positions
      for (const n of sim.nodes) {
        const g = sim.nodeElems.get(n.id)
        if (g) g.setAttribute('transform', `translate(${n.x.toFixed(1)},${n.y.toFixed(1)})`)
      }

      // Update viewport transform
      const { tx, ty, k } = sim.xf
      vp.setAttribute('transform', `translate(${tx.toFixed(2)},${ty.toFixed(2)}) scale(${k.toFixed(4)})`)

      rafId = requestAnimationFrame(frame)
    }

    rafId = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(rafId)
      svg.removeEventListener('wheel',     onWheel)
      svg.removeEventListener('mousedown', onSvgDown)
      window.removeEventListener('mousemove', onWinMove)
      window.removeEventListener('mouseup',   onWinUp)
    }
  }, [nodes, edges])  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Reset view button ─────────────────────────────────────────────────────
  const resetView = () => {
    simRef.current.xf = { tx: 0, ty: 0, k: 1 }
  }

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', width: '100%', height: HEIGHT, userSelect: 'none' }}
    >
      {/* SVG canvas */}
      <svg
        ref={svgRef}
        width="100%"
        height={HEIGHT}
        style={{
          display: 'block',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 12,
        }}
      >
        <g ref={vpRef}>
          <g ref={edgeLayerRef} />
          <g ref={nodeLayerRef} />
        </g>
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <NodeTooltip data={tooltip} containerW={dims.w} containerH={dims.h} platform={platform} />
      )}

      {/* Legend */}
      <div style={{
        position: 'absolute', top: 10, left: 14,
        display: 'flex', gap: 14,
        fontSize: '0.6875rem', color: 'var(--text-muted)',
        pointerEvents: 'none',
      }}>
        <LegendNode color={USER_COLOR}  label="User"         circle />
        <LegendNode color={ADMIN_COLOR} label="Admin"        circle />
        <LegendNode color={GROUP_COLOR} label="Group"        circle />
        <LegendNode color={RES_COLOR}   label="Resource"     circle />
        <LegendEdge color={EDGE_COLOR}  label="Access"       />
        <LegendEdge color={ADMIN_EDGE}  label="Admin access" />
      </div>

      {/* Controls */}
      <div style={{
        position: 'absolute', top: 10, right: 14,
        display: 'flex', gap: 6,
      }}>
        <ControlBtn onClick={resetView} title="Reset view">⊙</ControlBtn>
        <ControlBtn
          onClick={() => { simRef.current.alpha = 1 }}
          title="Restart physics"
        >
          ↺
        </ControlBtn>
      </div>

      {/* Hint */}
      <p style={{
        position: 'absolute', bottom: 10, right: 14,
        fontSize: '0.625rem', color: 'var(--text-muted)',
        pointerEvents: 'none',
      }}>
        Scroll to zoom · Drag background to pan · Drag nodes to pin
      </p>
    </div>
  )
}

// ── Small sub-components ──────────────────────────────────────────────────────

function LegendNode({ color, label, circle }: { color: string; label: string; circle: boolean }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <svg width={14} height={14}>
        {circle
          ? <circle cx={7} cy={7} r={5} fill={`${color}1e`} stroke={color} strokeWidth={1.5} />
          : <rect x={2} y={2} width={10} height={10} rx={3} fill={`${color}1e`} stroke={color} strokeWidth={1.5} />
        }
      </svg>
      {label}
    </span>
  )
}

function LegendEdge({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <svg width={20} height={10}>
        <path d="M0,5 Q10,1 20,5" fill="none" stroke={color} strokeWidth={1.5} />
      </svg>
      {label}
    </span>
  )
}

function ControlBtn({ onClick, title, children }: {
  onClick: () => void; title: string; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        width: 28, height: 28,
        borderRadius: 6,
        border: '1px solid var(--border)',
        background: 'var(--surface)',
        color: 'var(--text-muted)',
        fontSize: '0.875rem',
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        lineHeight: 1,
      }}
    >
      {children}
    </button>
  )
}
