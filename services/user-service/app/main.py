import datetime
import os
from contextlib import asynccontextmanager
from typing import Annotated

import bcrypt
import jwt
import pymysql
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from app.db import connect, get_conn, migrate

# Clé partagée avec le tournament-service, qui vérifie les jetons sans appeler ce service.
JWT_SECRET = os.environ["JWT_SECRET"]  # absente : le service refuse de démarrer
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET trop courte : 32 caractères minimum")
TOKEN_TTL = datetime.timedelta(hours=24)
# Comparé quand le compte n'existe pas : la réponse prend le même temps, qu'il existe ou non.
DUMMY_HASH = bcrypt.hashpw(b"compte-inconnu", bcrypt.gensalt())


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    try:
        migrate(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="user-service", lifespan=lifespan)
Conn = Annotated[pymysql.Connection, Depends(get_conn)]
bearer = HTTPBearer(auto_error=False)


class Register(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_-]{3,50}$")
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def bcrypt_limit(cls, v: str) -> str:
        if len(v.encode()) > 72:  # bcrypt refuse plus de 72 octets (un "é" en fait 2)
            raise ValueError("72 octets maximum")
        return v


class Login(BaseModel):
    username: str
    password: str


@app.get("/health")
def health() -> dict[str, str]:
    """Sonde liveness/readiness pour Kubernetes."""
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=201)
def register(data: Register, conn: Conn) -> dict:
    password_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
    with conn.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO app_user (username, email, password_hash) VALUES (%s, %s, %s)",
                (data.username, data.email, password_hash),
            )
        # La contrainte UNIQUE tranche : pas de course entre deux inscriptions simultanées.
        except pymysql.IntegrityError as e:
            raise HTTPException(409, "nom d'utilisateur ou e-mail déjà pris") from e
        conn.commit()
        return {"id": cur.lastrowid, "username": data.username, "email": data.email}


@app.post("/api/auth/login")
def login(data: Login, conn: Conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash FROM app_user WHERE username = %s",
            (data.username,),
        )
        user = cur.fetchone()
    password = data.password.encode()
    stored = user["password_hash"].encode() if user else DUMMY_HASH
    valid = len(password) <= 72 and bcrypt.checkpw(password, stored)
    if not user or not valid:
        raise HTTPException(401, "identifiants invalides")
    now = datetime.datetime.now(datetime.UTC)
    token = jwt.encode(
        {
            "sub": str(user["id"]),
            "username": user["username"],
            "iat": now,
            "exp": now + TOKEN_TTL,
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}


def current_user_id(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> int:
    """Id de l'utilisateur du jeton `Authorization: Bearer …`, sinon 401."""
    if creds is None:
        raise HTTPException(
            401, "jeton manquant", headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        claims = jwt.decode(
            creds.credentials,
            JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        return int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError) as e:
        raise HTTPException(
            401, "jeton invalide", headers={"WWW-Authenticate": "Bearer"}
        ) from e


@app.get("/api/auth/me")
def me(user_id: Annotated[int, Depends(current_user_id)], conn: Conn) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, email, created_at FROM app_user WHERE id = %s",
            (user_id,),
        )
        user = cur.fetchone()
    if not user:  # compte supprimé depuis l'émission du jeton
        raise HTTPException(401, "utilisateur inconnu")
    return user
