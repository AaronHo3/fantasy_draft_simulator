import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChartFrame } from './ChartFrame'

describe('ChartFrame', () => {
  it('renders the title, legend and children when data is available', () => {
    render(
      <ChartFrame title="Contribution" legend={[{ label: 'Actual', swatch: 'actual' }, { label: 'Expected', swatch: 'projected' }]}>
        <svg data-testid="chart" />
      </ChartFrame>,
    )
    expect(screen.getByRole('region', { name: 'Contribution' })).toBeInTheDocument()
    expect(screen.getByTestId('chart')).toBeInTheDocument()
    expect(screen.getByText('Expected')).toBeInTheDocument()
  })

  it('shows an unavailable note instead of the chart when told what is missing', () => {
    render(
      <ChartFrame title="Trend" unavailable="Needs per-week history; the performers endpoint returns one scope at a time.">
        <svg data-testid="chart" />
      </ChartFrame>,
    )
    expect(screen.queryByTestId('chart')).toBeNull()
    expect(screen.getByText(/one scope at a time/)).toBeInTheDocument()
  })
})
