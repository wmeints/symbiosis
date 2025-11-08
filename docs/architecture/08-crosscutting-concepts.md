# Crosscutting Concepts

This section describes concepts that are relevant across multiple parts of the system.

## Testing

### Authentication Testing with Fixtures

When testing request handlers that require an authenticated user, we use pytest fixtures that provide a complete Keycloak testcontainer environment. This approach ensures tests run against a real OIDC provider without requiring manual setup or external services.

#### Available Fixtures

The authentication testing infrastructure provides three main fixtures in `tests/conftest.py`:

##### 1. `keycloak` (session-scoped)

Starts a Keycloak testcontainer once per test session with a fully configured environment:

- **Realm**: `symbiosis` - A dedicated realm for testing
- **Client**: `integration` - A public client configured for direct access grants
- **User**: `test-user` (password: `test-password`) - A test user with email `test-user@example.com`

**Returns**: `KeycloakFixture` object containing:
- `admin_client`: Keycloak admin client for additional configuration
- `base_url`: Keycloak server URL
- `realm_name`: The realm name ("symbiosis")
- `client_id`: The client ID ("integration")
- `client_secret`: The client secret (None for public clients)
- `username`: Test user username ("test-user")
- `password`: Test user password ("test-password")
- `discovery_url`: OIDC discovery URL (property)
- `token_url`: Token endpoint URL (property)

**Example**:
```python
def test_with_keycloak_config(keycloak):
    # Access Keycloak configuration
    assert keycloak.realm_name == "symbiosis"
    assert keycloak.username == "test-user"

    # Use discovery URL for TokenValidator
    validator = TokenValidator(discovery_url=keycloak.discovery_url)
```

##### 2. `access_token` (function-scoped)

Obtains a fresh JWT access token for each test using the password grant flow. The token is issued for `test-user` and is valid for authentication.

**Returns**: `str` - A valid JWT access token

**Example**:
```python
def test_protected_endpoint(access_token):
    response = requests.get(
        "http://localhost:8000/api/protected",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
```

##### 3. `token_validator` (function-scoped)

Provides a `TokenValidator` instance configured with the Keycloak testcontainer's discovery URL. Use this to override the production `TokenValidator` dependency in tests.

**Returns**: `TokenValidator` - Configured for the test Keycloak instance

**Example**:
```python
def test_authenticated_endpoint(access_token, token_validator):
    app = FastAPI()

    # Override the TokenValidator dependency
    app.dependency_overrides[get_token_validator] = lambda: token_validator

    @app.get("/protected")
    def protected_route(user: AuthenticatedUser = Depends(authenticated_user)):
        return {"user": user.claims}

    client = TestClient(app)
    response = client.get(
        "/protected",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
```

#### How the Fixtures Work

1. **Container Lifecycle**: The `keycloak` fixture is session-scoped, meaning the Keycloak container starts once when the test session begins and is reused across all tests. This significantly improves test performance.

2. **Token Acquisition**: The `access_token` fixture is function-scoped, ensuring each test gets a fresh token. It uses the password grant flow to authenticate as `test-user` and retrieves an access token from the Keycloak testcontainer.

3. **Dependency Injection**: The `token_validator` fixture provides a properly configured `TokenValidator` that can be used to override the production dependency. This allows testing with real JWT validation against the testcontainer.

4. **Cleanup**: The Keycloak container is automatically stopped when the test session ends, ensuring no resources are leaked.

#### Usage Patterns

**Testing an authenticated endpoint**:
```python
def test_user_profile(access_token, token_validator):
    """Test accessing user profile with valid authentication."""
    app = FastAPI()
    app.dependency_overrides[get_token_validator] = lambda: token_validator

    @app.get("/profile")
    def get_profile(user: AuthenticatedUser = Depends(authenticated_user)):
        return {"username": user.claims.get("preferred_username")}

    client = TestClient(app)
    response = client.get(
        "/profile",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    assert response.json()["username"] == "test-user"
```

**Testing token validation**:
```python
def test_token_validation(access_token, keycloak):
    """Test that TokenValidator correctly validates tokens."""
    validator = TokenValidator(discovery_url=keycloak.discovery_url)

    claims = validator.validate(access_token)

    assert claims["preferred_username"] == "test-user"
    assert claims["email"] == "test-user@example.com"
```

**Creating additional test users**:
```python
def test_with_custom_user(keycloak):
    """Test with a custom user created during the test."""
    # Use the admin client to create additional users
    keycloak.admin_client.create_user(
        payload={
            "username": "admin-user",
            "enabled": True,
            "credentials": [{
                "type": "password",
                "value": "admin-password",
                "temporary": False
            }]
        }
    )

    # Obtain token for the new user
    response = requests.post(
        keycloak.token_url,
        data={
            "grant_type": "password",
            "client_id": keycloak.client_id,
            "username": "admin-user",
            "password": "admin-password"
        }
    )

    assert response.status_code == 200
```

#### Best Practices

1. **Use `access_token` for most tests**: The `access_token` fixture provides a ready-to-use token for testing authenticated endpoints.

2. **Override dependencies properly**: When testing FastAPI routes, always use `app.dependency_overrides` to inject the test `token_validator`.

3. **Don't restart containers**: Since the Keycloak fixture is session-scoped, avoid actions that would require restarting it. Use the admin client to configure additional resources instead.

4. **Clean up test data**: If you create additional users or clients during tests, consider cleaning them up in a teardown phase to avoid test pollution.

5. **Test both success and failure cases**: Use the fixtures to test both valid tokens (using `access_token`) and invalid scenarios (expired tokens, malformed tokens, etc.).

## Authentication and Authorization

### Token-Based Authentication

The gateway uses JWT (JSON Web Token) based authentication following the OpenID Connect (OIDC) standard. All authenticated requests must include a valid Bearer token in the Authorization header.

#### TokenValidator

The `TokenValidator` class (`src/symbiosis/auth/validation.py`) validates JWT tokens against an OIDC provider:

1. Fetches OIDC configuration from the discovery URL
2. Retrieves signing keys from the JWKS endpoint
3. Validates the token signature and claims
4. Returns the decoded claims if valid

**Configuration**: The validator requires an `OIDC_DISCOVERY_URL` environment variable pointing to the OIDC provider's discovery endpoint.

#### authenticated_user Dependency

The `authenticated_user` function (`src/symbiosis/auth/__init__.py`) is a FastAPI dependency that:

1. Extracts the Bearer token from the Authorization header
2. Validates the token using `TokenValidator`
3. Returns an `AuthenticatedUser` object containing the JWT claims
4. Raises HTTP 401 if the token is invalid

**Usage in routes**:
```python
from fastapi import Depends
from symbiosis.auth import authenticated_user, AuthenticatedUser

@app.get("/protected")
def protected_route(user: AuthenticatedUser = Depends(authenticated_user)):
    return {"username": user.claims.get("preferred_username")}
```

### Dependency Injection

The authentication system uses FastAPI's dependency injection to allow easy testing and configuration:

- **Production**: `get_token_validator()` reads the OIDC discovery URL from environment variables
- **Testing**: Tests override `get_token_validator` to use a testcontainer-configured validator

This pattern ensures production code can authenticate against a real OIDC provider while tests run against a controlled testcontainer environment.
