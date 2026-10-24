import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { LeagueConfig } from '../../api/types'
import { defaultLeague } from '../../lib/leagueDefaults'
import { ScoringEditor } from './ScoringEditor'

function Harness({ onChange }: { onChange: (l: LeagueConfig) => void }) {
  return <ScoringEditor league={defaultLeague()} onChange={onChange} />
}

describe('ScoringEditor categories', () => {
  it('lets a category be switched off and reports the new list', () => {
    const changes: LeagueConfig[] = []
    render(<Harness onChange={(l) => changes.push(l)} />)
    const tov = screen.getByRole('button', { name: /Turnovers/ })
    expect(tov).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(tov)
    expect(changes.at(-1)?.categories.map((c) => c.key)).toEqual(['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'FG_PCT', 'FT_PCT'])
  })

  it('offers an 8-cat preset that drops turnovers and a 9-cat preset that restores them', () => {
    const changes: LeagueConfig[] = []
    render(<Harness onChange={(l) => changes.push(l)} />)
    fireEvent.change(screen.getByLabelText(/Category preset/), { target: { value: 'eight' } })
    expect(changes.at(-1)?.categories.some((c) => c.key === 'TOV')).toBe(false)
    expect(changes.at(-1)?.categories).toHaveLength(8)
  })
})
