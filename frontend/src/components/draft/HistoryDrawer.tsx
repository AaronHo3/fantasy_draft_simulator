import { useState } from 'react'
import { lastCommittedPick, managerName } from '../../lib/draftState'
import { useDraftStore } from '../../store/draftStore'
import { Icon } from '../ui/Icon'
import { Segmented } from '../ui/Segmented'
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
        <button type="button" className="small ghost" aria-expanded={open} aria-controls="history-body" onClick={() => setOpen((o) => !o)} data-testid="history-toggle">
          <Icon name={open ? 'chevron-down' : 'chevron-right'} size={14} /> Draft history
        </button>
        <span className="last">
          {last ? (
            <>
              Last pick <b>#{last.overall}</b> {players[last.player_id]?.name ?? last.player_id} to {managerName(state, last.manager_id)}
            </>
          ) : (
            'No picks yet'
          )}
          <span className="muted">
            {' '}
            · {state.picks.length} of {state.schedule.length} recorded
          </span>
        </span>
        <span className="spacer" />
        <Segmented<HistoryTab>
          variant="pill"
          label="History view"
          value={tab}
          onChange={(t) => {
            setTab(t)
            setOpen(true)
          }}
          options={[
            { id: 'recent', label: 'Recent picks' },
            { id: 'board', label: 'Draft board', testId: 'tab-board' },
            { id: 'profiles', label: 'League profiles', testId: 'tab-profiles' },
          ]}
        />
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
