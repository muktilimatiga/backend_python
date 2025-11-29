from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, case, cast, Date
import models
from schemas import users as schemas
from core.security import hash_password, verify_password

def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()

def get_all_users(db: Session) -> List[models.User]:
    return db.query(models.User).order_by(models.User.username).all()

def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    hashed_pass = hash_password(user.password)
    db_user = models.User(
        **user.model_dump(exclude={"password"}), 
        hashed_password=hashed_pass
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(
    db: Session, username: str, password: str
) -> Optional[models.User]:
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def get_user_stats(db: Session, username: str, interval: str) -> Dict[str, int]:
    open_case = case((models.LogKomplain.status == 'open', 1), else_=0)
    proses_case = case((models.LogKomplain.status == 'proses', 1), else_=0)
    
    stats = (
        db.query(
            func.coalesce(func.sum(open_case), 0).label("open_tickets"),
            func.coalesce(func.sum(proses_case), 0).label("proses_tickets")
        )
        .join(models.User.tickets)
        .filter(
            models.User.username == username,
            cast(models.LogKomplain.last_updated, Date) >= func.date_trunc(interval, func.current_date())
        )
        .one()
    )
    
    total = stats.open_tickets + stats.proses_tickets
    return {
        "open_tickets": stats.open_tickets,
        "proses_tickets": stats.proses_tickets,
        "total_active": total
    }