import { useState } from 'react'
import { lastCommittedPick, managerName } from '../../lib/draftState'
import { useDraftStore } from '../../store/draftStore'
import { DraftBoard } from './DraftBoard'
import { LeagueProfiles } from './LeagueProfiles'
import { RecentPicks } from './RecentPicks'

type HistoryTab = 'recent' | 'board' | 'profiles'

/** Collapsible bottom section: recent picks (with corrections), the full board, league-wide category profiles. */
export function HistoryDrawer() {
  const state = useDraftStore((s) => s.state)
  const players = useDraftStore((s) => s.players)
  const [open, setOpen] = useState(true)
  const [tab, setTab] = useState<HistoryTab>('recent')
  if (!state) return null
  const last = lastCommittedPick(state)
  return (
    <section className="panel history" aria-label="Draft history">
      <div className="history-head">
        <button type="button" className="small" aria-expanded={open} aria-controls="history-body" onClick={() => setOpen((o) => !o)} data-testid="history-toggle">
          {open ? '▾' : '▸'} Draft history
        </button>
        <span className="last">
          {last ? (
            <>
              Last pick <b>#{last.overall}</b> {players[last.player_id]?.name ?? last.player_id} → {managerName(state, last.manager_id)}
            </>
          ) : (
            'No picks yet'
          )}
          <span className="muted"> · {state.picks.length} of {state.schedule.length} recorded</span>
        </span>
        <span className="spacer" />
        <div className="tabs" role="tablist" style={{ borderBottom: 'none', marginBottom: 0 }}>
          <button type="button" role="tab" aria-selected={tab === 'recent'} onClick={() => { setTab('recent'); setOpen(true) }}>
            Recent picks
          </button>
          <button type="button" role="tab" aria-selected={tab === 'board'} onClick={() => { setTab('board'); setOpen(true) }} data-testid="tab-board">
            Draft board
          </button>
          <button type="button" role="tab" aria-selected={tab === 'profiles'} onClick={() => { setTab('profiles'); setOpen(true) }} data-testid="tab-profiles">
            League category profiles
          </button>
        </div>
      </div>
      {open && (
        <div className="history-body" id="history-body">
          {tab === 'recent' && <RecentPicks />}
          {tab === 'board' && <DraftBoard />}
          {tab === 'profiles' && <LeagueProfiles />}
        </div>
      )}
    </section>
  )
}
