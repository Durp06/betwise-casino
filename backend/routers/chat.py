"""
routers/chat.py — in-game player chat for BOTH multiplayer games.

One polymorphic endpoint pair serves blackjack tables (CasinoTable/TableSeat)
and multiplayer Hold'em tables (HoldemTable/HoldemSeat), discriminated by the
`{table_kind}` path segment ('blackjack' | 'holdem').

Design constraints (project CLAUDE.md):
- Per-router SQL helper(s) at the bottom; lazy imports inside handlers with
  `# noqa: PLC0415`; type hints on every function; HTTPException not bare.
- The POST endpoint is rate-limited via the shared slowapi `limiter` (per-user),
  mirroring routers/poker_advice.py: it takes `request: Request` and stuffs
  `request.state.user_id` so ratelimit.py keys on the UUID.

SECURITY — stored-XSS defense:
- `_sanitize_body` trims, rejects empty/whitespace-only (400) and >500 chars
  (400), and strips ASCII control characters + null bytes. It does NOT
  HTML-escape: the body is stored VERBATIM. React-escaping happens once, on the
  client, when the body is rendered as a plain text child (`{m.body}`). Escaping
  on store too would double-escape. Because the client never feeds the body to
  dangerouslySetInnerHTML / href / eval, pasted markup such as
  `<script>alert(1)</script>` renders as inert literal text and cannot execute.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from backend.auth import CurrentUser
from backend.database import get_db
from backend.ratelimit import limiter
from backend.schemas import ChatMessageOut, ChatPostIn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_VALID_TABLE_KINDS = ("blackjack", "holdem")
_MAX_BODY_LEN = 500
_RECENT_LIMIT = 50

# Per-user post throttle (anti-flood). Tunable in tests / ops via the same env
# var the advice limiter uses so the suite never trips it during normal runs.
CHAT_RATE_LIMIT = "30/minute"


# ─── Pure helper (unit-tested) ─────────────────────────────────────────────────


def _sanitize_body(raw: str) -> str:
    """Validate + clean a chat body for storage.

    - Strips ASCII control characters (incl. NUL \\x00 and BEL \\x07) but keeps
      ordinary printable text, spaces, and unicode/emoji.
    - Trims surrounding whitespace.
    - Rejects empty / whitespace-only and over-length bodies with HTTP 400.

    Does NOT HTML-escape — the body is stored verbatim and rendered safely as a
    React text node client-side (see module docstring)."""
    # Strip C0 control chars (0x00-0x1F) and DEL (0x7F); keep \t? No — drop tabs
    # too so the stored text is single-line clean. Spaces (0x20) are kept.
    cleaned = "".join(ch for ch in raw if ord(ch) >= 0x20 and ord(ch) != 0x7F)
    cleaned = cleaned.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(cleaned) > _MAX_BODY_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Message too long (max {_MAX_BODY_LEN} characters)",
        )
    return cleaned


# ─── Route handlers ─────────────────────────────────────────────────────────


@router.post("/{table_kind}/{table_id}/messages", response_model=ChatMessageOut, status_code=201)
@limiter.limit(CHAT_RATE_LIMIT)
async def post_message(
    request: Request,
    table_kind: str,
    table_id: uuid.UUID,
    body: ChatPostIn,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ChatMessageOut:
    """Post a chat message. Requires the caller to be SEATED at the table."""
    request.state.user_id = str(current_user)
    return await _post_message(table_kind, table_id, body.body, current_user, db)


@router.get("/{table_kind}/{table_id}/messages", response_model=list[ChatMessageOut])
async def get_messages(
    table_kind: str,
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessageOut]:
    """Return the most recent 50 messages for this table, oldest-first.

    Any authenticated user may read, matching the public `/state` read."""
    return await _get_messages(table_kind, table_id, db)


# ─── SQL helper (single source per router) ─────────────────────────────────────


async def _is_seated(table_kind: str, table_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> bool:
    """True if `user_id` holds a seat at the given table."""
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import HoldemSeat, TableSeat  # noqa: PLC0415

    if table_kind == "blackjack":
        seat_id = (await db.execute(
            select(TableSeat.id).where(TableSeat.table_id == table_id, TableSeat.user_id == user_id)
        )).scalar_one_or_none()
    else:  # holdem
        seat_id = (await db.execute(
            select(HoldemSeat.id).where(HoldemSeat.table_id == table_id, HoldemSeat.user_id == user_id)
        )).scalar_one_or_none()
    return seat_id is not None


async def _post_message(
    table_kind: str,
    table_id: uuid.UUID,
    raw_body: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ChatMessageOut:
    from datetime import datetime, timezone  # noqa: PLC0415

    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import ChatMessage, User  # noqa: PLC0415

    if table_kind not in _VALID_TABLE_KINDS:
        raise HTTPException(status_code=404, detail="Unknown table kind")

    if not await _is_seated(table_kind, table_id, user_id, db):
        raise HTTPException(status_code=403, detail="You must be seated at this table to chat")

    # Validate BEFORE doing the username lookup so a bad body fails fast (and a
    # NUL byte never reaches the DB).
    clean = _sanitize_body(raw_body)

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    message = ChatMessage(
        id=uuid.uuid4(),
        table_kind=table_kind,
        table_id=table_id,
        user_id=user_id,
        username=user.username,
        body=clean,
        created_at=datetime.now(timezone.utc),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return ChatMessageOut.model_validate(message)


async def _get_messages(
    table_kind: str,
    table_id: uuid.UUID,
    db: AsyncSession,
) -> list[ChatMessageOut]:
    from sqlalchemy import select  # noqa: PLC0415

    from backend.models import ChatMessage  # noqa: PLC0415

    if table_kind not in _VALID_TABLE_KINDS:
        raise HTTPException(status_code=404, detail="Unknown table kind")

    # Fetch the most recent N (DESC) then reverse so the payload is oldest-first
    # for a chat scrollback that reads top-to-bottom.
    rows = (await db.execute(
        select(ChatMessage)
        .where(ChatMessage.table_kind == table_kind, ChatMessage.table_id == table_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(_RECENT_LIMIT)
    )).scalars().all()
    return [ChatMessageOut.model_validate(m) for m in reversed(rows)]


__all__ = ["router", "_sanitize_body"]
