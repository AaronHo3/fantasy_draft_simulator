import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CategoryDef, MatchupPairView } from '../../api/types'
import { MatchupCard } from './MatchupCard'

const CATS: CategoryDef[] = [
  { key: 'PTS', label: 'Points', higher_is_better: true, kind: 'counting', numerator: null, denominator: null },
  { key: 'FT_PCT', label: 'FT%', higher_is_better: true, kind: 'ratio', numerator: 'FTM', denominator: 'FTA' },
]
const NAMES = { m01: 'Aaron', m02: 'Kurdi' }

function pair(over: Partial<MatchupPairView> = {}): MatchupPairView {
  return {
    period: 1,
    home_manager_id: 'm01',
    away_manager_id: 'm02',
    odds: {
      period: 1,
      manager_a: 'm01',
      manager_b: 'm02',
      expected_a: 5.2,
      expected_b: 2.8,
      p_win_a: 0.7,
      p_tie: 0.1,
      p_win_b: 0.2,
      cat_p_a: { PTS: 0.8, FT_PCT: 0.3 },
      modal_score: [5, 3],
      games_a: 32,
      games_b: 28,
      notes: ['Kristaps Porzingis is OUT / on IR: 0 games this week'],
    },
    ...over,
  }
}

describe('MatchupCard', () => {
  it('renders a bye week without odds', () => {
    render(<MatchupCard pair={pair({ away_manager_id: null, odds: null })} names={NAMES} categories={CATS} userId="m01" />)
    expect(screen.getByText(/bye week/i)).toBeInTheDocument()
    expect(screen.queryByTestId('cat-PTS')).toBeNull()
  })

  it('names the projected winner and shows both breakdowns', () => {
    render(<MatchupCard pair={pair()} names={NAMES} categories={CATS} userId="m01" />)
    expect(screen.getByTestId('projected-winner')).toHaveTextContent('Aaron')
    expect(screen.getByTestId('projected-winner')).toHaveTextContent('70%')
    expect(screen.getByTestId('cat-PTS')).toHaveClass('fav-a')
    expect(screen.getByTestId('cat-FT_PCT')).toHaveClass('fav-b')
    // winner row then loser row, each with the team's own chance
    expect(screen.getByTestId('cat-PTS-winner')).toHaveTextContent('80%')
    expect(screen.getByTestId('cat-PTS-loser')).toHaveTextContent('20%')
    expect(screen.getByTestId('cat-FT_PCT-winner')).toHaveTextContent('30%')
    expect(screen.getByTestId('cat-FT_PCT-loser')).toHaveTextContent('70%')
    expect(screen.getByTestId('user-matchup')).toBeInTheDocument()
    expect(screen.getByText(/Kurdi 20% · tie 10%/)).toBeInTheDocument()
    expect(screen.getByText(/avg categories 5\.2/)).toBeInTheDocument()
    expect(screen.getByText(/Porzingis/)).toBeInTheDocument()
  })

  it('reads the user as the away side when ESPN lists them away', () => {
    render(<MatchupCard pair={pair({ home_manager_id: 'm02', away_manager_id: 'm01', odds: { ...pair().odds!, manager_a: 'm02', manager_b: 'm01' } })} names={NAMES} categories={CATS} userId="m01" />)
    expect(screen.getByTestId('user-matchup')).toBeInTheDocument()
    expect(screen.getByRole('heading').textContent).toMatch(/Kurdi.*vs.*Aaron/)
  })

  it('projects the away side as winner when its week odds are higher', () => {
    const o = { ...pair().odds!, p_win_a: 0.2, p_win_b: 0.7 }
    render(<MatchupCard pair={pair({ odds: o })} names={NAMES} categories={CATS} userId="m01" />)
    expect(screen.getByTestId('projected-winner')).toHaveTextContent('Kurdi')
    expect(screen.getByTestId('cat-PTS-winner')).toHaveTextContent('20%')
  })
})
