import { fmtCategoryDelta, fmtNum, fmtSigned, PER_GAME_KEYS, positionsText } from '../../lib/format'
import { idsMatch } from '../../lib/revision'
import { useDraftStore } from '../../store/draftStore'
import { Modal } from '../common/Modal'
import { TeamMark } from '../ui/PlayerIdentity'
import { ZBar } from './CategoryProfileTable'

/** Side-by-side comparison: score, per-game line, and each category's z as an aligned bar on one scale. */
export function CompareView() {
  const open = useDraftStore((s) => s.compareOpen)
  const result = useDraftStore((s) => s.compareResult)
  const status = useDraftStore((s) => s.compareStatus)
  const error = useDraftStore((s) => s.compareError)
  const state = useDraftStore((s) => s.state)
  const close = useDraftStore((s) => s.closeCompare)
  const rerun = useDraftStore((s) => s.runCompare)
  if (!open) return null
  const stale = result && state ? !idsMatch(result.ids, state) : false
  const players = result?.players ?? []
  const zExtent = Math.max(2, ...players.flatMap((p) => Object.values(p.z).map((v) => Math.abs(v))))
  return (
    <Modal title="Compare players" onClose={close} wide>
      {status === 'loading' && <p className="muted">Comparing…</p>}
      {status === 'error' && (
        <p className="callout error" role="alert">
          Compare failed: {error}
        </p>
      )}
      {stale && (
        <p className="callout warn">
          The draft moved since this comparison was computed.{' '}
          <button type="button" className="small" onClick={() => void rerun()}>
            Recompute
          </button>
        </p>
      )}
      {result && players.length > 0 && (
        <div className="table-wrap">
          <table className="grid compare-grid" aria-label="Side by side comparison">
            <thead>
              <tr>
                <th scope="col">Metric</th>
                {players.map((p) => (
                  <th key={p.player_id} scope="col" className="who">
                    {p.name}
                    <br />
                    <span className="muted">
                      <TeamMark team={p.team} /> · {positionsText(p.eligible_positions)}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">Score (tier)</th>
                {players.map((p) => (
                  <td key={p.player_id}>
                    <b>{fmtNum(p.score, 2)}</b> (T{p.tier})
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">Base value / replacement</th>
                {players.map((p) => (
                  <td key={p.player_id}>
                    {fmtNum(p.base_value, 2)} / {p.replacement_name ?? '—'}
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">Slot · availability</th>
                {players.map((p) => (
                  <td key={p.player_id}>
                    {p.slot ?? '—'} · {p.survival_hint}
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">Flags</th>
                {players.map((p) => (
                  <td key={p.player_id}>{p.flags.join(', ') || '—'}</td>
                ))}
              </tr>
              <tr>
                <th colSpan={players.length + 1} scope="colgroup" className="group">
                  Per game (projected)
                </th>
              </tr>
              {PER_GAME_KEYS.map((k) => (
                <tr key={k}>
                  <th scope="row">{k}</th>
                  {players.map((p) => (
                    <td key={p.player_id}>{fmtNum(p.per_game[k], k === 'GP' ? 0 : 1)}</td>
                  ))}
                </tr>
              ))}
              <tr>
                <th colSpan={players.length + 1} scope="colgroup" className="group">
                  z (league-standardised season value, bars on ±{zExtent.toFixed(0)}) · Δ to my roster totals if drafted
                </th>
              </tr>
              {result.keys.map((k) => (
                <tr key={k}>
                  <th scope="row">{k}</th>
                  {players.map((p) => {
                    const d = p.category_deltas?.[k]
                    return (
                      <td key={p.player_id}>
                        <span className="mini">
                          <ZBar z={p.z[k] ?? 0} extent={zExtent} />
                          <span className={(p.z[k] ?? 0) > 0.5 ? 'pos' : (p.z[k] ?? 0) < -0.5 ? 'neg' : ''}>{fmtSigned(p.z[k], 2)}</span>
                          {d ? <span className="muted">Δ {fmtCategoryDelta(k, d.delta)}</span> : null}
                        </span>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  )
}
