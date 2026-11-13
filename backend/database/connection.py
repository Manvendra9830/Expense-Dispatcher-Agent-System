"""
Database connection module.

Manages SQLAlchemy engine and session creation.
Includes automated backward-compatible schema migrations.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

from backend.utils.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class."""
    pass


# Create engine with SQLite-specific settings
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
    echo=False,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def migrate_db(target_engine=None) -> None:
    """
    Safely migrate receipts table to add Phase 2 columns without altering existing records.
    """
    eng = target_engine or engine
    try:
        with eng.connect() as conn:
            # Check if receipts table exists
            check_table = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='receipts'")
            ).fetchone()
            if not check_table:
                return

            result = conn.execute(text("PRAGMA table_info(receipts)")).fetchall()
            existing_cols = {row[1] for row in result}

            columns_to_add = [
                ("model_used", "VARCHAR(100)"),
                ("extraction_method", "VARCHAR(50) DEFAULT 'AI'"),
                ("fallback_used", "BOOLEAN DEFAULT 0"),
                ("fallback_reason", "TEXT"),
                ("processing_duration_ms", "INTEGER"),
            ]

            for col_name, col_def in columns_to_add:
                if col_name not in existing_cols:
                    logger.info(f"Migrating database: adding column '{col_name}' to receipts table.")
                    conn.execute(text(f"ALTER TABLE receipts ADD COLUMN {col_name} {col_def}"))
            conn.commit()
    except Exception as e:
        logger.warning(f"Database migration check encountered an issue: {e}")


def init_db(target_engine=None) -> None:
    """Initialize the database by creating all tables and running migrations."""
    eng = target_engine or engine
    from backend.database.models import Receipt, ReceiptItem  # noqa: F401
    Base.metadata.create_all(bind=eng)
    migrate_db(target_engine=eng)
    logger.info("Database initialized and verified successfully.")


def get_db() -> Session:
    """
    Get a database session. Used as a FastAPI dependency.

    Yields:
        SQLAlchemy Session instance.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
