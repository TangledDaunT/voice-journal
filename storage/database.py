"""
Stage 8: SQLite Storage for searchable index.
Provides fast querying of conversation metadata and transcripts.
"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Any

from ..config.settings import Config
from ..conversation.grouping import ConversationUnit
from ..llm_output.classifier import ClassificationResult
from ..utils.logger import logger, log_stage


# SQL schema for conversations table
SCHEMA_CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER UNIQUE,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    participants TEXT NOT NULL,  -- JSON array
    source_type TEXT NOT NULL,
    is_shivangi_conversation INTEGER NOT NULL,
    quality TEXT NOT NULL,
    languages TEXT NOT NULL,  -- JSON array
    summary TEXT,
    transcript TEXT,
    slug TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_date ON conversations(date);
CREATE INDEX IF NOT EXISTS idx_conversations_source_type ON conversations(source_type);
CREATE INDEX IF NOT EXISTS idx_conversations_quality ON conversations(quality);
CREATE INDEX IF NOT EXISTS idx_conversations_shivangi ON conversations(is_shivangi_conversation);
"""

# FTS5 virtual table for full-text search
SCHEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
    summary,
    transcript,
    content='conversations',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
    INSERT INTO conversations_fts(rowid, summary, transcript)
    VALUES (new.id, new.summary, new.transcript);
END;

CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, summary, transcript)
    VALUES('delete', old.id, old.summary, old.transcript);
END;

CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, summary, transcript)
    VALUES('delete', old.id, old.summary, old.transcript);
    INSERT INTO conversations_fts(rowid, summary, transcript)
    VALUES (new.id, new.summary, new.transcript);
