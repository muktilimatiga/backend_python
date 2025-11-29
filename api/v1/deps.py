from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from core.security import decode_access_token
from core.config import settings
from services import user_services
from services.database import get_db
import models
from schemas import users as schemas
from typing import Optional

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

def get_current_user(
    db: Session = Depends(get_db), token: Optional[str] = Depends(oauth2_scheme)
) -> Optional[models.User]:
    # Skip authentication if disabled in development mode
    if settings.DISABLE_AUTH:
        # Return a default user for development
        return models.User(
            id=1,
            username="dev_user",
            full_name="Development User",
            role="admin"
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise credentials_exception
    
    username = decode_access_token(token)
    if username is None:
        raise credentials_exception
        
    user = user_services.get_user_by_username(db, username=username)
    if user is None:
        raise credentials_exception
        
    return user

def get_current_user_optional(
    db: Session = Depends(get_db), token: Optional[str] = Depends(oauth2_scheme)
) -> Optional[models.User]:
    # Skip authentication if disabled in development mode
    if settings.DISABLE_AUTH:
        # Return a default user for development
        return models.User(
            id=1,
            username="dev_user",
            full_name="Development User",
            role="admin"
        )
    
    # If no token provided, return None instead of raising exception
    if not token:
        return None
    
    username = decode_access_token(token)
    if username is None:
        return None
        
    user = user_services.get_user_by_username(db, username=username)
    if user is None:
        return None
        
    return user