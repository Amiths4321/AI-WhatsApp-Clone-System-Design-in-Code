# api/routes/messages.py
# ══════════════════════════════════════════════════════
# API LAYER — Messages
# Teaches: send path, cursor pagination, delivery receipts
# ══════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from db.database    import get_db
from db.repository  import (MessageRepository, ConversationRepository,
                             MessageStatusRepository)
from core.security  import get_current_user_id
from services.delivery_service import DeliveryService
from schemas.message import (SendMessageRequest, MessageResponse,
                             DeliveryReceiptRequest, MessagePage)
from models.message import MessageState
from config.settings import MESSAGE_PAGE_SIZE

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post("/send", response_model=MessageResponse,
             status_code=status.HTTP_201_CREATED)
def send_message(
    payload:  SendMessageRequest,
    db:       Session = Depends(get_db),
    user_id:  int     = Depends(get_current_user_id),
):
    """
    WRITE PATH — Send a message.

    Full flow:
    1. Verify sender is a member of the conversation
    2. Store message in DB
    3. Fan-out: create MessageStatus per recipient
    4. Mark online recipients as DELIVERED immediately
    5. Return message with aggregated state
    """
    conv_repo = ConversationRepository(db)
    msg_repo  = MessageRepository(db)

    # ── Auth: is sender in this conversation? ─────────
    if not conv_repo.is_member(payload.conversation_id, user_id):
        raise HTTPException(status_code=403,
                            detail="You are not a member of this conversation")

    # ── Store message ─────────────────────────────────
    message = msg_repo.create(
        conversation_id = payload.conversation_id,
        sender_id       = user_id,
        content         = payload.content,
        message_type    = payload.message_type,
    )

    # ── Fan-out delivery ──────────────────────────────
    member_ids = conv_repo.get_member_ids(payload.conversation_id)
    delivery   = DeliveryService(db)
    delivery.fan_out(message.id, user_id, member_ids)

    # ── Update conversation timestamp ─────────────────
    conv_repo.update_last_message_at(payload.conversation_id)

    # ── Return with state ─────────────────────────────
    agg_state = delivery.get_aggregate_state(message.id, user_id)

    return MessageResponse(
        id              = message.id,
        conversation_id = message.conversation_id,
        sender_id       = message.sender_id,
        content         = message.content,
        message_type    = message.message_type,
        sent_at         = message.sent_at,
        state           = agg_state,
        is_deleted      = message.is_deleted,
    )


@router.get("/{conversation_id}", response_model=MessagePage)
def get_messages(
    conversation_id: int,
    before_id:       Optional[int] = Query(None,
                         description="Cursor: fetch messages before this ID"),
    db:      Session = Depends(get_db),
    user_id: int     = Depends(get_current_user_id),
):
    """
    READ PATH — Paginate messages in a conversation.

    Uses CURSOR-BASED pagination (before_id):
    - First load: GET /messages/5  → returns latest 20
    - Next page:  GET /messages/5?before_id=101 → next 20 older
    - No missing/duplicate messages even if new ones arrive
    """
    conv_repo = ConversationRepository(db)
    if not conv_repo.is_member(conversation_id, user_id):
        raise HTTPException(status_code=403, detail="Not a member")

    msg_repo = MessageRepository(db)
    # Fetch page_size + 1 to detect if there are more
    rows = msg_repo.get_page(conversation_id, before_id,
                             page_size=MESSAGE_PAGE_SIZE)

    has_more = len(rows) > MESSAGE_PAGE_SIZE
    rows     = rows[:MESSAGE_PAGE_SIZE]

    # Mark these messages as DELIVERED for this user
    status_repo = MessageStatusRepository(db)
    delivery    = DeliveryService(db)
    for msg in rows:
        if msg.sender_id != user_id:
            delivery.mark_delivered(msg.id, user_id)
        agg = delivery.get_aggregate_state(msg.id, msg.sender_id)

    # Build response (reverse so oldest first in page)
    messages = []
    for msg in reversed(rows):
        agg = delivery.get_aggregate_state(msg.id, msg.sender_id)
        messages.append(MessageResponse(
            id              = msg.id,
            conversation_id = msg.conversation_id,
            sender_id       = msg.sender_id,
            content         = msg.content,
            message_type    = msg.message_type,
            sent_at         = msg.sent_at,
            state           = agg,
            is_deleted      = msg.is_deleted,
        ))

    return MessagePage(
        messages    = messages,
        next_cursor = rows[-1].id if has_more else None,
        has_more    = has_more,
    )


@router.patch("/receipt", status_code=status.HTTP_204_NO_CONTENT)
def update_receipt(
    payload:  DeliveryReceiptRequest,
    db:       Session = Depends(get_db),
    user_id:  int     = Depends(get_current_user_id),
):
    """
    UPDATE RECEIPT — Client tells server "I received/read this message".
    This is what triggers the ✓✓ and 🔵 ticks on sender's side.

    In production: client sends receipts via WebSocket,
    not HTTP, to reduce connection overhead.
    """
    if payload.state not in (MessageState.DELIVERED, MessageState.READ):
        raise HTTPException(status_code=400,
                            detail="State must be DELIVERED or READ")

    msg_repo = MessageRepository(db)
    msg = msg_repo.get_by_id(payload.message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    delivery = DeliveryService(db)
    if payload.state == MessageState.READ:
        delivery.mark_read(payload.message_id, user_id)
    else:
        delivery.mark_delivered(payload.message_id, user_id)
