import { useEffect } from 'react'
import { managerName } from '../../lib/draftState'
import { fmtNum, PER_GAME_KEYS, positionsText } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { Badge } from '../common/Badge'

export function PlayerDrawer() {
  const id = useDraftStore((s) => s.drawerPlayerId)
  const player = useDraftStore((s) => (s.drawerPlayerId ? s.players[s.drawerPlayerId] ?? null : null))
  const playersStatus = useDraftStore((s) => s.playersStatus)
  const state = useDraftStore((s) => s.state)
  const close = useDraftStore((s) => s.openDrawer)
  const toggleCompare = useDraftStore((s) => s.toggleCompare)
  const compareIds = useDraftStore((s) => s.compareIds)
  const previewPlayerId = useDraftStore((s) => s.previewPlayerId)
  const setPreview = useDraftStore((s) => s.setPreview)

  useEffect(() => {
    if (!id) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [id, close])

  if (!id) return null
  const pick = state?.picks.find((p) => p.player_id === id)
  return (
    <aside className="drawer" role="dialog" aria-label="Player details" data-testid="player-drawer">
      <div className="row between" style={{ marginBottom: 6 }}>
        <h2>{player?.name ?? id}</h2>
        <button type="button" onClick={() => close(null)} aria-label="Close player details">
          Close (Esc)
        </button>
      </div>
      {!player && <p className="muted">{playersStatus === 'loading' ? 'Loading player index…' : 'Player not in the loaded snapshot index.'}</p>}
      {player && (
        <>
          <div className="row" style={{ marginBottom: 6 }}>
            <span>{player.team ?? '—'}</span>
            <span>
              primary <b>{player.primary_position ?? '—'}</b> · eligible <b>{positionsText(player.eligible_positions)}</b>
            </span>
            <Badge tone={player.eligibility_verified ? 'ok' : 'warn'}>
              eligibility {player.eligibility_verified ? 'verified' : 'unverified'} ({player.eligibility_source})
            </Badge>
          </div>
          <div className="row" style={{ marginBottom: 6 }}>
            <span>status {player.injury_status ?? '—'}</span>
            <span>ADP {fmtNum(player.adp, 1)}</span>
            <span>rank {fmtNum(player.rank, 0)}</span>
            <span>age {fmtNum(player.age, 0)}</span>
            {player.is_rookie && <Badge>rookie</Badge>}
            <Badge>projection: {player.projection_source}</Badge>
            {pick && state && (
              <Badge tone="warn">
                drafted by {managerName(state, pick.manager_id)} at #{pick.overall}
              </Badge>
            )}
          </div>
          <table className="grid" aria-label="Per-game projection">
            <thead>
              <tr>
                <th scope="col">Stat</th>
                <th scope="col" className="num">per game</th>
                <th scope="col" className="num">± sd</th>
              </tr>
            </thead>
            <tbody>
              {PER_GAME_KEYS.map((k) => (
                <tr key={k}>
                  <th scope="row">{k === 'GP' ? 'GP (season)' : k === 'MIN' ? 'MIN (per game)' : k}</th>
                  <td className="num">{fmtNum(player.per_game[k], k === 'GP' ? 0 : 1)}</td>
                  <td className="num muted">{fmtNum(player.per_game_sd[k], 1)}</td>
                </tr>
              ))}
              <tr>
                <th scope="row">FG% (FGM/FGA)</th>
                <td className="num">{player.per_game.FGA ? (player.per_game.FGM / player.per_game.FGA).toFixed(3) : '—'}</td>
                <td className="num muted">{fmtNum(player.per_game.FGA, 1)} FGA/g</td>
              </tr>
              <tr>
                <th scope="row">FT% (FTM/FTA)</th>
                <td className="num">{player.per_game.FTA ? (player.per_game.FTM / player.per_game.FTA).toFixed(3) : '—'}</td>
                <td className="num muted">{fmtNum(player.per_game.FTA, 1)} FTA/g</td>
              </tr>
            </tbody>
          </table>
          <div className="row" style={{ marginTop: 8 }}>
            {!pick && (
              <button type="button" onClick={() => setPreview(previewPlayerId === player.player_id ? null : player.player_id)} aria-pressed={previewPlayerId === player.player_id}>
                {previewPlayerId === player.player_id ? 'Stop preview' : 'Preview on my roster'}
              </button>
            )}
            <button type="button" onClick={() => toggleCompare(player.player_id)} aria-pressed={compareIds.includes(player.player_id)}>
              {compareIds.includes(player.player_id) ? 'Remove from compare' : 'Add to compare'}
            </button>
            <span className="mono muted">{player.player_id}</span>
          </div>
        </>
      )}
    </aside>
  )
}
