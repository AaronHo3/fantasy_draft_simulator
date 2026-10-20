import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CategoryDef, FreeAgentView, PlayerView } from '../../api/types'
import { FreeAgentsTable } from './FreeAgentsTable'

const CATS: CategoryDef[] = [{ key: 'PTS', label: 'Points', higher_is_better: true, kind: 'counting', numerator: null, denominator: null }]

function player(id: string, name: string): PlayerView {
  return {
    player_id: id,
    name,
    team: 'BOS',
    primary_position: 'PG',
    eligible_positions: ['PG', 'G'],
    eligibility_verified: true,
    injury_status: null,
    adp: null,
    rank: null,
    projection_source: 'demo',
    per_game: {},
    per_game_sd: {},
    drafted_by: null,
    drafted_overall: null,
  } as PlayerView
}

function fa(id: string, name: string, flags: string[] = []): FreeAgentView {
  return { player: player(id, name), score: 1.5, z: { PTS: 0.4 }, best_drop: player('d1', 'Bench Guy'), drop_value: 0.2, swap_delta: 1.3, injury_status: flags.includes('out') ? 'OUT' : 'ACTIVE', percent_owned: 12.5, flags }
}

describe('FreeAgentsTable', () => {
  it('hides OUT players when the toggle is on', () => {
    render(<FreeAgentsTable items={[fa('a', 'Healthy Guy'), fa('b', 'Hurt Guy', ['out'])]} categories={CATS} onSelect={() => {}} />)
    expect(screen.getByText('Hurt Guy')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(/hide out/i))
    expect(screen.queryByText('Hurt Guy')).toBeNull()
    expect(screen.getByText('Healthy Guy')).toBeInTheDocument()
    expect(screen.getByText('Bench Guy')).toBeInTheDocument()
  })

  it('calls onSelect with the player id on row click', () => {
    const picked: string[] = []
    render(<FreeAgentsTable items={[fa('a', 'Healthy Guy')]} categories={CATS} onSelect={(id) => picked.push(id)} />)
    fireEvent.click(screen.getByText('Healthy Guy'))
    expect(picked).toEqual(['a'])
  })
})
