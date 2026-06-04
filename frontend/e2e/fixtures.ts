import { test as base, expect } from "@playwright/test";

/**
 * Shared e2e fixtures.
 *
 * The app has a couple of *raw CSS* animations (e.g. the `.wobble` lobby/table
 * cards) that loop forever. framer-motion respects reduced-motion (handled in
 * playwright.config.ts), but CSS keyframes don't, so a perpetually-wobbling card
 * never satisfies Playwright's "element is stable" actionability gate and clicks
 * time out. We inject a stylesheet on every document that flattens all CSS
 * animations + transitions so elements settle instantly. This is e2e-only — the
 * app ships unchanged.
 */
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.addInitScript(() => {
      const css = `*, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
        scroll-behavior: auto !important;
      }`;
      const inject = () => {
        const style = document.createElement("style");
        style.setAttribute("data-e2e-no-motion", "");
        style.textContent = css;
        document.head.appendChild(style);
      };
      if (document.head) inject();
      else document.addEventListener("DOMContentLoaded", inject);
    });
    await use(page);
  },
});

export { expect };
