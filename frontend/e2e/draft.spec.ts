import { expect, test, type Page } from '@playwright/test'

// Full draft loop on the synthetic demo snapshot: setup -> confirm format -> five opponent picks via the
// picker -> user on the clock -> draft the highlighted player -> undo -> reload -> state restored.

async function waitSaved(page: Page) {
  await expect(page.getByTestId('top-save-status')).toHaveText('saved')
}

async function pickTopAvailableViaKeyboard(page: Page): Promise<{ id: string; name: string }> {
  const onClockBefore = await page.getByTestId('top-on-clock').textContent()
  // Fresh results for the current revision: wait until the first row is available.
  await expect(page.locator('[data-testid="picker-results"]')).toHaveAttribute('aria-busy', 'false')
  await expect(page.locator('[data-testid="picker-row"][data-drafted="false"]').first()).toBeVisible()
  await page.locator('body').press('/')
  await expect(page.getByTestId('picker-search')).toBeFocused()
  await page.getByTestId('picker-search').press('Enter')
  const dialog = page.getByTestId('confirm-pick-dialog')
  await expect(dialog).toBeVisible()
  const nameEl = dialog.getByTestId('confirm-pick-player')
  const id = (await nameEl.getAttribute('data-player-id')) ?? ''
  const name = (await nameEl.textContent()) ?? ''
  expect(id).not.toBe('')
  // The manager defaults to whoever is on the clock.
  const selected = await dialog.getByTestId('confirm-pick-manager').inputValue()
  expect(selected).toMatch(/^m\d\d$/)
  await page.getByTestId('picker-search').press('Enter')
  await expect(dialog).toBeHidden()
  await expect(page.getByTestId('top-on-clock')).not.toHaveText(onClockBefore ?? '')
  await waitSaved(page)
  return { id, name }
}

test('setup, five opponent picks, recommendation excludes drafted, draft, undo, reload', async ({ page }) => {
  page.on('dialog', (d) => void d.accept())
  await page.goto('/')

  // --- setup on demo data ---------------------------------------------------------------
  await expect(page.getByTestId('setup-demo-badge')).toBeVisible()
  await page.getByTestId('setup-league-name').fill('E2E demo league')
  await expect(page.getByTestId('setup-manager-count')).toHaveValue('12')
  await page.getByTestId('setup-confirm-format').check()
  await page.getByTestId('setup-create').click()

  await expect(page).toHaveURL(/\?session=[a-z0-9]+#\/draft/)
  const sessionUrl = page.url()
  await expect(page.getByTestId('top-format')).toHaveText('confirmed')
  await expect(page.getByTestId('format-warning')).toHaveCount(0)
  await expect(page.getByTestId('top-on-clock')).toHaveText('Team 1')
  await expect(page.getByTestId('top-picks-until')).toHaveText('5')
  await expect(page.getByTestId('rec-name')).toBeVisible()

  // --- five opponent picks through the picker --------------------------------------------
  const drafted: { id: string; name: string }[] = []
  for (let i = 0; i < 5; i += 1) drafted.push(await pickTopAvailableViaKeyboard(page))
  expect(new Set(drafted.map((d) => d.id)).size).toBe(5)

  await expect(page.getByTestId('top-on-clock')).toHaveText('Team 6 (you)')
  await expect(page.getByTestId('top-picks-until')).toHaveText('0')
  await expect(page.getByTestId('top-round')).toHaveText('1')
  await expect(page.getByTestId('top-overall')).toContainText('6 /')

  // --- highlighted recommendation and shortlist exclude drafted players --------------------
  const recName = page.getByTestId('rec-name')
  await expect(recName).toBeVisible()
  await expect(page.getByTestId('rec-updating')).toHaveCount(0)
  const highlightedId = (await recName.getAttribute('data-player-id')) ?? ''
  expect(highlightedId).not.toBe('')
  const draftedIds = new Set(drafted.map((d) => d.id))
  expect(draftedIds.has(highlightedId)).toBe(false)
  const shortlistIds = await page.locator('[data-testid="shortlist-row"]').evaluateAll((rows) => rows.map((r) => r.getAttribute('data-player-id')))
  expect(shortlistIds.length).toBeGreaterThan(5)
  for (const id of shortlistIds) expect(draftedIds.has(id ?? '')).toBe(false)
  // Drafted players are hidden by the default "available" filter and greyed when shown.
  await expect(page.locator(`[data-testid="picker-row"][data-player-id="${drafted[0].id}"]`)).toHaveCount(0)
  await page.getByTestId('picker-availability').selectOption('all')
  await expect(page.locator(`[data-testid="picker-row"][data-player-id="${drafted[0].id}"]`)).toHaveAttribute('data-drafted', 'true')
  await expect(page.locator(`[data-testid="picker-row"][data-player-id="${drafted[0].id}"]`)).toContainText('drafted by Team 1 at #1')

  // --- draft the highlighted player ---------------------------------------------------------
  await expect(page.getByTestId('rec-draft')).toBeEnabled()
  await page.getByTestId('rec-draft').click()
  await expect(page.getByTestId('top-on-clock')).toHaveText('Team 7')
  await waitSaved(page)
  await expect(page.getByTestId('rec-updating')).toHaveCount(0)
  await expect(page.locator(`[data-testid="shortlist-row"][data-player-id="${highlightedId}"]`)).toHaveCount(0)
  await expect(page.locator('[data-testid="recent-pick"][data-overall="6"]')).toBeVisible()
  await page.getByTestId('tab-board').click()
  await expect(page.locator(`[data-testid="board-cell-6"]`)).toHaveAttribute('data-filled', 'true')
  await expect(page.getByTestId('rec-draft')).toBeDisabled()

  // --- undo ---------------------------------------------------------------------------------
  await page.getByTestId('board-undo').click()
  await expect(page.getByTestId('top-on-clock')).toHaveText('Team 6 (you)')
  await waitSaved(page)
  await expect(page.locator('[data-testid="board-cell-6"]')).toHaveAttribute('data-filled', 'false')
  await expect(page.getByTestId('rec-updating')).toHaveCount(0)
  await expect(page.locator(`[data-testid="shortlist-row"][data-player-id="${highlightedId}"]`)).toHaveCount(1)

  // --- reload restores the session from the URL -----------------------------------------------
  await page.reload()
  await expect(page).toHaveURL(sessionUrl)
  await expect(page.getByTestId('top-on-clock')).toHaveText('Team 6 (you)')
  await expect(page.getByTestId('top-picks-until')).toHaveText('0')
  await expect(page.getByTestId('top-format')).toHaveText('confirmed')
  await page.getByTestId('tab-board').click()
  await expect(page.locator('[data-testid^="board-cell-"][data-filled="true"]')).toHaveCount(5)
  await page.getByTestId('picker-availability').selectOption('all')
  for (const d of drafted) {
    await expect(page.locator(`[data-testid="picker-row"][data-player-id="${d.id}"]`)).toHaveAttribute('data-drafted', 'true')
  }
  await expect(page.getByTestId('rec-name')).toBeVisible()
  await expect(page.getByTestId('rec-updating')).toHaveCount(0)
  expect(draftedIds.has((await page.getByTestId('rec-name').getAttribute('data-player-id')) ?? '')).toBe(false)
})
