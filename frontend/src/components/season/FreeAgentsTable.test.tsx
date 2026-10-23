import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CategoryDef } from '../../api/types'
import { makeFreeAgent as fa } from '../../test/seasonFixtures'
import { FreeAgentsTable } from './FreeAgentsTable'

const CATS: CategoryDef[] = [{ key: 'PTS', label: 'Points', higher_is_better: true, kind: 'counting', numerator: null, denominator: null }]

describe('FreeAgentsTable', () => {
  it('marks OUT players and shows each row’s best drop', () => {
    render(<FreeAgentsTable items={[fa('a', 'Healthy Guy'), fa('b', 'Hurt Guy', ['out'])]} categories={CATS} onSelect={() => {}} />)
    expect(screen.getByText('Hurt Guy').closest('tr')).toHaveClass('drafted')
    expect(screen.getByText('OUT')).toBeInTheDocument()
    expect(screen.getAllByText('Bench Guy')).toHaveLength(2)
  })

  it('selects on row or name click, opens details from the details button, and marks the selected row', () => {
    const picked: string[] = []
    const opened: string[] = []
    render(<FreeAgentsTable items={[fa('a', 'Healthy Guy'), fa('b', 'Other Guy')]} categories={CATS} selectedId="b" onSelect={(id) => picked.push(id)} onOpen={(id) => opened.push(id)} />)
    expect(screen.getByText('Other Guy').closest('tr')).toHaveClass('selected')
    fireEvent.click(screen.getByText('Other Guy').closest('tr')!.querySelector('td')!)
    fireEvent.click(screen.getByText('Healthy Guy'))
    fireEvent.click(screen.getByRole('button', { name: 'Details for Healthy Guy' }))
    expect(picked).toEqual(['b', 'a'])
    expect(opened).toEqual(['a'])
  })
})
