import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import type { MatchupPairView, SeasonOverview } from '../../api/types'
import { useSeasonStore } from '../../store/seasonStore'
import { MatchupsTab } from './MatchupsTab'

function odds(a: string, b: string, pa: number) {
  return { period: 1, manager_a: a, manager_b: b, expected_a: 5, expected_b: 3, p_win_a: pa, p_tie: 0.1, p_win_b: 0.9 - pa, cat_p_a: { PTS: 0.6 }, modal_score: [5, 3], games_a: 30, games_b: 30, notes: [] }
}
const pairs: MatchupPairView[] = [
  { period: 1, home_manager_id: 'm01', away_manager_id: 'm02', odds: odds('m01', 'm02', 0.7) },
  { period: 1, home_manager_id: 'm03', away_manager_id: 'm04', odds: odds('m03', 'm04', 0.3) },
  { period: 1, home_manager_id: 'm05', away_manager_id: null, odds: null },
]
const overview: SeasonOverview = {
  ids: { draft_revision: 1, strategy_revision: 0, league_revision: 1, last_seq: 1, snapshot_id: 'x', projection_version: 'v', seed: 1 },
  linked: true,
  league_name: 'L',
  synced_at: null,
  summary: null,
  warnings: [],
  current_period: 1,
  league_categories: [{ key: 'PTS', label: 'Points', higher_is_better: true, kind: 'counting', numerator: null, denominator: null }],
  manager_names: { m01: 'Aaron', m02: 'Yang', m03: 'Kurdi', m04: 'George', m05: 'Andrew' },
  power: [],
  movement: {},
  matchups: pairs,
  user_matchup: pairs[0],
}

describe('MatchupsTab', () => {
  beforeEach(() => useSeasonStore.setState({ overview, period: 1 }))

  it('features my matchup by default and swaps in the card I click', () => {
    render(<MatchupsTab sessionId="sess" userId="m01" />)
    const featured = screen.getByTestId('featured-matchup')
    expect(within(featured).getByRole('heading').textContent).toMatch(/Aaron.*vs.*Yang/)
    fireEvent.click(screen.getByRole('button', { name: /Kurdi vs George/ }))
    expect(within(screen.getByTestId('featured-matchup')).getByRole('heading').textContent).toMatch(/Kurdi.*vs.*George/)
    // my own card is now in the grid, still marked as mine, and one click brings it back
    const grid = screen.getByTestId('other-matchups')
    expect(within(grid).getByTestId('user-matchup')).toBeInTheDocument()
    fireEvent.click(within(grid).getByRole('button', { name: /Aaron.*vs.*Yang/ }))
    expect(within(screen.getByTestId('featured-matchup')).getByRole('heading').textContent).toMatch(/Aaron.*vs.*Yang/)
  })

  it('can feature a bye card too', () => {
    render(<MatchupsTab sessionId="sess" userId="m01" />)
    fireEvent.click(screen.getByRole('button', { name: /Andrew/ }))
    expect(screen.getByTestId('featured-matchup')).toHaveTextContent(/Bye week/)
  })
})
