"""API 依赖：认证与权限"""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..utils.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="未提供认证令牌，请先登录")
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期，请重新登录")
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被禁用")
    return user


def require_permission(*perms: str):
    """权限校验依赖。用法：Depends(require_permission("approval_submit"))"""
    def checker(user: User = Depends(get_current_user)) -> User:
        role_perms = user.role.permissions if user.role else []
        if "*" in role_perms:
            return user
        for p in perms:
            if p in role_perms:
                return user
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail=f"当前角色（{user.role.name if user.role else '未知'}）无权限执行该操作")
    return checker


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.role or user.role.code != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="该操作仅管理员可用")
    return user