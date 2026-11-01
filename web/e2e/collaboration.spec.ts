import { expect, test } from '@playwright/test';

import { createStudy, signIn, uniqueTitle } from './helpers';

test('two users: live updates and the conflict dialog', async ({ browser }) => {
  const alice = await signIn(browser, 'Alice');
  const url = await createStudy(alice, uniqueTitle('Collaboration'));
  const bob = await signIn(browser, 'Bob');
  await bob.goto(url);
  await expect(bob.getByText('Live', { exact: true })).toBeVisible();

  // Alice starts editing; Bob saves first.
  await alice.getByLabel('Therapeutic area').fill('Respiratory (Alice)');
  await bob.getByLabel('Therapeutic area').fill('Respiratory (Bob)');
  await bob.getByRole('button', { name: 'Save details' }).click();

  // Alice is told, live, and warned her form is now stale.
  await expect(alice.getByText('bob@studyforge.dev updated study details')).toBeVisible();
  await expect(
    alice.getByText('Someone else saved this study while you were editing'),
  ).toBeVisible();

  // Saving shows yours vs theirs; Alice keeps hers.
  await alice.getByRole('button', { name: 'Save details' }).click();
  const dialog = alice.getByRole('dialog');
  await expect(dialog.getByText('Someone else changed this')).toBeVisible();
  await expect(dialog.getByText('Respiratory (Bob)')).toBeVisible();
  await dialog.getByRole('button', { name: 'Keep mine' }).click();

  // Bob's screen updates to Alice's value without a refresh.
  await expect(bob.getByLabel('Therapeutic area')).toHaveValue('Respiratory (Alice)');
});
