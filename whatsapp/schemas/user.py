# schemas/user.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class RegisterRequest(BaseModel):
    phone:        str = Field(..., min_length=10, max_length=20)
    display_name: str = Field(..., min_length=1, max_length=100)
    password:     str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    phone:    str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user_id:      int
    display_name: str

class UserResponse(BaseModel):
    id:           int
    phone:        str
    display_name: str
    is_online:    bool
    last_seen:    Optional[datetime]
    model_config  = {"from_attributes": True}
