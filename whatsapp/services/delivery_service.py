# services/delivery_service.py
# ══════════════════════════════════════════════════════
# SERVICE — Message Delivery + Fan-out
#
# NEW concept: fan-out
#   When one user sends a message to a group of N people,
#   the system must "fan out" — deliver to each recipient.
#
# Architecture:
#   Synchronous (this code): works for small groups
#   At scale: publish to Kafka → N consumer workers
#   each handling delivery to one recipient asynchronously
# ══════════════════════════════════════════════════════

from sqlalchemy.orm import Session
from typing import List
from models.message import MessageState
from db.repository  import MessageStatusRepository, UserRepository
from services.presence_service import presence_service


class DeliveryService:
    """
    ARCHITECTURE ROLE: Manages the SENT→DELIVERED→READ pipeline.

    Fan-out problem:
    - 1 message sent to group of 256
    - 255 delivery status records created (fan-out on write)
    - Each recipient's client polls or connects via WebSocket
    - When recipient opens message → update to READ

    At WhatsApp's scale:
    - Store message in Cassandra (fast writes)
    - Publish to Kafka topic per recipient
    - Each Kafka consumer handles delivery to one device
    - Read receipts sent back via WebSocket
    """

    def __init__(self, db: Session):
        self.status_repo = MessageStatusRepository(db)
        self.user_repo   = UserRepository(db)

    def fan_out(self, message_id: int, sender_id: int,
                member_ids: List[int]) -> dict:
        """
        Step 1 of delivery: create MessageStatus for every recipient.
        Sender is excluded (they don't get a receipt for themselves).

        Returns delivery summary.
        """
        recipients = [uid for uid in member_ids if uid != sender_id]
        if not recipients:
            return {"recipients": 0, "online": 0, "offline": 0}

        # Create SENT status for all recipients
        self.status_repo.create_bulk(message_id, recipients)

        # Check who is online → mark as DELIVERED immediately
        online_ids  = presence_service.get_online_users(recipients)
        offline_ids = set(recipients) - online_ids

        # Online users get DELIVERED status right away
        for uid in online_ids:
            self.status_repo.update_state(
                message_id, uid, MessageState.DELIVERED
            )

        print(f"  [Delivery] msg={message_id} | "
              f"{len(online_ids)} delivered | {len(offline_ids)} pending")

        return {
            "recipients":   len(recipients),
            "online":       len(online_ids),
            "offline":      len(offline_ids),
            "pending_ids":  list(offline_ids),
        }

    def mark_delivered(self, message_id: int, recipient_id: int) -> bool:
        """
        Called when offline user comes back online and fetches messages.
        Updates SENT → DELIVERED.
        """
        return self.status_repo.update_state(
            message_id, recipient_id, MessageState.DELIVERED
        )

    def mark_read(self, message_id: int, reader_id: int) -> bool:
        """
        Called when user opens/views a message.
        Updates DELIVERED → READ.
        Triggers blue tick on sender's side.
        """
        return self.status_repo.update_state(
            message_id, reader_id, MessageState.READ
        )

    def get_aggregate_state(self, message_id: int, sender_id: int) -> MessageState:
        """What tick state does the sender see?"""
        return self.status_repo.get_aggregate_state(message_id, sender_id)
