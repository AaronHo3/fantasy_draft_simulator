import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RosterMoveView } from '../../api/types'
import { makePlayer } from '../../test/seasonFixtures'
import { RosterMoves } from './RosterMoves'

const mv = (manager: string, name: string, kind: 'add' | 'drop', pid: string, trade = false): RosterMoveView => ({
  manager_id: manager.toLowerCase().replace(' ', ''),
  manager_name: manager,
  kind,
  player: makePlayer(pid, name, kind === 'add' ? 'NOP' : 'PHX'),
  effective_at: '2026-10-24T05:24:59+00:00',
  period: 1,
  source: 'espn:x',
  trade,
})

describe('RosterMoves', () => {
  it('groups this week’s adds and drops by team and marks trades', () => {
    render(
      <RosterMoves
        period={1}
        moves={[mv('Yang Lei', 'Yves Missi', 'add', 'a'), mv('Yang Lei', 'Oso Ighodaro', 'drop', 'b'), mv('Tim Wu', 'Keaton Wagler', 'add', 'c', true)]}
        userId="timwu"
      />,
    )
    const yang = screen.getByRole('group', { name: /Yang Lei/ })
    expect(within(yang).getByText('Yves Missi').closest('.move')).toHaveClass('add')
    expect(within(yang).getByText('Oso Ighodaro').closest('.move')).toHaveClass('drop')
    const tim = screen.getByRole('group', { name: /Tim Wu/ })
    expect(within(tim).getByText(/trade/i)).toBeInTheDocument()
    expect(tim).toHaveClass('mine')
  })

  it('says so when nobody moved', () => {
    render(<RosterMoves period={3} moves={[]} userId="x" />)
    expect(screen.getByText(/no roster moves in week 3/i)).toBeInTheDocument()
  })
})
