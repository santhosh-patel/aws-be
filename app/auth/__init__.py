"""
Authentication & User Management Routes
Simple token-based auth with MongoDB user storage.
"""
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# ─── Schemas ─────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False

class LoginResponse(BaseModel):
    token: str
    user: dict

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class SettingsUpdate(BaseModel):
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    aws_region: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    enabled_tools: Optional[List[str]] = None
    system_prompt: Optional[str] = None

# ─── Helpers ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password with bcrypt (salted)."""
    import bcrypt
    # bcrypt truncates at 72 bytes; encode and truncate to avoid issues
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12)).decode("ascii")

def verify_password(plain: str, stored: str) -> bool:
    """Verify a password against stored hash. Supports bcrypt and legacy SHA-256."""
    if not stored:
        return False
    if stored.startswith("$2") or stored.startswith("$2a") or stored.startswith("$2b"):
        import bcrypt
        pwd_bytes = plain.encode("utf-8")[:72]
        try:
            return bcrypt.checkpw(pwd_bytes, stored.encode("ascii"))
        except Exception:
            return False
    # Legacy SHA-256 (for migration)
    import hashlib
    return hashlib.sha256(plain.encode()).hexdigest() == stored

def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_hex(32)

# Default token TTL (days). Can be overridden via env AUTH_TOKEN_TTL_DAYS.
def _token_ttl_days() -> int:
    try:
        return int(os.environ.get("AUTH_TOKEN_TTL_DAYS", "7"))
    except ValueError:
        return 7

async def store_token(db, token: str, user_id: str, expires_at: datetime) -> None:
    """Persist a token in the database."""
    if db is None or not hasattr(db, "tokens"):
        return
    try:
        await db.tokens.insert_one({
            "token": token,
            "user_id": user_id,
            "expires_at": expires_at,
            "created_at": datetime.utcnow()
        })
    except Exception:
        pass

async def delete_token(db, token: str) -> bool:
    """Remove a token from the database. Returns True if a document was deleted."""
    if db is None or not hasattr(db, "tokens"):
        return False
    try:
        result = await db.tokens.delete_one({"token": token})
        return result.deleted_count > 0
    except Exception:
        return False

async def get_user_by_token(db, token: str) -> Optional[dict]:
    """Look up a user by their auth token (from DB; checks expiry)."""
    from bson import ObjectId
    if db is None:
        return None
    now = datetime.utcnow()
    try:
        if hasattr(db, "tokens"):
            doc = await db.tokens.find_one({"token": token})
            if not doc:
                return None
            expires_at = doc.get("expires_at")
            if expires_at:
                if isinstance(expires_at, str):
                    try:
                        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    except ValueError:
                        return None
                if expires_at < now:
                    await delete_token(db, token)
                    return None
            user_id = str(doc.get("user_id", ""))
        else:
            user_id = _active_tokens.get(token)
        if not user_id:
            return None
        try:
            uid = ObjectId(user_id)
        except Exception:
            uid = user_id
        user = await db.users.find_one({"_id": uid})
        if not user:
            return None
        user["_id"] = str(user["_id"])
        return user
    except Exception:
        return None

# In-memory token store (fallback when DB has no tokens collection; maps token → user_id)
_active_tokens: Dict[str, str] = {}

# ─── DB Seeding ──────────────────────────────────────────────────────────────

async def seed_users(db):
    """Seed default users if they don't exist."""
    default_users = [
        {
            "email": "user@enculture.ai",
            "password_hash": hash_password("Test@1234"),
            "name": "User",
            "role": "USER",
            "avatar_url": "",
            "settings": {
                "aws_access_key": "",
                "aws_secret_key": "",
                "aws_region": "us-east-1",
                "openai_api_key": "",
                "openai_model": "gpt-4o",
                "enabled_tools": [],
                "system_prompt": ""
            },
            "created_at": datetime.utcnow()
        },
        {
            "email": "admin@enculture.ai",
            "password_hash": hash_password("Test@1234"),
            "name": "Admin",
            "role": "ADMIN",
            "avatar_url": "",
            "settings": {
                "aws_access_key": "",
                "aws_secret_key": "",
                "aws_region": "us-east-1",
                "openai_api_key": "",
                "openai_model": "gpt-4o",
                "enabled_tools": [],
                "system_prompt": ""
            },
            "created_at": datetime.utcnow()
        }
    ]
    for user_data in default_users:
        existing = await db.users.find_one({"email": user_data["email"]})
        if not existing:
            await db.users.insert_one(user_data)
            print(f"[OK] Seeded user: {user_data['email']}")
        else:
            print(f"  User exists: {user_data['email']}")
