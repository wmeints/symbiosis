"""JSON Web Token validation."""

import os
import time

import jwt
import requests
from jwt import PyJWKClient


class TokenValidator:
    """Implementation of JWT validation using OIDC configuration."""

    _discovery_url: str
    _oidc_config: dict | None
    _config_last_fetch: float | None
    _config_ttl: int
    _jwk_client: PyJWKClient | None
    _expected_audience: str | None
    _expected_issuer: str | None

    def __init__(
        self, discovery_url: str, timeout: int = 3, config_ttl: int = 3600
    ) -> None:
        """Initialize the TokenValidator with the OIDC discovery URL.

        Parameters
        ----------
        discovery_url : str
            The OIDC discovery URL.
        timeout : int, optional
            Timeout in seconds for HTTP requests, by default 3.
        config_ttl : int, optional
            Time-to-live in seconds for cached OIDC configuration, by default 3600.
        """
        self._discovery_url = discovery_url
        self._timeout = timeout
        self._config_ttl = config_ttl
        self._oidc_config = None
        self._config_last_fetch = None
        self._jwk_client = None
        self._expected_audience = os.getenv("OIDC_EXPECTED_AUDIENCE")
        self._expected_issuer = None  # Will be set from OIDC config

    def _get_oidc_config(self) -> dict:
        """Get the OIDC configuration, using cache if available.

        Returns
        -------
        dict
            The OIDC configuration.

        Raises
        ------
        ValueError
            If the OIDC configuration cannot be fetched.
        """
        now = time.time()
        if (
            self._oidc_config is None
            or self._config_last_fetch is None
            or now - self._config_last_fetch > self._config_ttl
        ):
            try:
                response = requests.get(self._discovery_url, timeout=self._timeout)
                response.raise_for_status()
                self._oidc_config = response.json()
                self._config_last_fetch = now

                # Set expected issuer from OIDC config
                self._expected_issuer = self._oidc_config.get("issuer")
            except requests.RequestException as err:
                error_msg = "Failed to fetch OIDC configuration"
                raise ValueError(error_msg) from err

        return self._oidc_config

    def validate(self, token: str) -> dict:
        """Validate a token and return the payload.

        Parameters
        ----------
        token : str
            The JWT token to validate.

        Returns
        -------
        dict
            The payload of the validated token.

        Raises
        ------
        ValueError
            If the OIDC configuration is invalid.
        jwt.InvalidTokenError
            If the token is invalid or expired.
        """
        oidc_config = self._get_oidc_config()
        signing_algorithms = oidc_config.get(
            "id_token_signing_alg_values_supported", []
        )
        jwks_uri = oidc_config.get("jwks_uri")

        if not jwks_uri:
            error_msg = "JWKS URI not found in OIDC configuration."
            raise ValueError(error_msg)

        # Reuse PyJWKClient instance
        if self._jwk_client is None:
            self._jwk_client = PyJWKClient(jwks_uri)

        signing_key = self._jwk_client.get_signing_key_from_jwt(token)

        # Decode and return only the payload (claims)
        decode_options = {
            "verify_exp": True,
            "verify_aud": bool(self._expected_audience),
            "verify_iss": bool(self._expected_issuer),
        }

        decode_kwargs = {
            "jwt": token,
            "key": signing_key.key,
            "algorithms": signing_algorithms,
            "options": decode_options,
        }

        # Add audience if configured
        if self._expected_audience:
            decode_kwargs["audience"] = self._expected_audience

        # Add issuer if available from OIDC config
        if self._expected_issuer:
            decode_kwargs["issuer"] = self._expected_issuer

        return jwt.decode(**decode_kwargs)
