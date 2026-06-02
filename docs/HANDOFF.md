# BetWise Casino — Handoff (2026-05-28)

Use this doc to pick up where the last session left off — whether you're the next collaborator joining the project, a future-you starting a fresh Claude session, or Myles handing the codebase to teammates.

For ongoing conventions (code style, "how to add a new game", PR workflow), read `CLAUDE.md` and `CONTRIBUTING.md`. This file is the **session-state snapshot**, not the rulebook.

---

## Where we are right now

- **Production**: https://betwise-casino-production.up.railway.app (auto-deploys from `main`)
- **Repo**: `Durp06/betwise-casino` — branch protection on `main` (PR required, CI gates merge, squash-merge only, linear history)
- **`main` HEAD**: commit `1dba7a4` ("Security hardening: 7 CSO findings...") as of 2026-05-28
- **Test posture**: 172 backend tests (pytest-asyncio + in-memory SQLite), 14 frontend tests (Vitest + jsdom), `ruff check backend` clean, `npx tsc --noEmit` clean
- **CI**: `.github/workflows/ci.yml` — runs `ruff`, `pytest`, `tsc`, `vitest`, `npm run build` on every push and on PRs to main

---

## What shipped in the last session

Four squash-merged PRs landed on `main`, in this order:

| PR  | SHA       | Title                                                                    | Why                                                                 |
|-----|-----------|--------------------------------------------------------------------------|---------------------------------------------------------------------|
| #1  | `aee7561` | Sync main: Hand Review + multi-game scaffold + standards                 | brought main current — 25 commits squashed                          |
| #2  | `4d52a40` | Drill Mode: active-retrieval coaching for Chipy                          | toggle to make Chipy quiz instead of telling, with dealer-bust %    |
| #3  | `1a371d5` | Chipy redesign — hand-painted sprite sheet                               | swapped hand-coded SVG mascot for a Gemini-generated 4×4 spritesheet|
| #4  | `1dba7a4` | Security hardening: 7 CSO findings                                       | full CSO audit + remediation pass                                   |

### Feature shape

