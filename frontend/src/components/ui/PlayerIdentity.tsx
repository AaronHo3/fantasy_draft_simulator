import type { ReactNode } from 'react'
import { positionsText } from '../../lib/format'
import { teamColor } from '../../lib/teamColors'
import { Portrait } from '../performers/Portrait'

interface PlayerIdentityProps {
  name: ReactNode
  team: string | null | undefined
  positions?: string[] | null
  espnId?: number | null
  size?: number
  /** Extra line under the name (status, games, flags). */
  meta?: ReactNode
  portrait?: boolean
}

/** Portrait (or initials), name, and a team-coloured mark with team · positions. */
export function PlayerIdentity({ name, team, positions, espnId, size = 32, meta, portrait = true }: PlayerIdentityProps) {
  const color = teamColor(team)
  return (
    <span className="player-id">
      {portrait && <Portrait name={typeof name === 'string' ? name : String(team ?? '')} espnId={espnId} team={team} size={size} />}
      <span className="player-id-text">
        <span className="player-id-name">{name}</span>
        <span className="player-id-meta">
          <span className="team-mark" style={{ background: color.primary }} aria-hidden="true" />
          {team ?? 'FA'}
          {positions && positions.length > 0 ? ` · ${positionsText(positions)}` : ''}
          {meta ? <> · {meta}</> : null}
        </span>
      </span>
    </span>
  )
}

/** Small coloured square plus tricode, for tables and chart labels. */
export function TeamMark({ team }: { team: string | null | undefined }) {
  const color = teamColor(team)
  return (
    <span className="team-tag">
      <span className="team-mark" style={{ background: color.primary }} aria-hidden="true" />
      {team ?? 'FA'}
    </span>
  )
}
