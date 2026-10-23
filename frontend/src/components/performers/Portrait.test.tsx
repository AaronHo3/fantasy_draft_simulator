import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Portrait, portraitUrl } from './Portrait'

describe('Portrait', () => {
  it('uses the ESPN headshot for a player with an ESPN id and falls back to initials when it fails', () => {
    expect(portraitUrl(1234)).toBe('https://a.espncdn.com/i/headshots/nba/players/full/1234.png')
    expect(portraitUrl(null)).toBeNull()
    render(<Portrait name="Jalen Suggs" espnId={1234} team="ORL" />)
    const img = screen.getByRole('img', { name: /Jalen Suggs/ })
    expect(img).toHaveAttribute('src', portraitUrl(1234)!)
    fireEvent.error(img)
    expect(document.querySelector('img')).toBeNull()
    expect(screen.getByTestId('portrait-fallback')).toHaveTextContent('JS')
  })

  it('renders initials straight away without an ESPN id', () => {
    render(<Portrait name="Two Way Guy" espnId={null} team={null} />)
    expect(screen.getByTestId('portrait-fallback')).toHaveTextContent('TG')
  })
})
