import { useDraftStore } from '../../store/draftStore'

interface PlayerNameProps {
  playerId: string
  name?: string | null
}

/** Player name that opens the detail drawer. Falls back to the player index, then the raw id. */
export function PlayerName({ playerId, name }: PlayerNameProps) {
  const indexed = useDraftStore((s) => s.players[playerId]?.name)
  const open = useDraftStore((s) => s.openDrawer)
  const label = name ?? indexed ?? playerId
  return (
    <button type="button" className="player-link" onClick={() => open(playerId)} aria-label={`Open details for ${label}`}>
      {label}
    </button>
  )
}
