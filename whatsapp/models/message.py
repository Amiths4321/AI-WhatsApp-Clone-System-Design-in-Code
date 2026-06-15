# models/message.py
# ══════════════════════════════════════════════════════
# DATABASE LAYER — Conversation + Message Models
#
# NEW concepts vs URL Shortener:
#   1. Two-table design: Conversation → Messages
#   2. Message state machine: SENT→DELIVERED→READ
#   3. ConversationMember: who is in each conversation
#   4. MessageStatus: per-recipient delivery tracking
#
# Architecture insight:
#   WhatsApp uses TWO tables for delivery tracking:
#   - Message: the content (stored once)
#   - MessageStatus: one row per recipient per message
#   This is how "✓ sent, ✓✓ delivered, 🔵 read" works
# ══════════════════════════════════════════════════════

import enum
from datetime import datetime, timezone
from sqlalchemy import (Column, String, Integer, DateTime,
                        Boolean, ForeignKey, Enum, Text)
from sqlalchemy.orm import relationship
from db.database import Base


# ── MESSAGE STATE MACHINE (NEW concept) ───────────────
# This is one of the most important design decisions in messaging systems.
# Each state maps to a UI indicator:
#   SENT      → single grey tick  ✓
#   DELIVERED → double grey tick  ✓✓
#   READ      → double blue tick  🔵🔵
#   FAILED    → red exclamation   ⚠
class MessageState(str, enum.Enum):
    SENT      = "sent"
    DELIVERED = "delivered"
    READ      = "read"
    FAILED    = "failed"


class ConversationType(str, enum.Enum):
    DIRECT = "direct"   # 1-to-1 chat
    GROUP  = "group"    # group chat


# ── CONVERSATION TABLE ────────────────────────────────
class Conversation(Base):
    """
    A conversation is a container for messages.
    Can be DIRECT (2 people) or GROUP (up to 256).

    Architecture insight: separating Conversation from Message
    lets you:
    - List conversations without loading all messages
    - Track last_message_at for sorting inbox
    - Add group metadata (name, avatar) independently
    """
    __tablename__ = "conversations"

    id              = Column(Integer, primary_key=True, index=True)
    type            = Column(Enum(ConversationType),
                             default=ConversationType.DIRECT, nullable=False)
    name            = Column(String(100), nullable=True)  # group name only
    created_by_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at      = Column(DateTime(timezone=True),
                             default=lambda: datetime.now(timezone.utc))
    last_message_at = Column(DateTime(timezone=True),
                             default=lambda: datetime.now(timezone.utc))
    is_active       = Column(Boolean, default=True)

    # Relationships
    members  = relationship("ConversationMember", back_populates="conversation",
                            lazy="dynamic")
    messages = relationship("Message", back_populates="conversation",
                            lazy="dynamic")


# ── CONVERSATION MEMBER TABLE ─────────────────────────
class ConversationMember(Base):
    """
    Who is in each conversation.
    Many-to-many: User ↔ Conversation.

    Architecture insight: this join table lets us:
    - Check if a user belongs to a conversation (auth)
    - Track when they joined / left
    - Store per-member settings (muted, admin)
    """
    __tablename__ = "conversation_members"

    id              = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"),
                             nullable=False, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"),
                             nullable=False, index=True)
    joined_at       = Column(DateTime(timezone=True),
                             default=lambda: datetime.now(timezone.utc))
    is_admin        = Column(Boolean, default=False)
    is_active       = Column(Boolean, default=True)  # False = left group

    # Relationships
    conversation = relationship("Conversation", back_populates="members")


# ── MESSAGE TABLE ─────────────────────────────────────
class Message(Base):
    """
    The message content — stored ONCE regardless of recipients.

    Architecture insight:
    Content is stored here. Delivery state per-recipient
    is stored in MessageStatus. This avoids duplicating
    the content N times for N recipients (storage efficiency).
    """
    __tablename__ = "messages"

    id              = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"),
                             nullable=False, index=True)
    sender_id       = Column(Integer, ForeignKey("users.id"),
                             nullable=False, index=True)
    content         = Column(Text, nullable=False)
    message_type    = Column(String(20), default="text")  # text/image/file
    sent_at         = Column(DateTime(timezone=True),
                             default=lambda: datetime.now(timezone.utc),
                             index=True)   # indexed for time-range queries
    is_deleted      = Column(Boolean, default=False)  # "This message was deleted"

    # Relationships
    conversation    = relationship("Conversation", back_populates="messages")
    status_records  = relationship("MessageStatus", back_populates="message",
                                   lazy="dynamic")

    def __repr__(self):
        return f"<Message {self.id} from user {self.sender_id}>"


# ── MESSAGE STATUS TABLE (NEW concept: delivery receipts) ─
class MessageStatus(Base):
    """
    Per-recipient delivery state for each message.

    WHY a separate table?
    In a group of 10 people:
    - 1 Message row (content stored once)
    - 9 MessageStatus rows (one per recipient, NOT sender)
    Each row tracks: delivered? read? when?

    This is how WhatsApp shows:
    - "Delivered to 7 of 9 members"
    - Blue ticks only when ALL recipients read it (direct chat)
    """
    __tablename__ = "message_statuses"

    id           = Column(Integer, primary_key=True, index=True)
    message_id   = Column(Integer, ForeignKey("messages.id"),
                          nullable=False, index=True)
    recipient_id = Column(Integer, ForeignKey("users.id"),
                          nullable=False, index=True)
    state        = Column(Enum(MessageState),
                          default=MessageState.SENT, nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at      = Column(DateTime(timezone=True), nullable=True)

    # Relationship
    message = relationship("Message", back_populates="status_records")
