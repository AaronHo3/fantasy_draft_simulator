import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Tooltip } from './Tooltip'

describe('Tooltip', () => {
  it('shows its content on hover and on keyboard focus, and hides on leave', () => {
    render(
      <Tooltip content="Exact value: 12.3 units">
        <button type="button">12.3</button>
      </Tooltip>,
    )
    expect(screen.queryByRole('tooltip')).toBeNull()
    fireEvent.mouseEnter(screen.getByRole('button'))
    expect(screen.getByRole('tooltip')).toHaveTextContent('12.3 units')
    fireEvent.mouseLeave(screen.getByRole('button'))
    expect(screen.queryByRole('tooltip')).toBeNull()
    fireEvent.focus(screen.getByRole('button'))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    expect(screen.getByRole('button')).toHaveAttribute('aria-describedby', screen.getByRole('tooltip').id)
  })
})
