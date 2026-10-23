import { Fragment, useMemo, useState } from 'react'
import type { RefinedCandidate } from '../../api/types'
import { managerName, userIsOnClock } from '../../lib/draftState'
import { categoryLabel, fmtCategoryDelta, fmtCategoryValue, fmtNum, fmtPct, fmtSigned, positionsText, topContributions } from '../../lib/format'
import { selectRecCurrent, selectRefineCurrent, useDraftStore } from '../../store/draftStore'
import { PlayerName } from '../common/PlayerName'
import { Icon } from '../ui/Icon'

export function ShortlistTable() {
  const state = useDraftStore((s) => s.state)
  const rec = useDraftStore((s) => s.rec)
  const current = useDraftStore(selectRecCurrent)
  const refineCurrent = useDraftStore(selectRefineCurrent)
  const refineResult = useDraftStore((s) => s.refineResult)
  const refineJob = useDraftStore((s) => s.refineJob)
  const refineUnavailable = useDraftStore((s) => s.refineUnavailable)
  const pendingCommit = useDraftStore((s) => s.pendingCommit)
  const previewPlayerId = useDraftStore((s) => s.previewPlayerId)
  const setPreview = useDraftStore((s) => s.setPreview)
  const compareIds = useDraftStore((s) => s.compareIds)
  const toggleCompare = useDraftStore((s) => s.toggleCompare)
  const runCompare = useDraftStore((s) => s.runCompare)
  const clearCompare = useDraftStore((s) => s.clearCompare)
  const commitPick = useDraftStore((s) => s.commitPick)
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const toggleExpanded = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const refined = useMemo(() => {
    const m = new Map<string, RefinedCandidate>()
    if (refineCurrent && refineResult) for (const c of refineResult.candidates) m.set(c.player_id, c)
    return m
  }, [refineCurrent, refineResult])

  if (!state) return null
  const rows = rec?.shortlist ?? []
  const onClock = state.on_clock_manager_id
  const meOnClock = userIsOnClock(state)
  const canDraft = onClock !== null && !pendingCommit
  const refinePending = refineJob && (refineJob.status === 'queued' || refineJob.status === 'running')
  const refineNote = refineUnavailable
    ? 'Refine (tiers B/C) unavailable in this build (501); showing fast tier A only.'
    : refinePending
      ? 'Refining (tier B/C)… order is held until it completes.'
      : refineJob?.status === 'failed'
        ? `Refine failed: ${refineJob.error ?? 'unknown error'}`
        : refineJob?.status === 'timeout'
          ? 'Refine timed out (20 s cap).'
          : refineCurrent && refineResult
            ? `Refined columns: ${refineResult.objective_label} · ${refineResult.scenarios} scenarios · ${refineResult.opponent_model} · supplementary: not yet shown to beat the fast ranking in the retrospective test (docs/EVALUATION.md)`
            : null

  return (
    <section aria-labelledby="shortlist-h">
      <div className="panel-head">
        <h3 id="shortlist-h">Ranked for my next pick</h3>
        <div className="row">
          {compareIds.length > 0 && (
            <>
              <button type="button" className="small primary" disabled={compareIds.length < 2} onClick={() => void runCompare()}>
                Compare {compareIds.length} selected
              </button>
              <button type="button" className="small" onClick={clearCompare}>
                Clear
              </button>
            </>
          )}
          {!current && <span className="badge">recalculating…</span>}
        </div>
      </div>
      {refineNote && <p className="muted" style={{ fontSize: 12 }}>{refineNote}</p>}
      <div className="table-wrap tall">
        <table className="grid" data-testid="shortlist-table" aria-busy={!current}>
          <thead>
            <tr>
              <th scope="col" className="num">#</th>
              <th scope="col">
                <span className="visually-hidden">Details</span>
              </th>
              <th scope="col" className="sticky-col">Player</th>
              <th scope="col">Pos</th>
              <th scope="col">Team</th>
              <th scope="col" className="num">Score</th>
              <th scope="col" className="num">Tier</th>
              <th scope="col" title="Slot filled, top category gains and costs under your strategy">Fit</th>
              <th scope="col" className="num" title="Refined marginal utility (tier B/C)">Marg. util</th>
              <th scope="col" className="num" title="Refined survival probability to your next pick">Surv. P</th>
              <th scope="col" className="num" title="Refined draft-now advantage vs waiting">Draft-now</th>
              <th scope="col" className="num">Base</th>
              <th scope="col">Replacement</th>
              <th scope="col" className="num">GP / MIN</th>
              <th scope="col" className="num">ADP</th>
              <th scope="col">Survival</th>
              <th scope="col">Flags</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => {
              const { gains, costs } = topContributions(c)
              const r = refined.get(c.player_id)
              const tierStart = i === 0 || rows[i - 1].tier !== c.tier
              const cats = state.league.categories
              const isOpen = expanded.has(c.player_id)
              return (
                <Fragment key={c.player_id}>
                <tr className={tierStart ? 'tier-start' : undefined} data-testid="shortlist-row" data-player-id={c.player_id} data-tier={c.tier}>
                  <td className="num">{i + 1}</td>
                  <td>
                    <button type="button" className="small ghost icon-btn" aria-expanded={isOpen} aria-label={`${isOpen ? 'Hide' : 'Show'} full category breakdown for ${c.name}`} data-testid="shortlist-expand" onClick={() => toggleExpanded(c.player_id)}>
                      <Icon name={isOpen ? 'chevron-down' : 'chevron-right'} size={13} />
                    </button>
                  </td>
                  <th scope="row" className="sticky-col">
                    <PlayerName playerId={c.player_id} name={c.name} />
                    {!c.eligibility_verified && <span className="badge warn"> unverified</span>}
                  </th>
                  <td>{positionsText(c.eligible_positions)}</td>
                  <td>{c.team ?? '—'}</td>
                  <td className="num">
                    {fmtNum(c.score, 2)} <span className="muted">±{fmtNum(c.value_sd, 1)}</span>
                  </td>
                  <td className="num">{tierStart ? <b>T{c.tier}</b> : <span className="muted">T{c.tier}</span>}</td>
                  <td className="nowrap">
                    <b>{c.slot ?? '—'}</b>
                    {c.fills_open_starting_slot ? '' : c.slot ? <span className="muted"> bench</span> : ''}
                    {!c.completion_ok && <span className="badge warn"> completion</span>}
                    {gains.length > 0 && <span className="pos"> {gains.join(' ')}</span>}
                    {costs.length > 0 && <span className="neg"> {costs.join(' ')}</span>}
                  </td>
                  <td className="num">{r ? fmtSigned(r.marginal_utility, 3) : <span className="muted">—</span>}</td>
                  <td className="num">
                    {r ? (
                      <span title={r.survival_label}>
                        {r.survival_probability === null ? <span className="muted">n/a</span> : fmtPct(r.survival_probability)}
                        {r.survival_probability !== null && r.survival_label === 'proxy' && <span className="muted"> (proxy)</span>}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="num">{r ? fmtSigned(r.draft_now_advantage, 3) : <span className="muted">—</span>}</td>
                  <td className="num">{fmtNum(c.base_value, 2)}</td>
                  <td>
                    {c.replacement_name ?? '—'} <span className="muted">{fmtNum(c.replacement_value, 1)}</span>
                  </td>
                  <td className="num nowrap">
                    {fmtNum(c.games, 0)} / {fmtNum(c.minutes, 1)}
                  </td>
                  <td className="num">{fmtNum(c.adp, 1)}</td>
                  <td className="muted">{c.survival_hint}</td>
                  <td>
                    {c.flags.map((f) => (
                      <span key={f} className="badge" style={{ marginRight: 2 }}>
                        {f}
                      </span>
                    ))}
                  </td>
                  <td className="nowrap">
                    <button
                      type="button"
                      className={meOnClock ? 'small primary' : 'small'}
                      disabled={!canDraft}
                      onClick={() => onClock && void commitPick(c.player_id, onClock)}
                      title={meOnClock ? `Draft ${c.name} to my team` : `Record ${c.name} for ${managerName(state, onClock)} (on the clock)`}
                    >
                      {meOnClock ? 'Draft' : `Record for ${managerName(state, onClock)}`}
                    </button>{' '}
                    <button type="button" className="small" aria-pressed={previewPlayerId === c.player_id} onClick={() => setPreview(previewPlayerId === c.player_id ? null : c.player_id, c)}>
                      Preview
                    </button>{' '}
                    <label className="nowrap">
                      <input type="checkbox" checked={compareIds.includes(c.player_id)} onChange={() => toggleCompare(c.player_id)} aria-label={`Compare ${c.name}`} />
                      cmp
                    </label>
                  </td>
                </tr>
                {isOpen && (
                  <tr className="breakdown" data-testid="shortlist-breakdown" data-player-id={c.player_id}>
                    <td colSpan={20}>
                      <table className="grid compact" aria-label={`Category breakdown for ${c.name}`}>
                        <thead>
                          <tr>
                            <th scope="col">Category</th>
                            {cats.map((cat) => (
                              <th scope="col" className="num" key={cat.key}>
                                {categoryLabel(cat.key, cats)}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <th scope="row">Per game</th>
                            {cats.map((cat) => (
                              <td className="num" key={cat.key}>
                                {cat.key === 'FG_PCT'
                                  ? `${fmtCategoryValue(cat.key, c.per_game.FGA ? c.per_game.FGM / c.per_game.FGA : null)} (${fmtNum(c.per_game.FGA, 1)} FGA)`
                                  : cat.key === 'FT_PCT'
                                    ? `${fmtCategoryValue(cat.key, c.per_game.FTA ? c.per_game.FTM / c.per_game.FTA : null)} (${fmtNum(c.per_game.FTA, 1)} FTA)`
                                    : fmtNum(c.per_game[cat.key], 1)}
                              </td>
                            ))}
                          </tr>
                          <tr>
                            <th scope="row">z (season total vs. draft pool)</th>
                            {cats.map((cat) => (
                              <td className={`num ${(c.z[cat.key] ?? 0) > 0.5 ? 'pos' : (c.z[cat.key] ?? 0) < -0.5 ? 'neg' : ''}`} key={cat.key}>
                                {fmtSigned(c.z[cat.key], 2)}
                              </td>
                            ))}
                          </tr>
                          <tr>
                            <th scope="row">Weighted by your strategy</th>
                            {cats.map((cat) => (
                              <td className={`num ${(c.contributions[cat.key] ?? 0) > 0.5 ? 'pos' : (c.contributions[cat.key] ?? 0) < -0.5 ? 'neg' : ''}`} key={cat.key}>
                                {fmtSigned(c.contributions[cat.key], 2)}
                              </td>
                            ))}
                          </tr>
                          {c.category_deltas && (
                            <tr>
                              <th scope="row">Change to my totals if drafted</th>
                              {cats.map((cat) => {
                                const d = c.category_deltas?.[cat.key]
                                const good = d?.delta === null || d?.delta === undefined ? null : cat.higher_is_better ? d.delta > 0 : d.delta < 0
                                return (
                                  <td className={`num ${good === null ? '' : good ? 'pos' : 'neg'}`} key={cat.key} title={d ? `${fmtCategoryValue(cat.key, d.before)} → ${fmtCategoryValue(cat.key, d.after)} (${d.unit})` : undefined}>
                                    {d ? fmtCategoryDelta(cat.key, d.delta) : '—'}
                                  </td>
                                )
                              })}
                            </tr>
                          )}
                          {r && (
                            <tr>
                              <th scope="row">Simulated P(win category) after this pick</th>
                              {cats.map((cat) => (
                                <td className="num" key={cat.key}>
                                  {fmtPct(r.category_win_probs[cat.key])}
                                </td>
                              ))}
                            </tr>
                          )}
                        </tbody>
                      </table>
                      {c.reasons.length > 0 && (
                        <ul className="muted" style={{ margin: '4px 0 0 16px', fontSize: 12 }}>
                          {c.reasons.map((t) => (
                            <li key={t}>{t}</li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
              )
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={20}>
                  <div className="empty-state">{current ? 'No available players fit your remaining roster.' : 'Recalculating for the current board…'}</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
