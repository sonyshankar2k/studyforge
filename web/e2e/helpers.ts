import { Browser, Page, expect } from '@playwright/test';

export type DemoUser = 'Alice' | 'Bob' | 'Carol';

/** Sign in with a demo account, in its own browser context (its own session). */
export async function signIn(browser: Browser, user: DemoUser): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('/login');
  await page.getByRole('button', { name: user, exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Studies' })).toBeVisible();
  return page;
}

/** Create a fresh study through the UI so every test starts from a clean design. */
export async function createStudy(page: Page, title: string): Promise<string> {
  await page.goto('/');
  await page.getByRole('button', { name: 'New study' }).click();
  await page.getByLabel('Title').fill(title);
  await page.getByRole('button', { name: 'Create study' }).click();
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
  await expect(page.getByText('Live', { exact: true })).toBeVisible();
  return page.url();
}

export function uniqueTitle(prefix: string): string {
  return `${prefix} ${Date.now().toString(36)}`;
}
