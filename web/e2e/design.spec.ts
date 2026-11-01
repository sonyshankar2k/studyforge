import { expect, test } from '@playwright/test';

import { createStudy, signIn, uniqueTitle } from './helpers';

test('eligibility criteria are numbered and can be reordered', async ({ browser }) => {
  const alice = await signIn(browser, 'Alice');
  await createStudy(alice, uniqueTitle('Eligibility'));
  await alice.getByRole('tab', { name: 'Eligibility' }).click();

  const inclusion = alice.locator('[data-category=inclusion]');
  for (const text of ['Adults aged 18 to 65', 'Diagnosed asthma', 'Non-smoker']) {
    await inclusion.getByLabel('Add inclusion criterion').fill(text);
    await inclusion.getByRole('button', { name: 'Add' }).click();
    await expect(inclusion.getByText(text)).toBeVisible();
  }

  // Keyboard-friendly reorder: move I3 up twice.
  await inclusion.getByRole('button', { name: 'Move I3 up' }).click();
  await inclusion.getByRole('button', { name: 'Move I2 up' }).click();

  await expect(inclusion.locator('.criterion')).toHaveText([
    /I1\s*Non-smoker/,
    /I2\s*Adults aged 18 to 65/,
    /I3\s*Diagnosed asthma/,
  ]);

  // The order is saved: it survives a reload.
  await alice.reload();
  await alice.getByRole('tab', { name: 'Eligibility' }).click();
  await expect(alice.locator('[data-category=inclusion] .criterion').first()).toContainText(
    'Non-smoker',
  );
});

test('schedule of activities: plan cells, and another user sees them live', async ({ browser }) => {
  const alice = await signIn(browser, 'Alice');
  const url = await createStudy(alice, uniqueTitle('Schedule'));
  await alice.getByRole('tab', { name: 'Schedule' }).click();

  for (const [name, day] of [
    ['Screening', '-14'],
    ['Week 4', '29'],
  ]) {
    await alice.getByRole('button', { name: 'Add visit' }).first().click();
    await alice.getByLabel('Visit name').fill(name);
    await alice.getByLabel('Study day').fill(day);
    await alice.locator('form.visit-form').getByRole('button', { name: 'Add visit' }).click();
    await expect(alice.getByRole('columnheader', { name: new RegExp(name) })).toBeVisible();
  }
  await alice.getByLabel('New activity').fill('Vital signs');
  await alice.getByRole('button', { name: 'Add activity' }).click();

  const bob = await signIn(browser, 'Bob');
  await bob.goto(url);
  await bob.getByRole('tab', { name: 'Schedule' }).click();
  const bobCell = bob.getByRole('checkbox', { name: 'Vital signs at Week 4' });
  await expect(bobCell).not.toBeChecked();

  await alice.getByRole('checkbox', { name: 'Vital signs at Week 4' }).check();
  await expect(alice.getByRole('checkbox', { name: 'Vital signs at Week 4' })).toBeChecked();

  // Bob's grid updates without a refresh.
  await expect(bobCell).toBeChecked();
  await expect(bob.getByText('alice@studyforge.dev updated the schedule')).toBeVisible();
});

test('export the design as USDM JSON', async ({ browser }) => {
  const alice = await signIn(browser, 'Alice');
  await alice.goto('/studies/1');
  const download = alice.waitForEvent('download');
  await alice.getByRole('button', { name: 'Export USDM' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('BREATHE-1-usdm.json');
});
