import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Explainer } from './Explainer'

describe('Explainer', () => {
  it('states the formulas and the league-specific unit sizes', () => {
    render(<Explainer unitSizes={{ PTS: 5.17, BLK: 0.3, FG_PCT: 0.37 }} benchmarkRates={{ FG_PCT: 0.477, FT_PCT: 0.802 }} categories={[{ key: 'PTS', label: 'Points' }, { key: 'BLK', label: 'Blocks' }, { key: 'FG_PCT', label: 'FG%' }] as never} />)
    fireEvent.click(screen.getByTestId('explainer-toggle'))
    expect(screen.getByText(/5\.2 points per game/i)).toBeInTheDocument()
    expect(screen.getByText(/0\.30 blocks per game/i)).toBeInTheDocument()
    expect(screen.getByText(/47\.7%/)).toBeInTheDocument()
    expect(screen.getByText(/× games/i)).toBeInTheDocument()
  })
})
