# Contributing to BetWise Casino

Welcome. This file is the short version — read [`CLAUDE.md`](./CLAUDE.md) for the binding code conventions and the "Adding a new game" walkthrough.

## Local setup

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v        # 118+ tests, all in-memory SQLite — no real DB needed

# Frontend
cd ../frontend
npm install
npm test -- --run                  # Vitest
npm run dev                        # localhost:5173, /api proxies to localhost:8000

# Run the whole app — from the REPO ROOT (not from backend/).
# The `backend.main:app` import path needs the project root on sys.path,
# which only works from the root directory.
cd ..   # if you're inside frontend/ from the step above
$env:BETWISE_DEV_USER_ID="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"   # PowerShell; bash: BETWISE_DEV_USER_ID=...
$env:BETWISE_TEST_DB_URL="sqlite+aiosqlite:///./dev.sqlite"
python -m uvicorn backend.main:app --reload --port 8000 --reload-dir backend
# Open http://localhost:5173 (Vite dev) — /api proxies to localhost:8000
```

The `BETWISE_DEV_USER_ID` bypass makes the backend treat every request as the same dev user — convenient for local dev, **NEVER set in production**.

## Branch + PR workflow

1. **Branch off `main`.** Name: `<area>/<short-kebab-summary>` — e.g. `feat/poker-engine`, `fix/dealer-hole-card-leak`, `chore/upgrade-pydantic`.
2. **One coherent change per PR.** Refactors, formatting passes, and feature work go in separate PRs.
3. **Write tests first.** Acceptance criteria → failing test → implementation that makes it pass. The `tester` and `implementer` subagents are configured for this loop; see `~/.claude/CLAUDE.md` if you use Claude Code.
4. **Open the PR against `main`.** Fill out the template. Link the spec or issue.
5. **CI must be green** before review. See [`.github/workflows/ci.yml`](./.github/workflows/ci.yml).
6. **At least one approval** from a non-author teammate. (For solo work, the oracle-codex review from CLAUDE.md's workflow counts.)
7. **Squash-merge.** Linear history. Delete the branch after merge.

## What CI checks

- Backend: `ruff check` + `python -m pytest tests/ -v`
- Frontend: `npx tsc --noEmit` + `npm test -- --run` + `npm run build`

A red CI is a blocking review comment. Don't merge around it.

## Where the code lives

| Concern | Location |
|---|---|
| FastAPI routes | `backend/routers/*.py` — thin handlers at the top, SQL helpers prefixed `_` at the bottom |
| SQLAlchemy models | `backend/models.py` — single file, `Mapped[]` typed columns |
| Pydantic schemas | `backend/schemas.py` — single file, `ConfigDict(from_attributes=True)` |
| Game logic per game | `backend/game/<game_name>/` — see CLAUDE.md "Adding a new game" |
| Cross-game registry | `backend/game/registry.py` |
| Tests | `backend/tests/` (pytest-asyncio, in-memory SQLite) and `frontend/tests/` (Vitest + jsdom + MSW) |
| Frontend pages | `frontend/src/pages/*.tsx` |
| Reusable components | `frontend/src/components/*.tsx` |
| Zustand store | `frontend/src/store/gameStore.ts` |
| Typed API client | `frontend/src/api/client.ts` — returns `{ data, error }`, never throws to components |
| TS types | `frontend/src/types/index.ts` |

## When in doubt

- The conventions in [`CLAUDE.md`](./CLAUDE.md) override anything in this file.
- The grader rubric in `~/.claude/projects/.../memory/feedback_grading_rubric.md` is the source of truth for what scores points on the final project.
- Ask in the team chat before doing anything that touches auth, the schema, or the deploy pipeline.
