import { expect, test } from '@playwright/test';

import { createStudy, signIn, uniqueTitle } from './helpers';

// Relative to web/, where `npm run e2e` runs.
const SAMPLE = '../samples/BREATHE-2_protocol_synopsis.pdf';

test('upload a protocol, review what the AI found, add it to the study', async ({ browser }) => {
  const alice = await signIn(browser, 'Alice');
  await createStudy(alice, uniqueTitle('Digitize'));

  await alice.getByRole('tab', { name: 'AI digitize' }).click();
  await alice.locator('input[type=file]').setInputFiles(SAMPLE);
  await alice.getByRole('button', { name: 'Start' }).click();

  const job = alice.locator('.job').first();
  await expect(job.getByText('Found 3 arms and 4 objectives')).toBeVisible({ timeout: 45_000 });

  await job.getByRole('button', { name: 'Review results' }).click();
  // Untick the exploratory objective, add the rest.
  await job.getByRole('checkbox', { name: /Explore the effect of SF-202/ }).uncheck();
  await job.getByRole('button', { name: 'Add 6 selected to the study' }).click();
  await expect(job.getByText('Added to the study')).toBeVisible();

  await alice.getByRole('tab', { name: 'Design' }).click();
  const arms = alice.getByRole('region', { name: 'Arms' }).locator('.item-title');
  await expect(arms).toHaveText([
    /SF-202 20 mg once daily/,
    /Active comparator fluticasone/,
    /Matching placebo once daily/,
  ]);
  const objectives = alice.getByRole('region', { name: 'Objectives & endpoints' });
  await expect(objectives.locator('.item')).toHaveCount(3);
  await expect(objectives.getByText('Explore the effect of SF-202')).toHaveCount(0);
});
