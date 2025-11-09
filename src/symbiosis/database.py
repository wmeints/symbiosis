"""Database configuration and connection management.

This module provides database configuration and connection management
for the Symbiosis Gateway. It creates a SQLAlchemy engine and exposes
SQLModel metadata for use with Alembic migrations.

The database connection string is read from the DATABASE_URL environment
variable.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel


def get_database_url() -> str:
    """Get the database URL from environment variables.

    Returns
    -------
    str
        The database connection URL.

    Raises
    ------
    ValueError
        If the DATABASE_URL environment variable is not set.
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        msg = (
            "DATABASE_URL environment variable is not set. "
            "Please set it to your PostgreSQL connection string."
        )
        raise ValueError(msg)

    return database_url


def create_db_engine() -> Engine:
    """Create and return a SQLAlchemy engine.

    Returns
    -------
    sqlalchemy.engine.Engine
        The database engine instance.
    """
    database_url = get_database_url()
    return create_engine(database_url, echo=False)


# Global engine instance (lazily initialized)
_engine: Engine | None = None


def get_engine() -> Engine:
    """Get or create the database engine.

    This function implements lazy initialization - the engine is only
    created when first requested, not at import time.

    Returns
    -------
    sqlalchemy.engine.Engine
        The database engine instance.
    """
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


# SQLModel metadata for Alembic
metadata = SQLModel.metadata
