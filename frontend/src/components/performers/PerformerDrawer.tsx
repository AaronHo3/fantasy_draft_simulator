import { useEffect } from 'react'
import type { CategoryDef, PerformerRow } from '../../api/types'
import { fmtNum, fmtSigned } from '../../lib/format'
import { Badge } from '../common/Badge'
import { Icon } from '../ui/Icon'
import { PlayerIdentity } from '../ui/PlayerIdentity'
import { StatCard, StatRow } from '../ui/StatCard'

const DETAIL_KEYS: { key: string; label: string }[] = [
  { key: 'PTS', label: 'Points' },
  { key: 'REB', label: 'Rebounds' },
  { key: 'AST', label: 'Assists' },
  { key: 'STL', label: 'Steals' },
  { key: 'BLK', label: 'Blocks' },
  { key: 'TOV', label: 'Turnovers' },
  { key: 'FG3M', label: 'Threes made' },
]

const pct1 = (v: number) => `${(v * 100).toFixed(1)}%`

function cell(v: number | null | undefined, key: string): string {
  if (v === null || v === undefined) return '—'
  return key.endsWith('PCT') ? pct1(v) : fmtNum(v, Number.isInteger(v) ? 0 : 1)
}

interface PerformerDrawerProps {
  row: PerformerRow
  onClose: () => void
  /** The league's scored categories; stats outside them are shown but labelled as not scored. */
  categories?: CategoryDef[]
}

