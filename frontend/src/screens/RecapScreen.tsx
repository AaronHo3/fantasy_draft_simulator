import { api } from '../api/client'
import { ProfileTable } from '../components/draft/CategoryProfileTable'
import { OpponentRosters } from '../components/draft/OpponentRosters'
import { PlayerDrawer } from '../components/draft/PlayerDrawer'
import { Icon } from '../components/ui/Icon'
import { PageHeader, type ContextChip } from '../components/ui/PageHeader'
import { StatCard, StatRow } from '../components/ui/StatCard'
import { EmptyState } from '../components/ui/States'
import { buildUrl } from '../lib/router'
import { selectRecCurrent, useDraftStore } from '../store/draftStore'

/** Draft recap: picks recorded, my category profile, and every final roster. */
export function RecapScreen() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const state = useDraftStore((s) => s.state)
  const rec = useDraftStore((s) => s.rec)
  const current = useDraftStore(selectRecCurrent)
  const notify = useDraftStore((s) => s.notify)
  const isDemo = useDraftStore((s) => s.snapshot?.is_demo ?? false)
  if (!sessionId || !state) {
    return (
      <EmptyState title="No session loaded" action={<a href={buildUrl('setup', null)}>Go to setup</a>}>
        The recap summarises a draft session.
      </EmptyState>
    )
  }

  const exportJson = async () => {
    try {
      const data = await api.exportSession(sessionId)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `draft-session-${sessionId}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      notify('error', `Export failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }
  const uid = state.league.user_manager_id
  const myCount = (state.has_roster_moves ? state.current_rosters[uid] : state.rosters[uid])?.length ?? 0
  const strengths = current && rec ? Object.entries(rec.category_profile.z).filter(([, z]) => z > 1).length : null
  const weaknesses = current && rec ? Object.entries(rec.category_profile.z).filter(([, z]) => z < -1).length : null
  const chips: ContextChip[] = [{ label: 'Format', value: state.league.scoring_format.replace('h2h_', 'H2H ').replace('_', ' '), tone: state.format_confirmed ? 'neutral' : 'warn' }]
  if (isDemo) chips.push({ label: 'Data', value: 'demo', tone: 'demo' })

  return (
    <div className="stack" data-testid="recap">
      <PageHeader
        title={state.is_complete ? 'Draft recap' : 'Draft recap (in progress)'}
        description={state.is_complete ? 'Every pick is recorded. Your projected category profile and every final roster, before any in-season moves.' : 'A snapshot of the draft so far.'}
        chips={chips}
        actions={
          <>
            <button type="button" className="primary" onClick={() => void exportJson()}>
              <Icon name="download" size={14} /> Export session JSON
            </button>
            {!state.is_complete && <a href={buildUrl('draft', sessionId)}>Back to the draft</a>}
          </>
        }
      />
      <StatRow>
        <StatCard label="Picks recorded" value={`${state.picks.length} / ${state.schedule.length}`} detail={state.is_complete ? 'draft complete' : `${state.schedule.length - state.picks.length} to go`} />
        <StatCard label="My roster" value={myCount} detail={state.has_roster_moves ? 'after ESPN moves' : 'drafted players'} />
        <StatCard label="Strong categories" value={strengths ?? '—'} detail="z above +1" tone={strengths ? 'good' : 'neutral'} />
        <StatCard label="Weak categories" value={weaknesses ?? '—'} detail="z below −1" tone={weaknesses ? 'bad' : 'neutral'} />
      </StatRow>
      <section className="panel">
        <div className="section-title">
          <h2>My category profile</h2>
          <span className="muted">projected season totals</span>
        </div>
        {current && rec ? <ProfileTable profile={rec.category_profile} categories={state.league.categories ?? []} /> : <p className="muted">updating…</p>}
      </section>
      <section className="panel">
        <div className="section-title">
          <h2>Final rosters</h2>
          <span className="muted">{state.has_roster_moves ? 'current rosters; players added after the draft are marked' : 'as drafted'}</span>
        </div>
        <OpponentRosters />
      </section>
      <PlayerDrawer />
    </div>
  )
}
