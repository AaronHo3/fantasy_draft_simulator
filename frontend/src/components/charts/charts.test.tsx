import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BarList } from './BarList'
import { Diverging } from './Diverging'
import { Heatmap } from './Heatmap'
import { Scatter } from './Scatter'

describe('BarList', () => {
  it('draws one bar per row with the exact value and calls back on click', () => {
    const onSelect = vi.fn()
    render(
      <BarList
        rows={[
          { id: 'a', label: 'Chet Holmgren', value: 60.2, secondary: 40.3, color: '#007AC1' },
          { id: 'b', label: 'Tyrese Maxey', value: 57.3, secondary: null, color: '#006BB6' },
        ]}
        format={(v) => v.toFixed(1)}
        unit="units"
        onSelect={onSelect}
        selectedId="b"
      />,
    )
    expect(screen.getAllByRole('button')).toHaveLength(2)
    expect(screen.getByText('60.2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Tyrese Maxey/ })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: /Chet Holmgren/ }))
    expect(onSelect).toHaveBeenCalledWith('a')
  })
})

describe('Diverging', () => {
  it('places positive and negative values on opposite sides of zero', () => {
    render(<Diverging rows={[{ id: 'a', label: 'Over', value: 4 }, { id: 'b', label: 'Under', value: -2 }]} format={(v) => v.toFixed(1)} unit="units" />)
    const over = screen.getByTestId('diverging-bar-a')
    const under = screen.getByTestId('diverging-bar-b')
    expect(over).toHaveAttribute('data-sign', 'positive')
    expect(under).toHaveAttribute('data-sign', 'negative')
    expect(screen.getByText('+4.0')).toBeInTheDocument()
    expect(screen.getByText('−2.0')).toBeInTheDocument()
  })
})

describe('Scatter', () => {
  it('renders one point per row and an equality line, skipping rows without both values', () => {
    render(
      <Scatter
        points={[
          { id: 'a', label: 'A', x: 10, y: 12 },
          { id: 'b', label: 'B', x: 5, y: null },
        ]}
        xLabel="Expected"
        yLabel="Actual"
        format={(v) => v.toFixed(0)}
      />,
    )
    expect(screen.getAllByTestId('scatter-point')).toHaveLength(1)
    expect(screen.getByTestId('equality-line')).toBeInTheDocument()
  })
})

describe('Heatmap', () => {
  it('writes the value into every cell so colour is never the only signal', () => {
    render(
      <Heatmap
        rows={[{ id: 'm1', label: 'Aaron' }]}
        columns={[{ key: 'PTS', label: 'Points' }, { key: 'REB', label: 'Rebounds' }]}
        value={(_r, c) => (c === 'PTS' ? 0.81 : null)}
        format={(v) => `${Math.round(v * 100)}%`}
        tone={(v) => (v >= 0.6 ? 'good' : v <= 0.4 ? 'bad' : 'even')}
        scaleNote="Chance to win the category against the league-average opponent."
        caption="Power heatmap"
      />,
    )
    expect(screen.getByText('81%')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText(/league-average opponent/)).toBeInTheDocument()
  })
})
