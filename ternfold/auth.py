from __future__ import annotations
import hashlib, secrets
from datetime import timedelta
from argon2 import PasswordHasher
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import SessionToken, User, now_utc

hasher=PasswordHasher()
COOKIE="ternfold_session"

def password_hash(password:str)->str: return hasher.hash(password)
def password_ok(stored:str,password:str)->bool:
    try: return hasher.verify(stored,password)
    except Exception: return False
def token_hash(token:str)->str: return hashlib.sha256(token.encode()).hexdigest()

def create_session(db:Session,user:User)->tuple[str,SessionToken]:
    raw=secrets.token_urlsafe(32)
    row=SessionToken(token_hash=token_hash(raw),csrf_token=secrets.token_urlsafe(24),user_id=user.id,expires_at=now_utc()+timedelta(hours=12))
    db.add(row); db.flush(); return raw,row

def current_user(request:Request,db:Session)->User|None:
    raw=request.cookies.get(COOKIE)
    if not raw: return None
    row=db.scalar(select(SessionToken).where(SessionToken.token_hash==token_hash(raw),SessionToken.revoked_at.is_(None)))
    if not row or row.expires_at<now_utc(): return None
    return db.get(User,row.user_id)

def require_user(request:Request,db:Session)->User:
    user=current_user(request,db)
    if not user or not user.active: raise HTTPException(401,"Sign in required")
    return user

def csrf_for(request:Request,db:Session)->str:
    raw=request.cookies.get(COOKIE)
    row=db.scalar(select(SessionToken).where(SessionToken.token_hash==token_hash(raw))) if raw else None
    return row.csrf_token if row else ""

def verify_csrf(request:Request,db:Session,value:str)->None:
    if not value or not secrets.compare_digest(value,csrf_for(request,db)): raise HTTPException(403,"This form expired. Refresh and try again.")
