import os
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Clé partagée avec le user-service : les jetons se vérifient ici, sans appel réseau.
JWT_SECRET = os.environ["JWT_SECRET"]  # absente : le service refuse de démarrer
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET trop courte : 32 caractères minimum")

bearer = HTTPBearer(auto_error=False)


def current_user_id(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> int:
    """Id de l'utilisateur du jeton émis par le user-service, sinon 401."""
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
