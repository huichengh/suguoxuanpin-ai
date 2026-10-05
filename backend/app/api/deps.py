"""API 依赖：认证与权限"""
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..utils.security import decode_token

bearer = HTTPBearer(auto_error=False)

# 令牌为三段 base64url（头.载荷.签名），段内字符集 [A-Za-z0-9_-]。
# 部分网关会在 Authorization 头中追加自己的凭据，且与令牌之间没有分隔符，
# 导致 HTTPBearer 截取出的 credentials 混入额外内容、验签必然失败。
# 由于追加内容与签名段同处一个字符集，按字符位置或正则都无法可靠切分。
# 这里的做法是：按点号定位候选起点，再对每个可能的结束位置逐一验签，
# 以「签名是否通过」为唯一判据。候选数量为 O(段数 × 长度)，开销可忽略。
_SCHEMES = ("bearer", "basic", "token", "jwt", "digest", "oauth", "ntlm", "negotiate")
_MIN_TOKEN_LEN = 20
_MAX_TOKEN_LEN = 4096


def _candidate_tokens(raw: str) -> List[str]:
    """枚举头中所有可能是令牌的三段串。

    JWT 首段固定（HS256 的头部 base64url 编码），可据此锚定起点。
    签名段长度也固定：HS256 为 SHA-256 的 32 字节，base64url 无填充即 43 字符。
    因此只有载荷段的终点不确定——网关凭据可能被插在载荷段与签名段之间，
    使第二个点前的内容被污染。枚举载荷终点并以验签结果为判据即可还原真实令牌。
    """
    if not raw:
        return []

    HEADER = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"  # {"alg":"HS256","typ":"JWT"}
    SIG_LENS = (43, 42, 44)  # HS256 标准长度为 43，兼容个别实现的补位差异
    H = len(HEADER)

    out: List[str] = []
    seen = set()

    pos = 0
    while True:
        i = raw.find(HEADER, pos)
        if i < 0:
            break
        pos = i + 1

        rest = raw[i + H:]
        d1 = rest.find(".")          # 首段与载荷段之间的点（真实）
        if d1 < 0:
            continue
        head_end = i + H + d1        # 首段末尾（不含分隔点）
        payload_from = head_end + 1  # 载荷段起始

        # 第二个点：签名段的起点。载荷段可能已被网关凭据污染，
        # 因此载荷终点需要在 d1 与该点之间枚举。
        for j, ch in enumerate(rest):
            if ch != "." or j <= d1:
                continue
            sig_start = i + H + j + 1
            # 签名段终点：优先按标准长度，末位兜底为「一直取到头尾」
            ends = [sig_start + L for L in SIG_LENS] + [len(raw)]
            for se in ends:
                if se > len(raw) or se <= sig_start:
                    continue
                # 载荷终点由短到长枚举，短令牌优先命中
                for pe in range(payload_from, j + 1):
                    cand = (raw[i:head_end] + "." +
                            raw[payload_from:pe] + "." +
                            raw[sig_start:se])
                    if not (_MIN_TOKEN_LEN <= len(cand) <= _MAX_TOKEN_LEN):
                        continue
                    if cand not in seen:
                        seen.add(cand)
                        out.append(cand)
                # 标准长度已试过，末位兜底只需再试一次
                if se == len(raw):
                    break
    return out


def _resolve_user(db: Session, request: Request, creds: Optional[HTTPAuthorizationCredentials]) -> User:
    """解析令牌并返回当前用户。

    令牌来源按可靠性排序：
      1. X-Auth-Token —— 自定义头。部分网关会改写 Authorization 头（追加自己的
         凭据），使标准头中的令牌被污染而验签失败；自定义头不受此影响。
      2. Authorization —— 标准做法，本地与直连部署时走这条路径。
      3. 候选枚举 —— 前两者都失败时，尝试从被改写的头中还原令牌。
    """
    # 1) 自定义头：内容未被改写，直接验签
    payload = None
    custom = (request.headers.get("x-auth-token") or "").strip()
    if custom:
        try:
            payload = decode_token(custom)
        except Exception:
            payload = None

    raw = request.headers.get("authorization") or ""

    # 2) 标准头：格式规范时直接验签
    if payload is None:
        parts = raw.split()
        cand = None
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].count(".") == 2:
            cand = parts[1]
        elif len(parts) == 1 and parts[0].count(".") == 2:
            cand = parts[0]
        if cand:
            try:
                payload = decode_token(cand)
            except Exception:
                payload = None

    # 3) 回退：头被网关改写，枚举候选并以验签结果为判据
    if payload is None and raw:
        for c in _candidate_tokens(raw):
            try:
                payload = decode_token(c)
                break
            except Exception:
                continue

    if payload is None:
        if not raw and not custom:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="未提供认证令牌，请先登录")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期，请重新登录")

    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被禁用")
    return user


def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    return _resolve_user(db, request, creds)


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