END;
"""


@dataclass
class ConversationRecord:
    """Database record for a conversation."""
    id: int
    conversation_id: int
    date: str
    start_time: str
    end_time: str
    duration_seconds: int
    participants: List[str]
    source_type: str
    is_shivangi_conversation: bool
    quality: str
    languages: List[str]
    summary: str
    transcript: str
    slug: str
    created_at: str
    updated_at: str


class SQLiteStore:
    """
    Stage 8: SQLite database for searchable conversation index.
    Maintains FTS5 index for fast text search.
    """

    def __init__(self, config: Config):
        self.config = config
        self.db_path = Path(config.database.path)

        # Create directory if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

        logger.info(f"SQLite initialized: {self.db_path}")

    @contextmanager
    def get_connection(self):
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create tables
            cursor.executescript(SCHEMA_CONVERSATIONS)

            # Create FTS if enabled
            if self.config.database.enable_fts:
                cursor.executescript(SCHEMA_FTS)

            log_stage("SQLite", "Database initialized")

    def insert_conversation(
        self,
        conversation: ConversationUnit,
        classification: ClassificationResult,
        note_path: Path
    ) -> int:
        """
        Insert a conversation into the database.

        Returns:
            Row ID of inserted record
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Prepare data
            data = {
                'conversation_id': conversation.conversation_id,
                'date': conversation.start_time.strftime("%Y-%m-%d"),
                'start_time': conversation.start_time.strftime("%H:%M:%S"),
                'end_time': conversation.end_time.strftime("%H:%M:%S"),
                'duration_seconds': int(conversation.duration_seconds),
                'participants': json.dumps(list(conversation.participants)),
                'source_type': classification.source_type,
                'is_shivangi_conversation': 1 if classification.is_shivangi_conversation else 0,
                'quality': classification.quality,
                'languages': json.dumps(sorted(list(conversation.languages))),
                'summary': classification.summary,
                'transcript': conversation.full_transcript,
                'slug': note_path.stem if note_path else ""
            }

            # Check for duplicates
            cursor.execute(
                "SELECT id FROM conversations WHERE conversation_id = ?",
                (data['conversation_id'],)
            )
            if cursor.fetchone():
                logger.warning(f"Conversation {data['conversation_id']} already exists")
                return -1

            # Insert
            cursor.execute("""
                INSERT INTO conversations (
                    conversation_id, date, start_time, end_time,
                    duration_seconds, participants, source_type,
                    is_shivangi_conversation, quality, languages,
                    summary, transcript, slug
                ) VALUES (
                    :conversation_id, :date, :start_time, :end_time,
                    :duration_seconds, :participants, :source_type,
                    :is_shivangi_conversation, :quality, :languages,
                    :summary, :transcript, :slug
                )
            """, data)

            row_id = cursor.lastrowid

            log_stage("SQLite", f"Inserted conversation #{conversation.conversation_id}")

            return row_id

    def get_conversation(self, conversation_id: int) -> Optional[ConversationRecord]:
        """Get a conversation by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
                (conversation_id,)
            )
            row = cursor.fetchone()

            if row:
                return self._row_to_record(row)
            return None

    def search_conversations(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[ConversationRecord]:
        """
        Full-text search across conversations.
        """
        if not self.config.database.enable_fts:
            logger.warning("FTS not enabled, falling back to LIKE search")
            return self._like_search(query, limit, offset)

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # FTS5 search
            cursor.execute("""
                SELECT c.*
                FROM conversations c
                JOIN conversations_fts fts ON c.id = fts.rowid
                WHERE conversations_fts MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?
            """, (query, limit, offset))

            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    def _like_search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[ConversationRecord]:
        """Fallback LIKE search when FTS is disabled."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            search_term = f"%{query}%"
            cursor.execute("""
                SELECT * FROM conversations
                WHERE summary LIKE ? OR transcript LIKE ?
                ORDER BY date DESC, start_time DESC
                LIMIT ? OFFSET ?
            """, (search_term, search_term, limit, offset))

            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_by_date(
        self,
        date: str,
        limit: int = 100
    ) -> List[ConversationRecord]:
        """Get all conversations for a specific date (YYYY-MM-DD)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM conversations
                WHERE date = ?
                ORDER BY start_time ASC
                LIMIT ?
            """, (date, limit))

            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_by_participant(
        self,
        participant: str,
        days: int = 30,
        limit: int = 100
    ) -> List[ConversationRecord]:
        """Get recent conversations with a specific participant."""
        from datetime import datetime, timedelta

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            # SQLite JSON functions for array search
            cursor.execute("""
                SELECT * FROM conversations
                WHERE date >= ?
                AND participants LIKE ?
                ORDER BY date DESC, start_time DESC
                LIMIT ?
            """, (start_date, f'%{participant}%', limit))

            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_by_quality(
        self,
        quality: str,
        days: int = 30,
        limit: int = 100
    ) -> List[ConversationRecord]:
        """Get recent conversations with specific quality rating."""
        from datetime import datetime, timedelta

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM conversations
                WHERE date >= ?
                AND quality = ?
                AND source_type = 'live_conversation'
                ORDER BY date DESC, start_time DESC
                LIMIT ?
            """, (start_date, quality, limit))

            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get statistics for recent conversations."""
        from datetime import datetime, timedelta

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total conversations
            cursor.execute("""
                SELECT COUNT(*) FROM conversations WHERE date >= ?
            """, (start_date,))
            total = cursor.fetchone()[0]

            # By source type
            cursor.execute("""
                SELECT source_type, COUNT(*) as count
                FROM conversations
                WHERE date >= ?
                GROUP BY source_type
            """, (start_date,))
            by_type = {row[0]: row[1] for row in cursor.fetchall()}

            # With Shivangi
            cursor.execute("""
                SELECT COUNT(*) FROM conversations
                WHERE date >= ? AND is_shivangi_conversation = 1
            """, (start_date,))
            with_shivangi = cursor.fetchone()[0]

            # Quality distribution
            cursor.execute("""
                SELECT quality, COUNT(*) as count
                FROM conversations
                WHERE date >= ? AND source_type = 'live_conversation'
                GROUP BY quality
            """, (start_date,))
            by_quality = {row[0]: row[1] for row in cursor.fetchall()}

            return {
                'days': days,
                'total': total,
                'by_type': by_type,
                'with_shivangi': with_shivangi,
                'by_quality': by_quality
            }

    def _row_to_record(self, row: sqlite3.Row) -> ConversationRecord:
        """Convert database row to ConversationRecord."""
        return ConversationRecord(
            id=row['id'],
            conversation_id=row['conversation_id'],
            date=row['date'],
            start_time=row['start_time'],
            end_time=row['end_time'],
            duration_seconds=row['duration_seconds'],
            participants=json.loads(row['participants']),
            source_type=row['source_type'],
            is_shivangi_conversation=bool(row['is_shivangi_conversation']),
            quality=row['quality'],
            languages=json.loads(row['languages']),
            summary=row['summary'],
            transcript=row['transcript'],
            slug=row['slug'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    def vacuum(self):
        """Vacuum the database to reclaim space."""
        with self.get_connection() as conn:
            conn.execute("VACUUM")
            log_stage("SQLite", "Database vacuumed")

    def get_all_ids(self) -> List[int]:
        """Get all conversation IDs (for sync checking)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT conversation_id FROM conversations")
            return [row[0] for row in cursor.fetchall()]


if __name__ == "__main__":
    # Quick test
    config = Config()
    config.database.path = "./test_data/test.db"

    store = SQLiteStore(config)
    print(f"Database: {store.db_path}")
    print("SQLite store ready")

    # Get stats
    stats = store.get_stats(days=30)
    print(f"\nStats: {stats}")
