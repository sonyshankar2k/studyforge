import { expect, test } from '@playwright/test';

test('a signed-out visitor is sent to sign in, then back to the page they wanted', async ({
  page,
}) => {
  await page.goto('/studies/1');
  await expect(page).toHaveURL(/\/login\?returnUrl=%2Fstudies%2F1/);

  await page.getByLabel('Email').fill('alice@studyforge.dev');
  await page.getByLabel('Password', { exact: true }).fill('wrong-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toHaveText('Incorrect email or password.');

  await page.getByLabel('Password', { exact: true }).fill('studyforge');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/studies\/1$/);
});

test('signing out returns to the sign-in page', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Carol', exact: true }).click();
  await page.getByRole('button', { name: 'Carol' }).first().click(); // user menu
  await page.getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { name: 'Sign in to StudyForge' })).toBeVisible();
});
