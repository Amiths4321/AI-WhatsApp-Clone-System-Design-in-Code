# api/routes/conversations.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from db.database    import get_db
from db.repository  import ConversationRepository, UserRepository
from core.security  import get_current_user_id
from schemas.message import CreateConversationRequest, ConversationResponse
from models.message  import ConversationType
from config.settings import MAX_GROUP_MEMBERS

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=ConversationResponse,
             status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload:  CreateConversationRequest,
    db:       Session = Depends(get_db),
    user_id:  int     = Depends(get_current_user_id),
):
    conv_repo = ConversationRepository(db)
    user_repo = UserRepository(db)

    # Validate group constraints
    if payload.type == ConversationType.GROUP:
        if not payload.name:
            raise HTTPException(status_code=400,
                                detail="Group conversations require a name")
        if len(payload.member_ids) > MAX_GROUP_MEMBERS:
            raise HTTPException(status_code=400,
                                detail=f"Max {MAX_GROUP_MEMBERS} members")
    else:
        # Direct: check if conversation already exists
        if len(payload.member_ids) != 1:
            raise HTTPException(status_code=400,
                                detail="Direct chat needs exactly 1 other member")
        existing = conv_repo.find_direct(user_id, payload.member_ids[0])
        if existing:
            member_count = existing.members.filter_by(is_active=True).count()
            return ConversationResponse(
                id=existing.id, type=existing.type, name=existing.name,
                last_message_at=existing.last_message_at,
                member_count=member_count,
            )

    # Create conversation
    conv = conv_repo.create(
        type=payload.type, created_by_id=user_id, name=payload.name
    )

    # Add creator + all members
    all_members = list(set([user_id] + payload.member_ids))
    for mid in all_members:
        user = user_repo.get_by_id(mid)
        if not user:
            raise HTTPException(status_code=404,
                                detail=f"User {mid} not found")
        conv_repo.add_member(conv.id, mid, is_admin=(mid == user_id))

    member_count = len(all_members)
    return ConversationResponse(
        id=conv.id, type=conv.type, name=conv.name,
        last_message_at=conv.last_message_at, member_count=member_count,
    )


@router.get("", response_model=List[ConversationResponse])
def list_conversations(
    db:      Session = Depends(get_db),
    user_id: int     = Depends(get_current_user_id),
):
    """List all conversations for the current user, newest first."""
    conv_repo = ConversationRepository(db)
    convs     = conv_repo.get_user_conversations(user_id)
    result    = []
    for c in convs:
        count = c.members.filter_by(is_active=True).count()
        result.append(ConversationResponse(
            id=c.id, type=c.type, name=c.name,
            last_message_at=c.last_message_at, member_count=count,
        ))
    return result


# api/routes/presence.py  (inlined here for brevity)
from fastapi import APIRouter as _R
from services.presence_service import presence_service

presence_router = _R(prefix="/presence", tags=["Presence"])

@presence_router.post("/heartbeat", status_code=204)
def heartbeat(user_id: int = Depends(get_current_user_id)):
    """Client sends this every 30s. Keeps user marked as online."""
    presence_service.heartbeat(user_id)

@presence_router.post("/typing/{conversation_id}", status_code=204)
def typing(conversation_id: int,
           user_id: int = Depends(get_current_user_id)):
    """Tell others 'User is typing...' Expires in 5s automatically."""
    presence_service.set_typing(conversation_id, user_id)

@presence_router.get("/typing/{conversation_id}")
def get_typing(conversation_id: int,
               user_id: int = Depends(get_current_user_id)):
    typing_users = presence_service.get_typing_users(conversation_id, user_id)
    return {"typing_user_ids": typing_users}
