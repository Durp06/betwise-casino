<!-- Keep this PR short and focused. One coherent change per PR. -->

## What

<!-- One sentence: what does this PR do? -->

## Why

<!-- One paragraph: why does it need to happen now? Link the issue / spec / Slack thread. -->

## How to verify

<!-- Concrete steps the reviewer can run. Don't say "test the feature" — say "1) seat at a table, 2) deal, 3) confirm X appears in the modal." -->

- [ ] `python -m pytest backend/tests/ -v` passes locally
- [ ] `cd frontend && npm test -- --run` passes locally
- [ ] `cd frontend && npx tsc --noEmit` is clean
- [ ] If this touches the UI: opened it locally and confirmed it works in the browser, not just in tests

## Checklist

- [ ] No `datetime.utcnow()` — only `datetime.now(timezone.utc)` (see CLAUDE.md grader anti-pattern)
- [ ] No new `any` types in TypeScript
- [ ] No inline SQL in route handlers — helpers live at the bottom of the router file
- [ ] No new inline styles in React — Tailwind utilities only (dynamic values like `width: ${pct}%` excepted)
- [ ] Every fetch shows loading + error states
- [ ] User-facing strings go through `t()`
- [ ] If adding a new game: followed the "Adding a new game" walkthrough in CLAUDE.md

## Screenshots / recordings

<!-- Drop screenshots or a short loom for any UI-visible change. -->
