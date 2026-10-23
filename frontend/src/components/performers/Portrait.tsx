import { useState } from 'react'
import { teamColor } from '../../lib/teamColors'

/** ESPN's public headshot CDN, the same source the app's player data comes from; null without an ESPN id. */
export function portraitUrl(espnId: number | null | undefined): string | null {
  return espnId ? `https://a.espncdn.com/i/headshots/nba/players/full/${espnId}.png` : null
}

export function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean)
  return parts.length === 0 ? '?' : (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

interface PortraitProps {
  name: string
  espnId: number | null | undefined
  team: string | null | undefined
  size?: number
}

/** Player headshot with a team-colored initials fallback when there is no id or the image fails. */
export function Portrait({ name, espnId, team, size = 48 }: PortraitProps) {
  const [failed, setFailed] = useState(false)
  const url = portraitUrl(espnId)
  const color = teamColor(team)
  const style = { width: size, height: size, borderColor: color.primary }
  if (!url || failed) {
    return (
      <span className="portrait fallback" style={{ ...style, background: color.primary }} data-testid="portrait-fallback" aria-label={name} role="img">
        {initials(name)}
      </span>
    )
  }
  return <img className="portrait" src={url} alt={name} width={size} height={size} loading="lazy" style={style} onError={() => setFailed(true)} />
}
