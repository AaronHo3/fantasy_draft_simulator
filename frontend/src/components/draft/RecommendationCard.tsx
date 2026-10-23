import { managerName, userIsOnClock } from '../../lib/draftState'
import { categoryLabel, fmtNum, positionsText } from '../../lib/format'
import { selectRecCurrent, useDraftStore } from '../../store/draftStore'
import { Diverging } from '../charts/Diverging'
import { Badge } from '../common/Badge'
import { PlayerName } from '../common/PlayerName'
import { Portrait } from '../performers/Portrait'
import { Tooltip } from '../ui/Tooltip'

/** Hero card for the best pick: who, value above replacement (± sd from the API), fit, category impact, risk. */
export function RecommendationCard() {
  const state = useDraftStore((s) => s.state)
  const rec = useDraftStore((s) => s.rec)
  const recStatus = useDraftStore((s) => s.recStatus)
  const recError = useDraftStore((s) => s.recError)
  const current = useDraftStore(selectRecCurrent)
  const pendingCommit = useDraftStore((s) => s.pendingCommit)
  const previewPlayerId = useDraftStore((s) => s.previewPlayerId)
  const previewCandidate = useDraftStore((s) => s.rec?.preview_candidate ?? s.previewCandidate)
  const setPreview = useDraftStore((s) => s.setPreview)
  const toggleCompare = useDraftStore((s) => s.toggleCompare)
  const compareIds = useDraftStore((s) => s.compareIds)
  const commitPick = useDraftStore((s) => s.commitPick)
  const highlightedId = current && rec ? rec.highlighted?.player_id ?? null : null
  const espnId = useDraftStore((s) => (highlightedId ? s.players[highlightedId]?.espn_id ?? null : null))
  if (!state) return null

  const onClock = userIsOnClock(state)
  const h = current && rec ? rec.highlighted : null
  const alternatives = current && rec ? rec.shortlist.slice(1, 4) : []
  const cats = state.league.categories
  const draftDisabledReason = pendingCommit
    ? 'A pick is still saving.'
    : !onClock
      ? `${managerName(state, state.on_clock_manager_id)} is on the clock. Record their pick first; this is your best pick when your turn comes.`
      : null
  const impact = h
    ? cats
        .map((c) => ({ id: c.key, label: categoryLabel(c.key, cats), value: h.contributions[c.key] ?? null, sublabel: c.higher_is_better ? undefined : 'lower is better' }))
        .sort((a, b) => Math.abs(b.value ?? 0) - Math.abs(a.value ?? 0))
    : []

  return (
    <section className={current ? 'rec-card' : 'rec-card stale'} aria-labelledby="rec-h" data-testid="rec-card" aria-busy={!current}>
      <div className="rec-top">
        <h3 id="rec-h" className="rec-kicker">
          {onClock ? 'Your best pick now' : 'Best pick at your next turn'}
          {previewPlayerId ? ' (preview)' : ''}
        </h3>
        {current && rec ? (
          <span className="muted small-text">
            fast ranking {fmtNum(rec.computed_ms, 0)} ms · <Badge tone="accent">tier {rec.tier}</Badge>
          </span>
        ) : (
          <Badge testId="rec-updating">recalculating…</Badge>
        )}
      </div>
      {previewPlayerId && previewCandidate && (
        <p className="callout" style={{ margin: '0 0 10px' }}>
          Previewing <b>{previewCandidate.name}</b>: roster, categories and this shortlist assume you draft them.{' '}
          <button type="button" className="small" onClick={() => setPreview(null)}>
            Clear preview
          </button>
        </p>
      )}
      {!current && recStatus === 'error' && (
        <p className="callout error" role="alert">
          Recommendation failed: {recError}
        </p>
      )}
      {!current && recStatus !== 'error' && <p className="muted">Recalculating for the current board…</p>}
      {current && !h && <div className="empty-state">No available players fit your remaining roster.</div>}
      {h && (
        <>
          <div className="rec-body">
            <div>
              <div className="rec-who">
                <Portrait name={h.name} espnId={espnId} team={h.team} size={56} />
                <div>
                  <div className="rec-name" data-testid="rec-name" data-player-id={h.player_id}>
                    <PlayerName playerId={h.player_id} name={h.name} />
                  </div>
                  <div className="rec-sub">
                    <span>
                      {h.team ?? 'FA'} · {positionsText(h.eligible_positions)}
                    </span>
                    {!h.completion_ok && <Badge tone="warn">completion risk</Badge>}
                    {!h.eligibility_verified && <Badge tone="warn">eligibility unverified</Badge>}
                    {h.flags.map((f) => (
                      <Badge key={f}>{f}</Badge>
                    ))}
                  </div>
                </div>
              </div>
              <div className="rec-facts">
                <Tooltip content="Weighted z above the best player likely to be available at your next pick; ± one standard deviation from the projection model.">
                  <span className="fact" tabIndex={0}>
                    <span className="fact-k">Value above replacement</span>
                    <span className="fact-v">
                      {fmtNum(h.score, 2)} <span className="sd">± {fmtNum(h.value_sd, 2)}</span>
                    </span>
                  </span>
                </Tooltip>
                <span className="fact">
                  <span className="fact-k">Fills</span>
                  <span className="fact-v small">
                    {h.slot ?? '—'}
                    <span className="sd"> {h.fills_open_starting_slot ? 'open starting slot' : h.slot === 'BENCH' ? 'bench' : ''}</span>
                  </span>
                </span>
                <span className="fact">
                  <span className="fact-k">Projected</span>
                  <span className="fact-v small">
                    {fmtNum(h.games, 0)} GP <span className="sd">· {fmtNum(h.minutes, 1)} MIN</span>
                  </span>
                </span>
                <span className="fact">
                  <span className="fact-k">Availability</span>
                  <span className="fact-v small">{h.survival_hint}</span>
                </span>
              </div>
              {h.reasons.length > 0 && (
                <ul className="rec-reasons" aria-label="Reasons">
                  {h.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rec-impact">
              <h4>Category impact under your strategy (weighted z)</h4>
              <Diverging rows={impact} format={(v) => v.toFixed(2)} unit="weighted z" negativeLabel="costs" positiveLabel="adds" />
            </div>
          </div>
          <div className="rec-actions">
            <button
              type="button"
              className="primary"
              data-testid="rec-draft"
              disabled={draftDisabledReason !== null}
              title={draftDisabledReason ?? `Draft ${h.name} for ${managerName(state, state.league.user_manager_id)}`}
              onClick={() => void commitPick(h.player_id, state.league.user_manager_id)}
            >
              Draft to my team
            </button>
            <button type="button" data-testid="rec-preview" onClick={() => setPreview(previewPlayerId === h.player_id ? null : h.player_id, h)} aria-pressed={previewPlayerId === h.player_id}>
              Preview
            </button>
            <button type="button" onClick={() => toggleCompare(h.player_id)} aria-pressed={compareIds.includes(h.player_id)}>
              {compareIds.includes(h.player_id) ? 'In compare' : 'Compare'}
            </button>
            {draftDisabledReason && <span className="muted small-text">{draftDisabledReason}</span>}
          </div>
          {alternatives.length > 0 && (
            <div className="rec-alts" aria-label="Alternatives">
              <span className="muted">Next best:</span>
              {alternatives.map((a) => (
                <span key={a.player_id}>
                  <PlayerName playerId={a.player_id} name={a.name} />{' '}
                  <span className="muted">
                    {fmtNum(a.score, 2)} · {a.slot ?? '—'}
                    {a.tier === h.tier ? ' · same tier' : ''}
                  </span>
                </span>
              ))}
            </div>
          )}
        </>
      )}
      {current && rec && rec.notes.length > 0 && (
        <ul className="muted" aria-label="Notes" style={{ marginTop: 8, fontSize: 12, paddingLeft: 18 }}>
          {rec.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
