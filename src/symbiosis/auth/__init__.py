"""Authentication middleware for the application."""

import os
from typing import Annotated
from jwt import InvalidTokenError
from pydantic import BaseModel, Field
from fastapi import HTTPException, Header, Depends
from symbiosis.auth.validation import TokenValidator


class AuthenticatedUser(BaseModel):
    """Represents an authenticated user.

    Attributes
    ----------
    claims : dict
        The JWT claims for the authenticated user.
    """

    claims: dict = Field(default_factory=dict)


def get_token_validator() -> TokenValidator:
    """Get a configured TokenValidator instance.

    This dependency provides a TokenValidator configured with the OIDC
    discovery URL from the environment variable OIDC_DISCOVERY_URL.

    Returns
    -------
    TokenValidator
        A configured token validator instance.

    Raises
    ------
    ValueError
        If OIDC_DISCOVERY_URL environment variable is not set.
    """
    discovery_url = os.getenv("OIDC_DISCOVERY_URL")
    if not discovery_url:
        msg = "OIDC_DISCOVERY_URL environment variable is not set"
        raise ValueError(msg)
    return TokenValidator(discovery_url=discovery_url)


def authenticated_user(
    authorization: Annotated[str, Header()],
    token_validator: Annotated[TokenValidator, Depends(get_token_validator)],
) -> AuthenticatedUser:
    """Extract and validate the authenticated user from the request.

    Parameters
    ----------
    authorization : str
        The authorization header from the request.
    token_validator : TokenValidator
        The token validator instance (injected dependency).

    Returns
    -------
    AuthenticatedUser
        The authenticated user object.

    Raises
    ------
    HTTPException
        If the authorization header is missing or invalid.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = authorization[len("Bearer ") :]

    try:
        token_payload = token_validator.validate(token)
    except InvalidTokenError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err

    return AuthenticatedUser(claims=token_payload)
