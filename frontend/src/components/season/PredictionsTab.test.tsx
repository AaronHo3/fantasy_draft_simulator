import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PredictionsResponse } from '../../api/types'
import { PredictionsTable } from './PredictionsTable'

const NAMES = { m01: 'Aaron', m02: 'Kurdi', m03: 'George' }

const body: PredictionsResponse = {
  ids: { draft_revision: 1, strategy_revision: 0, league_revision: 1, last_seq: 1, snapshot_id: 'x', projection_version: 'v', seed: 1 },
  predictions: [
    { period: 1, home_manager_id: 'm01', away_manager_id: 'm02', predicted_winner: 'm01', p_winner: 0.7, p_tie: 0.1, expected_home: 5.2, expected_away: 2.8, locked: true, predicted_at: '2026-10-19T04:00:00+00:00', actual_winner: 'm01', actual_cats: { m01: 5, m02: 3 }, correct: true },
    { period: 1, home_manager_id: 'm03', away_manager_id: null, predicted_winner: null, p_winner: null, p_tie: null, expected_home: null, expected_away: null, locked: true, predicted_at: '2026-10-19T04:00:00+00:00', actual_winner: null, actual_cats: null, correct: null },
    { period: 2, home_manager_id: 'm02', away_manager_id: 'm03', predicted_winner: 'm03', p_winner: 0.55, p_tie: 0.2, expected_home: 3.7, expected_away: 4.3, locked: false, predicted_at: '2026-10-25T04:00:00+00:00', actual_winner: null, actual_cats: null, correct: null },
  ],
  summary: { n_predicted: 2, n_decided: 1, n_correct: 1, hit_rate: 1, brier: 0.09, by_period: { '1': { n_decided: 1, n_correct: 1 } } },
}

describe('PredictionsTable', () => {
  it('lists every projected winner with its outcome and the running tally', () => {
    render(<PredictionsTable body={body} names={NAMES} userId="m01" />)
    expect(screen.getByTestId('predictions-summary')).toHaveTextContent('1 of 1 decided weeks correct')
    const rows = screen.getAllByTestId('prediction-row')
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveTextContent('Aaron')
    expect(rows[0]).toHaveTextContent('70%')
    expect(rows[0]).toHaveTextContent('correct')
    expect(rows[1]).toHaveTextContent('bye')
    expect(rows[2]).toHaveTextContent('pending')
    expect(rows[2]).toHaveTextContent('open')
  })
})