- **Hand Review** (PR #1): `GET /api/sessions/{id}/review` + `SessionReviewModal` — Chess.com-style move classification (best / good / inaccuracy / mistake / blunder) with EV-loss math. Backed by `backend/game/blackjack/review.py::classify_action`.
- **Drill Mode** (PR #2): `coachMode: "quick" | "drill"` toggle persisted to localStorage. Drill mode suppresses pre-play streaming and shows a quiz prompt; post-play narration now cites dealer-bust % from `backend/game/blackjack/odds.py`.
- **Chipy spritesheet** (PR #3): `frontend/src/assets/chipy/chipy-spritesheet.png` (2.2MB, Pillow-chroma-keyed to remove the checkerboard alpha-preview pixels). Component is a thin CSS-sprite renderer with Framer Motion idle bob; `Chipy` props shape unchanged so every caller still works.
- **Security hardening** (PR #4): 7 CSO findings closed in 5 commits — IDOR fix, slowapi rate limit on advice endpoints, race-condition lock on `/action`, JWT aud + iss validation, dev-bypass production guard, CORS wildcard startup guard, Dockerfile non-root user.

### Multi-game scaffold

`backend/game/` now uses a per-game subpackage layout. Blackjack lives at `backend/game/blackjack/`; the `backend/game/__init__.py` shim re-exports old import paths via `sys.modules.setdefault(...)` so historical `from backend.game.engine import X` still works. To add poker / baccarat: see CLAUDE.md "Adding a new game" — slot in `backend/game/<your_game>/` + register in `backend/game/registry.py`.

---

## Outstanding manual config (before next deploy fully takes effect)

Two of the security fixes ship dormant until env vars are set in Railway:

```bash
# In the linked Railway service — set these via `railway variables --set ...` or the dashboard
ENVIRONMENT=production
BETWISE_CORS_ORIGINS=https://betwise-casino-production.up.railway.app
BETWISE_ADVICE_RATE_LIMIT=10/minute   # optional; defaults to this if unset
```

- **`ENVIRONMENT=production`** is the kill switch for the dev-auth bypass. Without it, if anyone ever pastes `BETWISE_DEV_USER_ID` into Railway, all requests authenticate as that UUID. CSO Finding #7.
- **`BETWISE_CORS_ORIGINS`** must NOT contain `*`. The app refuses to boot if it does (CSO Finding #5).
- **`BETWISE_ADVICE_RATE_LIMIT`** controls the slowapi limit on `/api/advice/{id}` and `/pre`. Tighten if abuse appears.

Plus one outside Railway:

- **Anthropic dashboard** → Settings → Limits → set a project-level monthly spend cap. Defense-in-depth ceiling beyond the per-user rate limit.

---

## Setup for a new contributor / fresh machine

```bash
# 1. Clone
gh repo clone Durp06/betwise-casino
cd betwise-casino

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate                     # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest tests/ -v                 # 172+ tests, in-memory SQLite — no real DB

# 3. Frontend
cd ../frontend
npm install
npm test -- --run                          # 14 Vitest tests
npm run build                              # produces frontend/dist/

# 4. Run the whole app (from repo root)
cd ..
$env:BETWISE_DEV_USER_ID="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"   # PowerShell; bash: BETWISE_DEV_USER_ID=...
$env:BETWISE_TEST_DB_URL="sqlite+aiosqlite:///./dev.sqlite"
python -m uvicorn backend.main:app --reload --port 8000 --reload-dir backend
# In another terminal:
cd frontend
$env:VITE_API_PROXY_TARGET="http://localhost:8000"
npx vite --port 5173
# Open http://localhost:5173 — Vite proxies /api → localhost:8000
```

The dev-bypass UUID stands in for a Supabase JWT during local dev. Set `ENVIRONMENT=production` in Railway and that bypass is rejected with a 503 in prod (CSO #7 guard).

---

## Conventions cheat sheet

These are the rules CI enforces and reviewers block on. Full list in `CLAUDE.md`:

- All API routes prefixed `/api`.
- Cards: `{ suit: "hearts"|"diamonds"|"clubs"|"spades", value: "2"-"10"|"J"|"Q"|"K"|"A" }`.
- Monetary values are integers in fake cents (`$10.00 = 1000`). User starts at `100000` chips.
- Async SQLAlchemy everywhere. Pydantic v2 with `ConfigDict(from_attributes=True)`.
- Frontend: no `any`, Tailwind only, every fetch shows loading + error states, all UI strings through `t()`.
- **Never `datetime.utcnow()`** — always `datetime.now(timezone.utc)`. Grader anti-pattern.
- Per-router SQL helpers, no inlined raw SQL in handlers.
- Branch naming: `<area>/<short-kebab>` — `feat/`, `fix/`, `chore/`, `refactor/`, `docs/`, `test/`.
- Commit subjects: `<area>(scope): imperative summary`.

---

## Known limitations

- **Split returns 501.** Schema has implicit `UNIQUE(session_id, user_id)` on hands — splitting needs a migration to add `(session_id, user_id, hand_index)`. Tracked as future work; the basic-strategy engine already returns `"split"` correctly when applicable.
- **`pose` prop on `Chipy`** is currently a no-op since arm positions are baked into each sprite cell. Kept on the props for API stability + future per-pose sprite expansion.
- **Race condition test** for `/action` is structural (asserts `with_for_update` appears in `_take_action`) plus two behavioural double-deal tests, not a true concurrent-request test. Adequate for the in-memory SQLite harness but the production race fix is meaningful only in Postgres.
- **Chipy spritesheet** has no `pose="wave"` / `pose="thumbsup"` / `pose="point"` variants — only `expression` is mapped. Adding pose variants means generating + adding more sprite cells.

---

## Key decisions and the reasoning behind them

These are the moments where we picked one path over another. If you're tempted to revisit one of these, the context is here:

- **Polling over WebSockets** for multiplayer. 3-second `setInterval` against `GET /api/tables/{id}/state` — blackjack turns last ≥ 5s, so the staleness budget tolerates ~3s. WebSockets would add reconnect, session pinning, deploy draining — three problems we don't actually have.
- **Sprite sheet over SVG paths for Chipy.** Hand-coded SVG has a quality ceiling. Gemini-generated PNG sprites + Framer Motion bob hits the 1930s rubber-hose aesthetic we couldn't reach in path code.
- **Single big PR for security hardening** (PR #4) over five small PRs. The 5-agent parallel-worktree experiment failed (3 of 5 agents broke isolation), so all 7 fixes went into one branch + one PR with 5 commits. Squash-merged to a single commit on main.
- **Lean ruff ruleset** (`F` + `B` only). Stylistic rules (`E`, `I`, `UP`) are deferred until we do one project-wide formatting pass — turning them on now would force a 100+-fix change while feature work is in flight.
- **Branch protection: 0 required approvals** for now. Bump to 1 with `gh api -X PUT repos/Durp06/betwise-casino/branches/main/protection/required_pull_request_reviews -f required_approving_review_count=1` once teammates are actually active.
- **Local-only security reports.** `.gstack/security-reports/` is gitignored — sensitive findings + remediation plans stay off the public repo.

---

## Workflow used (and where it broke down)

Per `~/.claude/CLAUDE.md`, work goes through: **planner → tester → implementer → oracle-codex → verify**.

What worked: the Hand Review + Drill Mode features both went through this loop cleanly. Spec under `specs/`, failing tests written by the tester subagent, implementer made them pass, oracle reviewed.

What broke: the **oracle-codex Windows sandbox is fragile** — the codex CLI's PowerShell sandbox crashes mid-run on this machine. Documented in `~/.claude/projects/.../memory/feedback_oracle_windows.md`. When this happens, inspect `.git/.oracle-review-<sha>.md` directly before trusting the subagent's verdict. Real codex output is thousands of lines with a "OpenAI Codex" banner; fabricated verdicts are short markdown with no command-log evidence. Per-finding, do your own audit and write `.git/.oracle-reviewed-<sha>` manually as the documented escape hatch.

What broke worse: **the 5-agent parallel-worktree experiment for security fixes failed** (3 of 5 agents contaminated the main worktree by switching branches instead of staying in their isolated worktrees). Lesson: parallel-with-worktrees works for genuinely-independent diffs across non-overlapping files; for tightly-scoped fixes that touch shared files (`backend/main.py`, `backend/auth.py`), sequential in the main repo is faster and cleaner.

---

## What I'd do next if I were continuing

1. **Set the Railway env vars** (15 min including verifying the redeploy). See "Outstanding manual config" above.
2. **Invite collaborators** to `Durp06/betwise-casino` (Settings → Collaborators). Once they're active, bump branch protection to require 1 review.
3. **Mobile sweep**: the gold-tier rubric scores mobile readiness. Verify the table page renders cleanly at 375px viewport. Likely some Tailwind tweaks needed on the action bar + post-hand menu.
4. **Split implementation**: write the migration (`(session_id, user_id, hand_index)` unique constraint), update `_take_action` to handle split, write the multi-hand test scaffolding. Will surface schema choices about how to render split hands in the multiplayer felt.
5. **Per-pose sprite expansion** for the Chipy mascot — generate `wave` / `thumbsup` / `point` sprites and add to the cell map, so the lobby header and action-response moments can actually use the pose prop.
6. **Lessons / Drills page**: the Chess.com-of-blackjack framing has Hand Review and Drill Mode but no structured "Lessons" experience yet. Soft hands, splitting, doubling, insurance — each a small module that uses the existing strategy engine + Chipy explanation flow.

---

## Provenance

- Last session: 2026-05-21 → 2026-05-28 (multi-day, multiple context compactions)
- AI assistant: Claude Code (Opus 4.7)
- Auditor for security report: `/cso` skill (gstack)
- Mascot art: Google Gemini (Imagen 3)
- Original codebase + design: Myles Slyles (`@Durp06`)
