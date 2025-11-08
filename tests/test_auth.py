"""Tests for authentication functionality."""

from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends

from symbiosis.auth import authenticated_user, get_token_validator, AuthenticatedUser
from symbiosis.auth.validation import TokenValidator


def test_authenticated_user_happy_flow(
    access_token: str, token_validator: TokenValidator
):
    """
    Test the happy flow for authenticated_user function.

    This test verifies that when a valid Bearer token is provided,
    the authenticated_user dependency correctly validates it and
    returns an AuthenticatedUser with the expected claims.

    Args:
        access_token: Valid JWT token from the Keycloak testcontainer
        token_validator: TokenValidator configured for the test Keycloak instance
    """
    # Create a test FastAPI app
    app = FastAPI()

    # Override the token validator dependency with our test fixture
    app.dependency_overrides[get_token_validator] = lambda: token_validator

    # Create a test endpoint that uses the authenticated_user dependency
    @app.get("/protected")
    def protected_endpoint(
        user: AuthenticatedUser = Depends(authenticated_user),  # noqa: B008
    ):
        return {"user": user.claims}

    # Create a test client
    client = TestClient(app)

    # Make a request with the Bearer token
    response = client.get(
        "/protected",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # Assert the response is successful
    assert response.status_code == 200

    # Get the returned user data (claims are now directly in user_data)
    claims = response.json()["user"]

    # Verify standard JWT claims exist
    assert "sub" in claims  # Subject (user ID)
    assert "exp" in claims  # Expiration time
    assert "iat" in claims  # Issued at time
    assert "aud" in claims  # Audience

    # Verify Keycloak-specific claims
    assert "preferred_username" in claims
    assert claims["preferred_username"] == "test-user"

    # Verify email is present (we set it in the Keycloak fixture)
    assert "email" in claims
    assert claims["email"] == "test-user@example.com"
