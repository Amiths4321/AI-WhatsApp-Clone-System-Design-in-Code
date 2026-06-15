# schemas/message.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.message import MessageState, ConversationType

class CreateConversationRequest(BaseModel):
    type:        ConversationType = ConversationType.DIRECT
    member_ids:  List[int] = Field(..., min_length=1)
    name:        Optional[str] = None   # required for group

class ConversationResponse(BaseModel):
    id:              int
    type:            ConversationType
    name:            Optional[str]
    last_message_at: datetime
    member_count:    int
    model_config     = {"from_attributes": True}

class SendMessageRequest(BaseModel):
    conversation_id: int
    content:         str = Field(..., min_length=1, max_length=4096)
    message_type:    str = "text"

class MessageResponse(BaseModel):
    id:              int
    conversation_id: int
    sender_id:       int
    content:         str
    message_type:    str
    sent_at:         datetime
    state:           MessageState   # aggregated state for this user
    is_deleted:      bool
    model_config     = {"from_attributes": True}

class DeliveryReceiptRequest(BaseModel):
    message_id:  int
    state:       MessageState   # DELIVERED or READ

class MessagePage(BaseModel):
    """Cursor-based pagination response."""
    messages:    List[MessageResponse]
    next_cursor: Optional[int]   # message_id to fetch next page
    has_more:    bool