/** Slide-in detail: actual vs expected production, games counted, makes/attempts, and the per-category units. */
export function PerformerDrawer({ row: r, onClose, categories }: PerformerDrawerProps) {
  const scored = categories ? new Set(categories.map((c) => c.key)) : null
  const isScored = (key: string) => scored === null || scored.has(key)
  const scoresTov = isScored('TOV')
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const hasBaseline = r.expected !== null && r.expected_contribution !== null
  return (
    <aside className="drawer performer-drawer" role="dialog" aria-label={`${r.player.name} details`} data-testid="performer-detail">
      <div className="drawer-head">
        <PlayerIdentity name={r.player.name} team={r.player.team} positions={r.player.eligible_positions} espnId={r.player.espn_id} size={56} meta={`${r.games} GP · ${fmtNum(r.minutes, 0)} MIN`} />
        <button type="button" onClick={onClose} aria-label="Close details">
          <Icon name="close" size={14} /> Close
        </button>
      </div>
      {r.flags.length > 0 && (
        <div className="row" style={{ marginBottom: 12 }}>
          {r.flags.map((f) => (
            <Badge key={f} tone={f === 'no games' ? 'neutral' : 'warn'}>
              {f}
            </Badge>
          ))}
        </div>
      )}
      <StatRow>
        <StatCard label="Contribution" value={fmtNum(r.contribution, 1)} detail={r.contribution_per_game === null ? 'units' : `${fmtNum(r.contribution_per_game, 2)} per game`} />
        <StatCard label="Expected" value={hasBaseline ? fmtNum(r.expected_contribution, 1) : '—'} detail={hasBaseline ? 'projection × games played' : 'no baseline (prior only)'} />
        <StatCard
          label="Vs expected"
          value={r.over_expected === null ? '—' : fmtSigned(r.over_expected, 1)}
          detail={r.over_expected_per_game === null ? '' : `${fmtSigned(r.over_expected_per_game, 2)} per game`}
          tone={r.over_expected === null ? 'neutral' : r.over_expected > 0 ? 'good' : r.over_expected < 0 ? 'bad' : 'neutral'}
        />
        <StatCard label="Games counted" value={r.games} detail={`${r.periods} week${r.periods === 1 ? '' : 's'} with games`} />
      </StatRow>
      <h3 style={{ margin: '16px 0 6px' }}>Production: actual vs expected</h3>
      <div className="table-wrap">
        <table className="grid compact" aria-label={`${r.player.name} full line`}>
          <thead>
            <tr>
              <th scope="col">Stat</th>
              <th scope="col" className="num">Actual total</th>
              <th scope="col" className="num">Expected total</th>
              <th scope="col" className="num">Δ</th>
              <th scope="col" className="num">Actual / game</th>
              <th scope="col" className="num">Expected / game</th>
            </tr>
          </thead>
          <tbody>
            {DETAIL_KEYS.map(({ key, label }) => {
              const a = r.actual[key] ?? null
              const e = r.expected?.[key] ?? null
              const sign = key === 'TOV' ? -1 : 1
              const unscored = !isScored(key)
              return (
                <tr key={key} className={unscored ? 'unscored' : undefined}>
                  <th scope="row">
                    {label}
                    {key === 'TOV' && scoresTov && <span className="muted"> (lower is better)</span>}
                    {unscored && <span className="muted"> · not scored in this league</span>}
                  </th>
                  <td className="num">{cell(a, key)}</td>
                  <td className="num">{cell(e, key)}</td>
                  <td className={`num ${unscored ? 'muted' : a !== null && e !== null ? ((a - e) * sign > 0 ? 'pos' : (a - e) * sign < 0 ? 'neg' : '') : 'muted'}`}>{a !== null && e !== null ? fmtSigned(a - e, 1) : '—'}</td>
                  <td className="num">{cell(r.actual_per_game[key], key)}</td>
                  <td className="num">{cell(r.expected_per_game?.[key], key)}</td>
                </tr>
              )
            })}
            {(
              [
                ['FG', 'FGM', 'FGA', 'FG_PCT'],
                ['FT', 'FTM', 'FTA', 'FT_PCT'],
                ['3P', 'FG3M', 'FG3A', null],
              ] as const
            ).map(([label, mk, ak, pk]) => (
              <tr key={label}>
                <th scope="row">{label} (makes/attempts)</th>
                <td className="num">
                  {fmtNum(r.actual[mk], 0)}/{fmtNum(r.actual[ak], 0)}
                  {pk && r.actual[pk] !== null && r.actual[pk] !== undefined ? ` · ${pct1(r.actual[pk])}` : ''}
                </td>
                <td className="num">
                  {r.expected ? `${fmtNum(r.expected[mk], 0)}/${fmtNum(r.expected[ak], 0)}${pk && r.expected[pk] !== null && r.expected[pk] !== undefined ? ` · ${pct1(r.expected[pk])}` : ''}` : '—'}
                </td>
                <td className="num muted">{pk && r.actual[pk] !== null && r.actual[pk] !== undefined && r.expected?.[pk] !== null && r.expected?.[pk] !== undefined ? fmtSigned(((r.actual[pk] ?? 0) - (r.expected?.[pk] ?? 0)) * 100, 1) + ' pts' : '—'}</td>
                <td className="num">
                  {fmtNum(r.actual_per_game[mk], 1)}/{fmtNum(r.actual_per_game[ak], 1)}
                </td>
                <td className="num">{r.expected_per_game ? `${fmtNum(r.expected_per_game[mk], 1)}/${fmtNum(r.expected_per_game[ak], 1)}` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3 style={{ margin: '16px 0 6px' }}>Contribution by category (units)</h3>
      <div className="table-wrap">
        <table className="grid compact" aria-label={`${r.player.name} contribution by category`}>
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col" className="num">Actual</th>
              <th scope="col" className="num">Expected</th>
              <th scope="col" className="num">Δ</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(r.contribution_by_category).map(([k, v]) => {
              const e = r.expected_by_category?.[k] ?? null
              return (
                <tr key={k}>
                  <th scope="row">{k.replace('_PCT', '%').replace('FG3M', '3PM')}</th>
                  <td className="num">{fmtNum(v, 1)}</td>
                  <td className="num">{e === null ? '—' : fmtNum(e, 1)}</td>
                  <td className={`num ${e === null ? 'muted' : v - e > 0 ? 'pos' : v - e < 0 ? 'neg' : ''}`}>{e === null ? '—' : fmtSigned(v - e, 1)}</td>
                </tr>
              )
            })}
            <tr>
              <th scope="row">Total</th>
              <td className="num">
                <b>{fmtNum(r.contribution, 1)}</b>
              </td>
              <td className="num">{r.expected_contribution === null ? '—' : fmtNum(r.expected_contribution, 1)}</td>
              <td className="num">{r.over_expected === null ? '—' : fmtSigned(r.over_expected, 1)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="table-note">
        One unit is one standard deviation of per-game production across the league pool. FG% and FT% are shooting impact on the player's own attempts against the pool rate.{' '}
        {scoresTov ? 'Turnovers count against.' : 'Turnovers are not scored in this league and are not part of contribution.'}
      </p>
    </aside>
  )
}
