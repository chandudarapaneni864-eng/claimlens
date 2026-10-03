import { compactMoney } from '../format'

export function ColumnChart({ data, valueKey = 'amount', format = compactMoney, secondaryKey, height = 220 }) {
  const W = 640
  const H = height
  const pad = { l: 46, r: 12, t: 16, b: 34 }
  const max = Math.max(1, ...data.map((d) => d[valueKey]))
  const nice = niceMax(max)
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const slot = innerW / Math.max(1, data.length)
  const bw = Math.min(46, slot * 0.55)
  const ticks = [0, 0.25, 0.5, 0.75, 1]
  return (
    <svg className="svg-chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Monthly totals">
      {ticks.map((t) => {
        const y = pad.t + innerH * (1 - t)
        return (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y} y2={y} stroke="#e8ecee" />
            <text x={pad.l - 8} y={y + 4} textAnchor="end">{format(nice * t)}</text>
          </g>
        )
      })}
      {data.map((d, i) => {
        const h = (d[valueKey] / nice) * innerH
        const x = pad.l + slot * i + (slot - bw) / 2
        const y = pad.t + innerH - h
        return (
          <g key={d.label}>
            <rect x={x} y={y} width={bw} height={Math.max(h, d[valueKey] ? 2 : 0)} rx="5" fill="#1d7a6c">
              <title>{`${d.label}: ${format(d[valueKey])}${secondaryKey ? `, ${d[secondaryKey]} claims` : ''}`}</title>
            </rect>
            {secondaryKey && d[secondaryKey] > 0 && (
              <text x={x + bw / 2} y={y - 6} textAnchor="middle" style={{ fill: '#22324d', fontWeight: 600 }}>{d[secondaryKey]}</text>
            )}
            <text x={x + bw / 2} y={H - 12} textAnchor="middle">{d.label.split(' ')[0]}</text>
          </g>
        )
      })}
    </svg>
  )
}

function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(v))
  const n = v / p
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p
}

export function Donut({ items, size = 150, thickness = 22, center }) {
  const total = items.reduce((s, i) => s + i.value, 0) || 1
  const r = (size - thickness) / 2
  const c = 2 * Math.PI * r
  let offset = 0
  return (
    <div className="donut-wrap">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Distribution">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef1f2" strokeWidth={thickness} />
        {items.filter((i) => i.value > 0).map((i) => {
          const len = (i.value / total) * c
          const el = (
            <circle key={i.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={i.color} strokeWidth={thickness}
              strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} transform={`rotate(-90 ${size / 2} ${size / 2})`}>
              <title>{`${i.label}: ${i.value}`}</title>
            </circle>
          )
          offset += len
          return el
        })}
        {center && (
          <>
            <text x="50%" y="48%" textAnchor="middle" style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 700, fill: '#16233a' }}>{center.value}</text>
            <text x="50%" y="62%" textAnchor="middle" style={{ fontSize: 11, fill: '#8a95a3' }}>{center.label}</text>
          </>
        )}
      </svg>
      <div className="donut-legend">
        {items.map((i) => (
          <div key={i.label}><i style={{ width: 10, height: 10, borderRadius: 3, background: i.color, display: 'inline-block' }} /><span>{i.label}</span><span>{i.value}</span></div>
        ))}
      </div>
    </div>
  )
}

export function HBars({ items, format = (v) => v, color = '#1d7a6c' }) {
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <div className="bars-h">
      {items.map((i) => (
        <div className="bar-row" key={i.label}>
          <span>{i.label}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(i.value / max) * 100}%`, background: i.color || color }} /></div>
          <span className="bar-val">{format(i.value)}</span>
        </div>
      ))}
    </div>
  )
}
