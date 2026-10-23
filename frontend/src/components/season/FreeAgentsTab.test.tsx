import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSeasonStore } from '../../store/seasonStore'
import { makeFreeAgent as fa, makeOverview } from '../../test/seasonFixtures'
import { FreeAgentsTab } from './FreeAgentsTab'

const overview = makeOverview()

describe('FreeAgentsTab', () => {
  beforeEach(() => {
    useSeasonStore.setState({
      overview,
      freeAgents: { ids: overview.ids, items: [fa('a', 'Healthy Guy'), fa('b', 'Hurt Guy', ['out'])], synced_at: null },
      faStatus: 'ready',
      loadFreeAgents: async () => {},
    })
  })

  it('hides OUT players by default, shows them on demand, and explains the selected swap', () => {
    render(<FreeAgentsTab sessionId="sess" />)
    expect(screen.queryByText('Hurt Guy')).toBeNull()
    const panel = screen.getByTestId('swap-panel')
    expect(within(panel).getByText('Healthy Guy')).toBeInTheDocument()
    expect(within(panel).getByText('Bench Guy')).toBeInTheDocument()
    expect(within(panel).getByText('+1.30')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(/hide out/i))
    const hurt = screen.getByText('Hurt Guy')
    expect(hurt).toBeInTheDocument()
    fireEvent.click(hurt.closest('tr')!.querySelector('td')!)
    expect(within(screen.getByTestId('swap-panel')).getByText('Hurt Guy')).toBeInTheDocument()
  })
})
