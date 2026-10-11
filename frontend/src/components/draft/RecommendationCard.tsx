import { managerName, userIsOnClock } from '../../lib/draftState'
import { fmtNum, positionsText } from '../../lib/format'
import { selectRecCurrent, useDraftStore } from '../../store/draftStore'
import { Badge } from '../common/Badge'
import { PlayerName } from '../common/PlayerName'

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
  if (!state) return null

  const onClock = userIsOnClock(state)
  const h = current && rec ? rec.highlighted : null
  const alternatives = current && rec ? rec.shortlist.slice(1, 4) : []
  const draftDisabledReason = pendingCommit
    ? 'A pick is still saving.'
    : !onClock
      ? `${managerName(state, state.on_clock_manager_id)} is on the clock. Record their pick first; this is your best pick when your turn comes.`
      : null

  return (
    <section className={current ? 'rec-card' : 'rec-card stale'} aria-labelledby="rec-h" data-testid="rec-card" aria-busy={!current}>
      <div className="row between">
        <h3 id="rec-h">{onClock ? 'Your best pick now' : 'Best pick at your next turn'}{previewPlayerId ? ' (preview)' : ''}</h3>
        {current && rec ? (
          <span className="muted small-text">
            fast ranking {fmtNum(rec.computed_ms, 0)} ms · <Badge tone="accent">tier {rec.tier}</Badge>
          </span>
        ) : (
          <Badge testId="rec-updating">recalculating…</Badge>
        )}
      </div>
      {previewPlayerId && previewCandidate && (
        <p className="callout" style={{ margin: '6px 0' }}>
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
          <div className="title" data-testid="rec-name" data-player-id={h.player_id}>
            <PlayerName playerId={h.player_id} name={h.name} />{' '}
            <span className="muted" style={{ fontSize: 13, fontWeight: 400 }}>
              {h.team ?? '—'} · {positionsText(h.eligible_positions)}
            </span>
          </div>
          <div className="meta">
            <span>
              value above replacement <b>{fmtNum(h.score, 2)}</b> <span className="muted">± {fmtNum(h.value_sd, 2)}</span>
            </span>
            <span>
              fills <b>{h.slot ?? '—'}</b>
              {h.fills_open_starting_slot ? ' (open starting slot)' : h.slot === 'BENCH' ? ' (bench)' : ''}
            </span>
            <span>
              {fmtNum(h.games, 0)} GP · {fmtNum(h.minutes, 1)} MIN <span className="muted">projected</span>
            </span>
            <span className="muted">{h.survival_hint}</span>
            {!h.completion_ok && <Badge tone="warn">completion risk</Badge>}
            {!h.eligibility_verified && <Badge tone="warn">eligibility unverified</Badge>}
            {h.flags.map((f) => (
              <Badge key={f}>{f}</Badge>
            ))}
          </div>
          <ul aria-label="Reasons">
            {h.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <div className="actions">
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
            <div className="alts" aria-label="Alternatives">
              <span className="muted">Next best:</span>
              {alternatives.map((a) => (
                <span key={a.player_id}>
                  <PlayerName playerId={a.player_id} name={a.name} /> <span className="muted">{fmtNum(a.score, 2)} · {a.slot ?? '—'}{a.tier === h.tier ? ' · same tier' : ''}</span>
                </span>
              ))}
            </div>
          )}
        </>
      )}
      {current && rec && rec.notes.length > 0 && (
        <ul className="muted" aria-label="Notes" style={{ marginTop: 6, fontSize: 12 }}>
          {rec.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
