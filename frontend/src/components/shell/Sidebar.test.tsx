import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Sidebar } from './Sidebar'

const base = {
  route: 'draft' as const,
  sessionId: 'abc123',
  sessionName: '1000T Fantasy League',
  isComplete: false,
  leagueName: null,
  syncedAt: null,
  isDemo: false,
}

describe('Sidebar', () => {
  it('hides in-season pages until the draft is complete and marks the current page', () => {
    render(<Sidebar {...base} />)
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: /Draft/ })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).queryByRole('link', { name: /Season/ })).toBeNull()
    expect(within(nav).queryByRole('link', { name: /Performers/ })).toBeNull()
  })

  it('shows every page plus the league context once the draft is complete and linked', () => {
    render(<Sidebar {...base} route="season" isComplete leagueName="1000Thieves" syncedAt="2026-10-23T08:50:57+00:00" />)
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: /Season/ })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: /Performers/ })).toBeInTheDocument()
    const ctx = screen.getByRole('complementary', { name: 'Session context' })
    expect(ctx).toHaveTextContent('1000Thieves')
    expect(ctx).toHaveTextContent('1000T Fantasy League')
  })

  it('labels synthetic data loudly', () => {
    render(<Sidebar {...base} isDemo />)
    expect(screen.getByText(/demo data/i)).toBeInTheDocument()
  })
})
