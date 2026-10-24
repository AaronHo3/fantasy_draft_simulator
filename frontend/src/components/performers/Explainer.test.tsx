import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CategoryDef } from '../../api/types'
import { Explainer } from './Explainer'

const CATS = [
  { key: 'PTS', label: 'Points', higher_is_better: true },
  { key: 'BLK', label: 'Blocks', higher_is_better: true },
  { key: 'FG_PCT', label: 'FG%', higher_is_better: true },
] as unknown as CategoryDef[]

describe('Explainer', () => {
  it('states the formulas and the league-specific unit sizes', () => {
    render(<Explainer unitSizes={{ PTS: 5.17, BLK: 0.3, FG_PCT: 0.37 }} benchmarkRates={{ FG_PCT: 0.477, FT_PCT: 0.802 }} categories={CATS} />)
    fireEvent.click(screen.getByTestId('explainer-toggle'))
    expect(screen.getByText(/5\.2 points per game/i)).toBeInTheDocument()
    expect(screen.getByText(/0\.30 blocks per game/i)).toBeInTheDocument()
    expect(screen.getByText(/47\.7%/)).toBeInTheDocument()
    expect(screen.getByText(/× games/i)).toBeInTheDocument()
  })

  it('says turnovers are not scored when the league has no TOV category, and counts them only when it does', () => {
    const { unmount } = render(<Explainer unitSizes={{ PTS: 5 }} benchmarkRates={{ FG_PCT: 0.47, FT_PCT: 0.8 }} categories={CATS} />)
    fireEvent.click(screen.getByTestId('explainer-toggle'))
    expect(screen.getByText(/turnovers are not a scoring category in this league/i)).toBeInTheDocument()
    expect(screen.queryByText(/turnovers count against/i)).toBeNull()
    unmount()
    render(<Explainer unitSizes={{ PTS: 5, TOV: 0.8 }} benchmarkRates={{ FG_PCT: 0.47, FT_PCT: 0.8 }} categories={[...CATS, { key: 'TOV', label: 'Turnovers', higher_is_better: false } as unknown as CategoryDef]} />)
    fireEvent.click(screen.getByTestId('explainer-toggle'))
    expect(screen.getByText(/turnovers count against/i)).toBeInTheDocument()
  })
})
