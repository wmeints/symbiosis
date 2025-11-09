"""Symbiosis CLI module."""

import os
import sys
from typing import Annotated
from typer import Typer, Option
import uvicorn
from alembic.config import Config
from alembic import command

app = Typer(help="Symbiosis Gateway")
database_app = Typer(help="Database management commands")


@app.command()
def serve(
    port: Annotated[int, Option(help="The port to bind the server to")] = 4321, 
    address: Annotated[str, Option(help="The address to bind the server to")] = "127.0.0.1",  # noqa: E501
) -> None:
    """Start the Symbiosis Gateway server.

    Parameters
    ----------
    port : int
        The port to bind the server to.
    address : str
        The address to bind the server to.
    """
    uvicorn.run("symbiosis.server:app", host=address, port=port, reload=True)


@database_app.command()
def migrate() -> None:
    """Run database migrations to upgrade to the latest schema.

    This command applies all pending database migrations to bring the
    database schema up to date. The database connection string must be
    set in the DATABASE_URL environment variable.

    Raises
    ------
    ValueError
        If the DATABASE_URL environment variable is not set.
    SystemExit
        If the migration fails.
    """
    # Verify DATABASE_URL is set
    if not os.getenv("DATABASE_URL"):
        print("Error: DATABASE_URL environment variable is not set.")
        print("Please set it to your PostgreSQL connection string.")
        sys.exit(1)

    try:
        # Create Alembic configuration
        alembic_cfg = Config("alembic.ini")

        # Run migrations
        print("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        print("Database migrations completed successfully.")
    except Exception as e:
        print(f"Error running migrations: {e}")
        sys.exit(1)


# Register database subcommand
app.add_typer(database_app, name="database")


if __name__ == "__main__":
    app()
