import type { CategoryProfile, CategoryDelta, CategoryDef } from '../../api/types'
import { categoryLabel, fmtCategoryDelta, fmtCategoryValue, fmtInt, fmtNum, fmtSigned, LOWER_IS_BETTER } from '../../lib/format'
import { selectRecCurrent, useDraftStore } from '../../store/draftStore'
import { Badge } from '../common/Badge'

interface ProfileTableProps {
  profile: CategoryProfile
  categories: CategoryDef[]
  deltas?: Record<string, CategoryDelta> | null
  title?: string
}

const Z_EXTENT = 12

/** z-score as a bar around zero: strengths extend right (green), weaknesses left (red). */
export function ZBar({ z, extent = Z_EXTENT }: { z: number; extent?: number }) {
  const w = Math.min(50, (Math.abs(z) / extent) * 50)
  return (
    <span className="zbar-track" aria-hidden="true">
      <span className={`zbar-fill ${z < 0 ? 'neg' : 'pos'}`} style={{ width: `${w}%` }} />
    </span>
  )
}

/** Roster category totals with z as aligned bars; shows before/after when previewing a pick. */
export function ProfileTable({ profile, categories, deltas, title }: ProfileTableProps) {
  const keys = Object.keys(profile.totals)
  const attemptsFor = (k: string) => (k === 'FG_PCT' ? profile.attempts.FGA : k === 'FT_PCT' ? profile.attempts.FTA : null)
  return (
    <div className="table-wrap">
      <table className="grid profile" data-testid="category-profile" aria-label={title ?? 'Category profile'}>
        <thead>
          <tr>
            <th scope="col">Category</th>
            <th scope="col" className="zbar" title="Roster z-score against a full draft-pool roster; above +1 is a strength, below −1 a weakness">
              Strength (z)
            </th>
            <th scope="col" className="num">z</th>
            {deltas ? (
              <>
                <th scope="col" className="num">Before</th>
                <th scope="col" className="num">After</th>
                <th scope="col" className="num">Δ</th>
              </>
            ) : (
              <th scope="col" className="num">Projected</th>
            )}
            <th scope="col" className="num">Attempts</th>
            <th scope="col">Punt</th>
            <th scope="col" className="num">Weight</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => {
            const d = deltas?.[k]
            const punt = profile.punt_labels[k]
            const att = attemptsFor(k)
            const delta = d?.delta ?? null
            const good = delta === null ? null : LOWER_IS_BETTER.has(k) ? delta < 0 : delta > 0
            const z = profile.z[k] ?? 0
            return (
              <tr key={k} data-cat={k}>
                <th scope="row">
                  {categoryLabel(k, categories)}
                  {LOWER_IS_BETTER.has(k) && <span className="muted"> (lower better)</span>}
                </th>
                <td className="zbar">
                  <ZBar z={z} />
                </td>
                <td className={`num ${z > 1 ? 'pos' : z < -1 ? 'neg' : ''}`}>{fmtSigned(z, 1)}</td>
                {d ? (
                  <>
                    <td className="num">{fmtCategoryValue(k, d.before)}</td>
                    <td className="num">{fmtCategoryValue(k, d.after)}</td>
                    <td className={`num ${good === null ? '' : good ? 'pos' : 'neg'}`} title={d.unit}>
                      {fmtCategoryDelta(k, delta)}
                    </td>
                  </>
                ) : deltas ? (
                  <>
                    <td className="num muted">—</td>
                    <td className="num">{fmtCategoryValue(k, profile.totals[k])}</td>
                    <td className="num muted">—</td>
                  </>
                ) : (
                  <td className="num">{fmtCategoryValue(k, profile.totals[k])}</td>
                )}
                <td className="num muted">{att === null ? '' : `${fmtInt(att)} ${k === 'FG_PCT' ? 'FGA' : 'FTA'}`}</td>
                <td>{punt ? <Badge tone="warn">{punt} punt</Badge> : <span className="muted">—</span>}</td>
                <td className="num">{fmtNum(profile.weights[k], 2)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="table-note">Units: {profile.unit}; rates are makes ÷ attempts (shown with attempts). Bars span ±{Z_EXTENT} z.</p>
    </div>
  )
}

export function CategoryProfileTable() {
  const state = useDraftStore((s) => s.state)
  const rec = useDraftStore((s) => s.rec)
  const current = useDraftStore(selectRecCurrent)
  const previewPlayerId = useDraftStore((s) => s.previewPlayerId)
  const previewCandidate = useDraftStore((s) => s.rec?.preview_candidate ?? s.previewCandidate)
  if (!state) return null
  const profile = current && rec ? rec.category_profile : null
  const deltas = previewPlayerId && previewCandidate?.category_deltas ? previewCandidate.category_deltas : null
  return (
    <section aria-labelledby="cats-h">
      <div className="panel-head">
        <h3 id="cats-h">My category profile{deltas ? ` · if I draft ${previewCandidate?.name}` : ''}</h3>
        {!current && <span className="badge">recalculating…</span>}
      </div>
      {profile ? <ProfileTable profile={profile} categories={state.league.categories ?? []} deltas={deltas} /> : <p className="muted">Recalculating…</p>}
      <p className="table-note">Roster totals, not player averages. z above +1 is a strength, below −1 a weakness, relative to a full draft-pool roster.</p>
    </section>
  )
}
