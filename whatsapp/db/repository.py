# db/repository.py
# ══════════════════════════════════════════════════════
# DATABASE LAYER — Repositories
#
# NEW vs URL Shortener:
#   - 4 repositories (one per model)
#   - JOIN queries (conversations + members)
#   - Cursor-based pagination (NEW concept)
#   - Bulk inserts (fan-out: N MessageStatus rows)
# ══════════════════════════════════════════════════════

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from models.user    import User
from models.message import (Conversation, ConversationMember,
                            Message, MessageStatus,
                            MessageState, ConversationType)
from config.settings import MESSAGE_PAGE_SIZE


# ── USER REPOSITORY ───────────────────────────────────
class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, phone: str, display_name: str, password_hash: str) -> User:
        user = User(phone=phone, display_name=display_name,
                    password_hash=password_hash)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_id(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_phone(self, phone: str) -> Optional[User]:
        return self.db.query(User).filter(User.phone == phone).first()

    def set_online(self, user_id: int, is_online: bool):
        now = datetime.now(timezone.utc)
        update = {"is_online": is_online}
        if not is_online:
            update["last_seen"] = now
        self.db.query(User).filter(User.id == user_id).update(update)
        self.db.commit()


# ── CONVERSATION REPOSITORY ───────────────────────────
class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, type: ConversationType, created_by_id: int,
               name: Optional[str] = None) -> Conversation:
        conv = Conversation(type=type, created_by_id=created_by_id, name=name)
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def add_member(self, conversation_id: int, user_id: int,
                   is_admin: bool = False) -> ConversationMember:
        member = ConversationMember(
            conversation_id=conversation_id,
            user_id=user_id,
            is_admin=is_admin
        )
        self.db.add(member)
        self.db.commit()
        return member

    def get_by_id(self, conv_id: int) -> Optional[Conversation]:
        return self.db.query(Conversation).filter(
            Conversation.id == conv_id,
            Conversation.is_active == True
        ).first()

    def is_member(self, conv_id: int, user_id: int) -> bool:
        """Auth check: does this user belong to this conversation?"""
        return self.db.query(ConversationMember).filter(
            ConversationMember.conversation_id == conv_id,
            ConversationMember.user_id == user_id,
            ConversationMember.is_active == True
        ).first() is not None

    def get_member_ids(self, conv_id: int) -> List[int]:
        """Get all member IDs — used for fan-out."""
        rows = self.db.query(ConversationMember.user_id).filter(
            ConversationMember.conversation_id == conv_id,
            ConversationMember.is_active == True
        ).all()
        return [r[0] for r in rows]

    def get_user_conversations(self, user_id: int) -> List[Conversation]:
        """List all conversations for a user, newest first."""
        conv_ids = self.db.query(ConversationMember.conversation_id).filter(
            ConversationMember.user_id == user_id,
            ConversationMember.is_active == True
        ).subquery()

        return (self.db.query(Conversation)
                .filter(Conversation.id.in_(conv_ids))
                .filter(Conversation.is_active == True)
                .order_by(desc(Conversation.last_message_at))
                .all())

    def update_last_message_at(self, conv_id: int):
        self.db.query(Conversation).filter(
            Conversation.id == conv_id
        ).update({"last_message_at": datetime.now(timezone.utc)})
        self.db.commit()

    def find_direct(self, user_a: int, user_b: int) -> Optional[Conversation]:
        """Find existing 1-to-1 conversation between two users."""
        # Conversations where user_a is member
        a_convs = self.db.query(ConversationMember.conversation_id).filter(
            ConversationMember.user_id == user_a,
            ConversationMember.is_active == True
        ).subquery()
        # Of those, find one where user_b is also member and type=DIRECT
        result = (self.db.query(Conversation)
                  .filter(Conversation.id.in_(a_convs))
                  .filter(Conversation.type == ConversationType.DIRECT)
                  .join(ConversationMember,
                        and_(ConversationMember.conversation_id == Conversation.id,
                             ConversationMember.user_id == user_b,
                             ConversationMember.is_active == True))
                  .first())
        return result


# ── MESSAGE REPOSITORY ────────────────────────────────
class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, conversation_id: int, sender_id: int,
               content: str, message_type: str = "text") -> Message:
        msg = Message(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
            message_type=message_type
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def get_by_id(self, msg_id: int) -> Optional[Message]:
        return self.db.query(Message).filter(
            Message.id == msg_id,
            Message.is_deleted == False
        ).first()

    def get_page(self, conv_id: int, before_id: Optional[int] = None,
                 page_size: int = MESSAGE_PAGE_SIZE) -> List[Message]:
        """
        Cursor-based pagination (NEW concept).

        Why cursor-based instead of offset (page 1, page 2...)?
        - Offset: SELECT ... LIMIT 20 OFFSET 100
          Problem: if new messages arrive, page 2 shifts → duplicate/missing msgs
        - Cursor: SELECT ... WHERE id < {last_seen_id} LIMIT 20
          Stable: new messages don't affect older pages
        """
        q = self.db.query(Message).filter(
            Message.conversation_id == conv_id,
            Message.is_deleted == False
        )
        if before_id:
            q = q.filter(Message.id < before_id)

        return q.order_by(desc(Message.id)).limit(page_size + 1).all()

    def soft_delete(self, msg_id: int):
        self.db.query(Message).filter(Message.id == msg_id).update(
            {"is_deleted": True}
        )
        self.db.commit()


# ── MESSAGE STATUS REPOSITORY ─────────────────────────
class MessageStatusRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_bulk(self, message_id: int,
                    recipient_ids: List[int]) -> List[MessageStatus]:
        """
        Fan-out: create one MessageStatus per recipient.
        Architecture insight: this is the 'write amplification'
        problem. In a group of 256, one message = 255 status rows.
        At WhatsApp scale: use Kafka to fan out asynchronously.
        """
        statuses = [
            MessageStatus(message_id=message_id, recipient_id=rid)
            for rid in recipient_ids
        ]
        self.db.bulk_save_objects(statuses)
        self.db.commit()
        return statuses

    def update_state(self, message_id: int, recipient_id: int,
                     state: MessageState) -> Optional[MessageStatus]:
        """Update delivery receipt for one recipient."""
        now = datetime.now(timezone.utc)
        update = {"state": state}
        if state == MessageState.DELIVERED:
            update["delivered_at"] = now
        elif state == MessageState.READ:
            update["delivered_at"] = now
            update["read_at"]      = now

        rows = self.db.query(MessageStatus).filter(
            MessageStatus.message_id   == message_id,
            MessageStatus.recipient_id == recipient_id
        ).update(update)
        self.db.commit()
        return rows > 0

    def get_for_message(self, message_id: int) -> List[MessageStatus]:
        return self.db.query(MessageStatus).filter(
            MessageStatus.message_id == message_id
        ).all()

    def get_aggregate_state(self, message_id: int,
                            sender_id: int) -> MessageState:
        """
        Compute the aggregate state shown to the sender.
        WhatsApp rule:
        - All recipients READ  → show READ (blue ticks)
        - All recipients DELIVERED → show DELIVERED (grey double)
        - Otherwise → SENT (grey single)
        """
        statuses = self.get_for_message(message_id)
        if not statuses:
            return MessageState.SENT

        states = {s.state for s in statuses}
        if all(s.state == MessageState.READ for s in statuses):
            return MessageState.READ
        if all(s.state in (MessageState.READ, MessageState.DELIVERED)
               for s in statuses):
            return MessageState.DELIVERED
        return MessageState.SENT
