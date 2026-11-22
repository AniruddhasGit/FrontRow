"""POST /api/support/messages - the Help & support contact form (CR-008 T8). Stores the message; sends no email.

Open to a guest and to a signed-in account. A signed-in sender's message is filed under their own account and
address (the session decides; an email in the body is ignored for them); a guest must give an address. Limited per
real client IP in Redis, failing closed, so the form cannot be used to fill the table.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import current_user, db
from app.api.errors import ApiError
from app.api.me import _down
from app.core.ratelimit import Bucket, client_ip, enforce
from app.models import support_message

router = APIRouter(prefix="/api/support")

# ponytail: reuses the registration bucket's capacity setting (5 per IP per hour) under its own key, so no new setting
# exists for one form; a dedicated RATE_LIMIT_SUPPORT_IP_PER_HOUR is the upgrade path if the two ever need to differ.
SUPPORT_IP = Bucket("support:ip", "RATE_LIMIT_REGISTER_IP_PER_HOUR", 3600, "Too many messages. Try again in {span}.")
UNAVAILABLE = "Your message cannot be sent right now. Try again shortly."
SENT = "Thanks - your message has been received. Payments here are simulated, so nothing has been charged."
ERRORS = {"email": "Enter the email address a reply should go to.", "message": "Write a message of 1 to 2000 characters."}


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: Literal["booking", "payment", "rewards", "account", "other"]
    message: StrictStr
    email: StrictStr | None = None


@router.post("/messages", status_code=201)
async def send_message(request: Request, conn: AsyncConnection = Depends(db)) -> dict:
    try:
        body = Message.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise ApiError(400, "REQUEST_INVALID", "This request could not be processed.") from None
    settings, clock = request.app.state.settings, request.app.state.clock
    try:
        user = await current_user(request, conn, settings, clock)
    except ApiError as exc:
        if exc.status != 401:
            raise
        user = None
    email = user.email if user else (body.email or "").strip()
    text = body.message.strip()
    errors = {}
    if not (3 <= len(email) <= 254 and "@" in email):
        errors["email"] = ERRORS["email"]
    if not 1 <= len(text) <= 2000:
        errors["message"] = ERRORS["message"]
    if errors:
        raise ApiError(422, "VALIDATION_FAILED", next(iter(errors.values())), {"fields": errors})
    await enforce(request, [(SUPPORT_IP, client_ip(request, settings))], UNAVAILABLE)
    try:
        async with conn.begin():
            row = (await conn.execute(insert(support_message).values(
                user_id=user.id if user else None, email=email, topic=body.topic, message=text, created_at=clock.now())
                .returning(support_message.c.id))).scalar_one()
    except Exception as exc:
        if _down(exc):
            raise ApiError(503, "DEPENDENCY_UNAVAILABLE", UNAVAILABLE) from None
        raise
    return {"id": row, "message": SENT}
