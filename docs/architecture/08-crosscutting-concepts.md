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

## Database Migrations

### Overview

The gateway uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations. Alembic is integrated with SQLModel to provide automatic migration generation based on model changes and manual migration support for complex schema changes.

### Configuration

#### Database Connection

The database connection string is read from the `DATABASE_URL` environment variable. This variable must be set before running migrations or starting the application.

**Format**: `postgresql://user:password@host:port/database`

**Example**:
```bash
export DATABASE_URL="postgresql://symbiosis:password@localhost:5432/symbiosis"
```

#### Alembic Configuration Files

The migration system consists of several key files:

- **`alembic.ini`**: Main Alembic configuration file. Configured to use `DATABASE_URL` from environment variables.
- **`alembic/env.py`**: Alembic environment configuration. Imports SQLModel metadata and configures both online and offline migration modes.
- **`alembic/versions/`**: Directory containing migration scripts. Each migration is versioned and tracked.
- **`src/symbiosis/database.py`**: Database configuration module that exports SQLModel metadata for use by Alembic.

#### Ruff Integration

Migration scripts are automatically formatted using Ruff through Alembic's post-write hooks. This ensures all generated migration files follow the project's code style guidelines.

### Running Migrations

#### Upgrade to Latest Version

To apply all pending migrations and upgrade the database to the latest schema:

```bash
symbiosis database migrate
```

This command:
1. Verifies the `DATABASE_URL` environment variable is set
2. Runs all pending migrations in order
3. Updates the `alembic_version` table to track the current schema version
4. Provides clear error messages if migrations fail

**Note**: The migrate command always upgrades to the latest version (`head` in Alembic terminology).

### Creating New Migrations

When you add, modify, or remove SQLModel models, you need to create a migration to update the database schema.

#### Auto-generating Migrations

Alembic can automatically detect changes to SQLModel models and generate migrations:

```bash
uv run alembic revision --autogenerate -m "description of changes"
```

**Example**:
```bash
uv run alembic revision --autogenerate -m "add projects table"
```

This will:
1. Compare current SQLModel metadata with the database schema
2. Generate a new migration file in `alembic/versions/`
3. Automatically format the migration file using Ruff
4. Include upgrade and downgrade functions

#### Manual Migrations

For complex changes that Alembic cannot auto-detect (like data migrations, custom indexes, or stored procedures), create a manual migration:

```bash
uv run alembic revision -m "description of changes"
```

Then edit the generated migration file to add your custom upgrade and downgrade logic.

### Migration Files

Each migration file contains:

- **Revision identifier**: Unique ID for this migration
- **Parent revision**: Previous migration in the chain
- **Upgrade function**: SQL or Python code to apply the migration
- **Downgrade function**: SQL or Python code to reverse the migration

**Example migration**:
```python
"""add projects table

Revision ID: abc123def456
Revises:
Create Date: 2025-11-09 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision = 'abc123def456'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('projects')
```

### Best Practices

1. **Always review auto-generated migrations**: Alembic's auto-detection is not perfect. Review generated migrations before applying them, especially for column renames or complex changes.

2. **Test migrations before deployment**: Run migrations against a test database first to ensure they work correctly and don't cause data loss.

3. **Write reversible migrations**: Always implement both `upgrade()` and `downgrade()` functions. This allows rolling back changes if needed.

4. **Use descriptive migration messages**: Migration messages should clearly describe what the migration does (e.g., "add user roles table" not "update schema").

5. **One logical change per migration**: Keep migrations focused on a single logical change. This makes them easier to understand, review, and rollback if needed.

6. **Never modify existing migrations**: Once a migration has been applied to a production database, never modify it. Create a new migration to make additional changes.

7. **Coordinate with deployments**: Ensure database migrations are run before deploying new application code that depends on schema changes.

8. **Use transactions for safety**: Alembic runs migrations within transactions by default (for databases that support DDL transactions). This ensures migrations either complete fully or rollback entirely.

### Integration with SQLModel

The migration system is tightly integrated with SQLModel:

- **Metadata Export**: `src/symbiosis/database.py` exports `SQLModel.metadata`, which contains all table definitions from SQLModel models.
- **Auto-detection**: Alembic uses this metadata to compare against the current database schema and detect changes.
- **Model-First Approach**: Define your schema using SQLModel models, then generate migrations to sync the database.

**Workflow**:
1. Create or modify SQLModel models in the application
2. Generate a migration using `alembic revision --autogenerate`
3. Review and test the generated migration
4. Run `symbiosis database migrate` to apply the migration
5. Commit the migration file to version control

### Environment Variables

The following environment variable is required for database operations:

- **`DATABASE_URL`**: PostgreSQL connection string in the format `postgresql://user:password@host:port/database`

**Security Note**: Never commit database credentials to version control. Use environment variables or secrets management in production.
