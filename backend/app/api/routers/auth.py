"""认证接口"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import AuditLog, Role, User
from ...utils.security import create_access_token, verify_password
from ..deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        db.add(AuditLog(user=body.username, action="login_failed", target=body.username,
                        detail="用户名或密码错误", ip="127.0.0.1"))
        db.commit()
        raise HTTPException(401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, detail="该账号已被禁用")

    user.last_login_at = datetime.utcnow()
    db.add(AuditLog(user=user.username, action="login", target=user.username,
                    detail=f"角色 {user.role.name if user.role else '-'}", ip="127.0.0.1"))
    db.commit()

    token = create_access_token({"sub": user.username, "role": user.role.code if user.role else ""})
    return {
        "access_token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role.name if user.role else "",
            "role_code": user.role.code if user.role else "",
            "permissions": user.role.permissions if user.role else [],
            "store": user.store.name if user.store else None,
        },
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role.name if user.role else "",
        "role_code": user.role.code if user.role else "",
        "permissions": user.role.permissions if user.role else [],
        "store": user.store.name if user.store else None,
    }