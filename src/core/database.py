import sqlite3
import os
from core.config import DB_PATH

# Schema adapted for SQLite
SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        "id" TEXT PRIMARY KEY,
        "identifier" TEXT NOT NULL UNIQUE,
        "metadata" TEXT NOT NULL,
        "createdAt" TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS threads (
        "id" TEXT PRIMARY KEY,
        "createdAt" TEXT,
        "name" TEXT,
        "userId" TEXT,
        "userIdentifier" TEXT,
        "tags" TEXT,
        "metadata" TEXT,
        FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS steps (
        "id" TEXT PRIMARY KEY,
        "name" TEXT NOT NULL,
        "type" TEXT NOT NULL,
        "threadId" TEXT NOT NULL,
        "parentId" TEXT,
        "streaming" BOOLEAN NOT NULL,
        "waitForAnswer" BOOLEAN,
        "isError" BOOLEAN,
        "metadata" TEXT,
        "tags" TEXT,
        "input" TEXT,
        "output" TEXT,
        "createdAt" TEXT,
        "command" TEXT,
        "start" TEXT,
        "end" TEXT,
        "generation" TEXT,
        "showInput" TEXT,
        "language" TEXT,
        "indent" INT,
        "defaultOpen" BOOLEAN,
        "autoCollapse" BOOLEAN DEFAULT 0,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS elements (
        "id" TEXT PRIMARY KEY,
        "threadId" TEXT,
        "type" TEXT,
        "url" TEXT,
        "chainlitKey" TEXT,
        "name" TEXT NOT NULL,
        "display" TEXT,
        "objectKey" TEXT,
        "size" TEXT,
        "page" INT,
        "language" TEXT,
        "forId" TEXT,
        "mime" TEXT,
        "props" TEXT,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS feedbacks (
        "id" TEXT PRIMARY KEY,
        "forId" TEXT NOT NULL,
        "threadId" TEXT NOT NULL,
        "value" INT NOT NULL,
        "comment" TEXT,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );
    """,
]


def initialize_database(db_path: str = str(DB_PATH)):
    """Checks and initializes the database schema, including migrations."""
    # Ensure the parent directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. Basic Table Initialization
        for statement in SCHEMA:
            cursor.execute(statement)

        # 2. Migrations (e.g., autoCollapse column)
        cursor.execute("PRAGMA table_info(steps)")
        columns = [column[1] for column in cursor.fetchall()]
        if "autoCollapse" not in columns:
            print("Migrating database: Adding autoCollapse column to steps table.")
            cursor.execute("ALTER TABLE steps ADD COLUMN autoCollapse BOOLEAN DEFAULT 0")

        conn.commit()
        conn.close()
        print(f"Database core initialized at: {db_path}")
    except Exception as e:
        print(f"FAILED to initialize database: {e}")
        raise e
