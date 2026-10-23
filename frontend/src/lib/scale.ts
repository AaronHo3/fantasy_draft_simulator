// Small scale helpers for the hand-written SVG charts.

export type Tone = 'good' | 'bad' | 'even'

/** Linear map from `domain` to `range`, clamped to the range. */
export function linear(domain: [number, number], range: [number, number]): (v: number) => number {
  const [d0, d1] = domain
  const [r0, r1] = range
  const span = d1 - d0 || 1
  return (v: number) => {
    const t = Math.min(1, Math.max(0, (v - d0) / span))
    return r0 + t * (r1 - r0)
  }
}

/** Round a positive maximum up to a readable step (7.3 → 8, 63 → 70, 0.37 → 0.4, 3.4 → 3.5). */
export function niceMax(v: number): number {
  if (!Number.isFinite(v) || v <= 0) return 1
  const base = 10 ** Math.floor(Math.log10(v))
  const m = v / base
  const step = m < 2 ? base / 10 : m < 5 ? base / 2 : base
  return Number((Math.ceil(v / step - 1e-9) * step).toPrecision(3))
}

/** Largest absolute value in the list (at least 1), for diverging charts. */
export function symmetricMax(values: number[]): number {
  let m = 0
  for (const v of values) if (Number.isFinite(v)) m = Math.max(m, Math.abs(v))
  return m > 0 ? m : 1
}

/** Favoured / unfavoured / toss-up for a win probability; 40–60% stays neutral. */
export function probabilityTone(p: number): Tone {
  if (p >= 0.6) return 'good'
  if (p <= 0.4) return 'bad'
  return 'even'
}

/** Sign tone for a delta where positive is good (flip for lower-is-better categories). */
export function deltaTone(v: number | null | undefined, higherIsBetter = true): Tone {
  if (v === null || v === undefined || v === 0 || !Number.isFinite(v)) return 'even'
  return (v > 0) === higherIsBetter ? 'good' : 'bad'
}
