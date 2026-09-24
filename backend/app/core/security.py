from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User

settings = get_settings()
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(days=1))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user_id(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        user_uuid = UUID(user_id)
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    # The token can be structurally valid (correct signature, not expired)
    # while still naming a user that no longer exists in this database —
    # e.g. an old token issued against a database that was since replaced
    # or reset (such as moving to a fresh Docker Postgres volume). Trusting
    # the token's `sub` claim without this check lets an orphaned user_id
    # sail through every endpoint until it finally trips a foreign-key
    # violation deep in an INSERT. Catch it here instead, as a clean 401 —
    # the frontend already treats 401 as "log in again" (see the response
    # interceptor in api/client.ts).
    exists = await db.execute(select(User.id).where(User.id == user_uuid))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=401,
            detail="Your session refers to an account that no longer exists. Please log in again.",
        )

    return user_uuid