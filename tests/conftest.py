"""Pytest configuration and fixtures for Symbiosis Gateway tests."""

from dataclasses import dataclass

import pytest
import requests
from keycloak import KeycloakAdmin
from testcontainers.keycloak import KeycloakContainer

from symbiosis.auth.validation import TokenValidator


@dataclass
class KeycloakFixture:
    """Keycloak testcontainer fixture data."""

    admin_client: KeycloakAdmin
    base_url: str
    realm_name: str
    client_id: str
    client_secret: str
    username: str
    password: str

    @property
    def discovery_url(self) -> str:
        """Get the OIDC discovery URL for the test realm."""
        base = f"{self.base_url}/realms/{self.realm_name}"
        return f"{base}/.well-known/openid-configuration"

    @property
    def token_url(self) -> str:
        """Get the token endpoint URL for the test realm."""
        return f"{self.base_url}/realms/{self.realm_name}/protocol/openid-connect/token"


@pytest.fixture(scope="session")
def keycloak() -> KeycloakFixture:
    """
    Start a Keycloak testcontainer with a fully configured test environment.

    This fixture:
    - Starts a Keycloak container
    - Creates a 'symbiosis' realm
    - Creates an 'integration' client with credentials
    - Creates a 'test-user' with credentials

    The fixture is session-scoped, so the container is started once and
    reused across all tests in the session.

    Returns:
        KeycloakFixture: Object containing all necessary Keycloak connection details
    """
    # Start Keycloak container
    container = KeycloakContainer()
    container.start()

    try:
        # Get base URL and admin client
        base_url = container.get_url()
        admin_username = container.username
        admin_password = container.password

        # Create admin client for master realm
        admin_client = KeycloakAdmin(
            server_url=base_url,
            username=admin_username,
            password=admin_password,
            realm_name="master",
            verify=True,
        )

        # Create symbiosis realm
        realm_name = "symbiosis"
        admin_client.create_realm(
            payload={
                "realm": realm_name,
                "enabled": True,
                "displayName": "Symbiosis Test Realm",
            }
        )

        # Change to the symbiosis realm (admin stays authenticated to master)
        admin_client.change_current_realm(realm_name)

        # Create integration client as a public client (no secret needed)
        client_id = "integration"
        client_secret = None  # Public clients don't need secrets

        admin_client.create_client(
            payload={
                "clientId": client_id,
                "enabled": True,
                "redirectUris": ["http://localhost:*/*"],
                "webOrigins": ["*"],
                "standardFlowEnabled": True,
                "directAccessGrantsEnabled": True,
                "publicClient": True,  # Make it a public client
                "protocol": "openid-connect",
            },
            skip_exists=False,
        )

        # Create test user
        username = "test-user"
        password = "test-password"

        admin_client.create_user(
            payload={
                "username": username,
                "enabled": True,
                "email": "test-user@example.com",
                "firstName": "Test",
                "lastName": "User",
                "credentials": [
                    {
                        "type": "password",
                        "value": password,
                        "temporary": False,
                    }
                ],
            }
        )

        # Return fixture data
        yield KeycloakFixture(
            admin_client=admin_client,
            base_url=base_url,
            realm_name=realm_name,
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
        )

    finally:
        # Clean up: stop the container
        container.stop()


@pytest.fixture
def access_token(keycloak: KeycloakFixture) -> str:
    """
    Get a valid access token for the test user.

    This fixture obtains a fresh access token for each test using the
    password grant flow. The token is issued for the 'test-user' in the
    'symbiosis' realm using the 'integration' client.

    The fixture is function-scoped, so each test gets a fresh token.

    Args:
        keycloak: The session-scoped Keycloak fixture

    Returns:
        str: A valid JWT access token
    """
    # For public clients, we don't send a client secret
    response = requests.post(
        keycloak.token_url,
        data={
            "grant_type": "password",
            "client_id": keycloak.client_id,
            "username": keycloak.username,
            "password": keycloak.password,
        },
        timeout=10,
    )

    response.raise_for_status()

    token_data = response.json()
    return token_data["access_token"]


@pytest.fixture
def token_validator(keycloak: KeycloakFixture) -> TokenValidator:
    """
    Get a TokenValidator configured for the Keycloak testcontainer.

    This fixture provides a TokenValidator instance configured with the
    discovery URL from the Keycloak testcontainer. It can be used to
    override the default TokenValidator dependency in tests.

    The fixture is function-scoped to match typical test isolation needs.

    Args:
        keycloak: The session-scoped Keycloak fixture

    Returns:
        TokenValidator: A validator configured for the test Keycloak instance
    """
    return TokenValidator(discovery_url=keycloak.discovery_url)
