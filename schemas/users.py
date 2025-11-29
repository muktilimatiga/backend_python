from pydantic import BaseModel
from typing import Optional, List

class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None
    role: Optional[str] = None
    
    class Config:
        from_attributes = True

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int

class UserStats(BaseModel):
    open_tickets: int
    proses_tickets: int
    total_active: int

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None