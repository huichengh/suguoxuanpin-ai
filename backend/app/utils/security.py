"""安全工具：密码哈希与 JWT

实现说明：
令牌的签发与校验未使用 PyJWT，改为标准库 hmac + hashlib 手工实现 HS256。
原因：PyJWT 在部分部署环境下会出现「签名完全正确但校验抛
InvalidSignatureError」的情况，表现为登录成功后业务接口一律 401，
且用同一密钥在本地手工验签却通过。手工实现只依赖标准库，行为可预期，
不引入 cryptography 后端带来的环境差异。

安全等价性说明：
- 签名算法仍为 HS256，与原实现一致
- 校验步骤完整：格式 → 签名（常数时间比较）→ 算法声明 → 过期时间
- 使用 hmac.compare_digest 做常数时间比较，防时序侧信道
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import bcrypt

from ..config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES


def hash_password(plain: str) -> str:
    """bcrypt 哈希，密码绝不明文存储。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_access_token(data: dict) -> str:
    """签发 HS256 令牌。载荷中的 exp 为 UTC 秒级时间戳。"""
    payload = dict(data)
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = int(expire.timestamp())

    seg_h = _b64url_encode(
        json.dumps({"alg": ALGORITHM, "typ": "JWT"}, separators=(",", ":")).encode()
    )
    seg_p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())

    signing_input = f"{seg_h}.{seg_p}".encode()
    sig = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    return f"{seg_h}.{seg_p}.{_b64url_encode(sig)}"


def decode_token(token: str) -> dict:
    """校验并解码 HS256 令牌。校验失败或已过期时抛异常。"""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("令牌格式错误")

    seg_h, seg_p, seg_s = parts
    signing_input = f"{seg_h}.{seg_p}".encode()
    expected = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()

    if not hmac.compare_digest(_b64url_decode(seg_s), expected):
        raise ValueError("令牌签名无效")

    header = json.loads(_b64url_decode(seg_h))
    if header.get("alg") != ALGORITHM:
        raise ValueError("令牌算法不匹配")

    payload = json.loads(_b64url_decode(seg_p))
    exp = payload.get("exp")
    if exp is not None and int(exp) < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("令牌已过期")

    return payload
