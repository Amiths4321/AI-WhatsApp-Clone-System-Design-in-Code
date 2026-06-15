# api/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db.database  import get_db
from db.repository import UserRepository
from core.security import hash_password, verify_password, create_token
from schemas.user  import RegisterRequest, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register", response_model=TokenResponse,
             status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    repo = UserRepository(db)
    if repo.get_by_phone(payload.phone):
        raise HTTPException(status_code=409,
                            detail="Phone number already registered")
    user = repo.create(
        phone         = payload.phone,
        display_name  = payload.display_name,
        password_hash = hash_password(payload.password),
    )
    return TokenResponse(
        access_token = create_token(user.id),
        user_id      = user.id,
        display_name = user.display_name,
    )

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    repo = UserRepository(db)
    user = repo.get_by_phone(payload.phone)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(
        access_token = create_token(user.id),
        user_id      = user.id,
        display_name = user.display_name,
    )
