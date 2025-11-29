from typing import List
from fastapi import APIRouter, HTTPException, Query, Depends, status
from sqlalchemy.orm import Session
import models
from schemas import users as schemas
from services import user_services
from services.database import get_db
from api.v1.deps import get_current_user

router = APIRouter()

@router.post("/", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
def add_user(
    user: schemas.UserCreate, 
    db: Session = Depends(get_db)
):
    db_user = user_services.get_user_by_username(db, user.username)
    if db_user:
        raise HTTPException(status_code=409, detail=f"User '{user.username}' already exists.")
    return user_services.create_user(db=db, user=user)

@router.get("/me", response_model=schemas.User)
def get_current_user_me(
    current_user: models.User = Depends(get_current_user)
):
    return current_user

@router.get("/", response_model=List[schemas.User])
def get_all_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return user_services.get_all_users(db)

@router.get("/{username}/stats", response_model=schemas.UserStats)
def get_user_stats_endpoint(
    username: str,
    interval: str = Query("month", enum=["week", "month", "year"]),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    db_user = user_services.get_user_by_username(db, username)
    if not db_user:
        raise HTTPException(status_code=44.04, detail=f"User '{username}' not found.")
    
    stats_dict = user_services.get_user_stats(db, username, interval)
    return schemas.UserStats(**stats_dict)