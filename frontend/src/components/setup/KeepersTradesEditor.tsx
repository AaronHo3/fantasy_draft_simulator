import type { Keeper, LeagueConfig, TradedPick } from '../../api/types'

interface Props {
  league: LeagueConfig
  onChange: (l: LeagueConfig) => void
}

export function KeepersTradesEditor({ league, onChange }: Props) {
  const keepers = league.keepers ?? []
  const trades = league.traded_picks ?? []
  const managers = league.managers
  const first = managers[0]?.id ?? ''
  const second = managers[1]?.id ?? first

  const setKeeper = (i: number, k: Keeper) => onChange({ ...league, keepers: keepers.map((x, j) => (j === i ? k : x)) })
  const setTrade = (i: number, t: TradedPick) => onChange({ ...league, traded_picks: trades.map((x, j) => (j === i ? t : x)) })

  return (
    <fieldset>
      <legend>Keepers and traded picks</legend>
      <div className="stack">
        {keepers.map((k, i) => (
          <div className="row" key={`k-${i}`}>
            <span className="muted">Keeper</span>
            <select aria-label="Keeper manager" value={k.manager_id} onChange={(e) => setKeeper(i, { ...k, manager_id: e.target.value })}>
              {managers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
            <input aria-label="Keeper player id" placeholder="player id (e.g. demo:0001)" value={k.player_id} onChange={(e) => setKeeper(i, { ...k, player_id: e.target.value })} />
            <label>
              round <input type="number" min={1} value={k.round} onChange={(e) => setKeeper(i, { ...k, round: Math.max(1, Number(e.target.value) || 1) })} />
            </label>
            <button type="button" className="small" onClick={() => onChange({ ...league, keepers: keepers.filter((_, j) => j !== i) })} aria-label="Remove keeper">
              Remove
            </button>
          </div>
        ))}
        {trades.map((t, i) => (
          <div className="row" key={`t-${i}`}>
            <span className="muted">Traded pick</span>
            <label>
              round <input type="number" min={1} value={t.round} onChange={(e) => setTrade(i, { ...t, round: Math.max(1, Number(e.target.value) || 1) })} />
            </label>
            <span>from</span>
            <select aria-label="From manager" value={t.from_manager_id} onChange={(e) => setTrade(i, { ...t, from_manager_id: e.target.value })}>
              {managers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
            <span>to</span>
            <select aria-label="To manager" value={t.to_manager_id} onChange={(e) => setTrade(i, { ...t, to_manager_id: e.target.value })}>
              {managers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
            <button type="button" className="small" onClick={() => onChange({ ...league, traded_picks: trades.filter((_, j) => j !== i) })} aria-label="Remove traded pick">
              Remove
            </button>
          </div>
        ))}
        <div className="row">
          <button type="button" className="small" onClick={() => onChange({ ...league, keepers: [...keepers, { manager_id: first, player_id: '', round: 1 }] })}>
            Add keeper
          </button>
          <button type="button" className="small" onClick={() => onChange({ ...league, traded_picks: [...trades, { round: 1, from_manager_id: first, to_manager_id: second }] })}>
            Add traded pick
          </button>
          <span className="muted">Keeper player ids come from the snapshot (search in the draft picker shows them).</span>
        </div>
      </div>
    </fieldset>
  )
}
