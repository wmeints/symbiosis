"""JSON Web Token validation."""

import jwt
import requests
from jwt import PyJWKClient


class TokenValidator:
    """Implementation of JWT validation using OIDC configuration."""

    _discovery_url: str

    def __init__(self, discovery_url: str) -> None:
        """Initialize the TokenValidator with the OIDC discovery URL.

        Parameters
        ----------
        discovery_url : str
            The OIDC discovery URL.
        """
        self._discovery_url = discovery_url

    def validate(self, token: str) -> dict:
        """Validate a token and return the payload.

        Parameters
        ----------
        token : str
            The JWT token to validate.

        Returns
        -------
        dict
            The payload of the validated token or an error message.
        """
        oidc_config = requests.get(self._discovery_url, timeout=3).json()
        signing_algorithms = oidc_config.get(
            "id_token_signing_alg_values_supported", []
        )
        jwks_uri = oidc_config.get("jwks_uri")

        if not jwks_uri:
            error_msg = "JWKS URI not found in OIDC configuration."
            raise ValueError(error_msg)

        jwk_client = PyJWKClient(jwks_uri)
        signing_key = jwk_client.get_signing_key_from_jwt(token)

        # Decode and return only the payload (claims)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=signing_algorithms,
            options={"verify_aud": False},
        )
