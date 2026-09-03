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

from config.settings import Config
from conversation.grouping import ConversationUnit
from llm_output.classifier import ClassificationResult
from utils.logger import logger, log_stage


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
    raw_transcript TEXT,
    cleaned_transcript TEXT,
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
    raw_transcript,
    cleaned_transcript,
    content='conversations',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
    INSERT INTO conversations_fts(rowid, summary, raw_transcript, cleaned_transcript)
    VALUES (new.id, new.summary, new.raw_transcript, new.cleaned_transcript);
END;

CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, summary, raw_transcript, cleaned_transcript)
    VALUES('delete', old.id, old.summary, old.raw_transcript, old.cleaned_transcript);
END;

CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, summary, raw_transcript, cleaned_transcript)
    VALUES('delete', old.id, old.summary, old.raw_transcript, old.cleaned_transcript);
    INSERT INTO conversations_fts(rowid, summary, raw_transcript, cleaned_transcript)
    VALUES (new.id, new.summary, new.raw_transcript, new.cleaned_transcript);
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
    raw_transcript: str
    cleaned_transcript: str
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

            columns = {row[1] for row in cursor.execute("PRAGMA table_info(conversations)")}
            if "raw_transcript" not in columns:
                cursor.execute("ALTER TABLE conversations ADD COLUMN raw_transcript TEXT")
            if "cleaned_transcript" not in columns:
                cursor.execute("ALTER TABLE conversations ADD COLUMN cleaned_transcript TEXT")
            cursor.execute(
                "UPDATE conversations SET raw_transcript = COALESCE(raw_transcript, transcript), "
                "cleaned_transcript = COALESCE(cleaned_transcript, transcript)"
            )

            # Create FTS if enabled
            if self.config.database.enable_fts:
                fts_schema = cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE name = 'conversations_fts'"
                ).fetchone()
                fts_needs_migration = not fts_schema or not all(
                    column in fts_schema[0]
                    for column in ("raw_transcript", "cleaned_transcript")
                )
                if fts_needs_migration:
                    cursor.executescript("""
                        DROP TRIGGER IF EXISTS conversations_ai;
                        DROP TRIGGER IF EXISTS conversations_ad;
                        DROP TRIGGER IF EXISTS conversations_au;
                        DROP TABLE IF EXISTS conversations_fts;
                    """)
                    cursor.executescript(SCHEMA_FTS)
                try:
                    cursor.execute(
                        "INSERT INTO conversations_fts(conversations_fts) VALUES ('rebuild')"
                    )
                except sqlite3.DatabaseError:
                    logger.warning("Recreating malformed conversations FTS index")
                    cursor.executescript("""
                        DROP TRIGGER IF EXISTS conversations_ai;
                        DROP TRIGGER IF EXISTS conversations_ad;
                        DROP TRIGGER IF EXISTS conversations_au;
                        DROP TABLE IF EXISTS conversations_fts;
                    """)
                    cursor.executescript(SCHEMA_FTS)
                    cursor.execute(
                        "INSERT INTO conversations_fts(conversations_fts) VALUES ('rebuild')"
                    )

            log_stage("SQLite", "Database initialized")

    def insert_conversation(
        self,
        conversation: ConversationUnit,
        classification: ClassificationResult,
        note_path: Path,
        raw_transcript: Optional[str] = None,
        cleaned_transcript: Optional[str] = None
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
                'transcript': raw_transcript or conversation.full_transcript,
                'raw_transcript': raw_transcript or conversation.full_transcript,
                'cleaned_transcript': cleaned_transcript or raw_transcript or conversation.full_transcript,
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
                    summary, transcript, raw_transcript, cleaned_transcript, slug
                ) VALUES (
                    :conversation_id, :date, :start_time, :end_time,
                    :duration_seconds, :participants, :source_type,
                    :is_shivangi_conversation, :quality, :languages,
                    :summary, :transcript, :raw_transcript, :cleaned_transcript, :slug
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
            raw_transcript=row['raw_transcript'] or row['transcript'],
            cleaned_transcript=row['cleaned_transcript'] or row['transcript'],
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


# Backlog tracking schema
SCHEMA_BACKLOG = """
CREATE TABLE IF NOT EXISTS backlog_tracking (
    segment_id TEXT PRIMARY KEY,
    duration_seconds REAL NOT NULL,
    captured_at TEXT NOT NULL,
    processed_at TEXT,
    processing_attempts INTEGER DEFAULT 0,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_backlog_captured ON backlog_tracking(captured_at);
CREATE INDEX IF NOT EXISTS idx_backlog_processed ON backlog_tracking(processed_at);
"""

# Backlog summary table
SCHEMA_BACKLOG_SUMMARY = """
CREATE TABLE IF NOT EXISTS backlog_summary (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_hours REAL DEFAULT 0,
    segment_count INTEGER DEFAULT 0,
    last_updated TEXT NOT NULL,
    last_day_start_hours REAL DEFAULT 0,
    growth_warning BOOLEAN DEFAULT 0
);
"""


# Glossary schema (for Hindi/Hinglish terms)
SCHEMA_GLOSSARY = """
CREATE TABLE IF NOT EXISTS glossary_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_devanagari TEXT NOT NULL,
    term_romanized TEXT NOT NULL UNIQUE,
    first_seen_date TEXT NOT NULL,
    occurrence_count INTEGER DEFAULT 1,
    last_seen_date TEXT NOT NULL,
    inferred_meaning TEXT,
    example_transcript TEXT,
    conversation_ids TEXT,  -- JSON array
    is_validated INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_glossary_romanized ON glossary_terms(term_romanized);
CREATE INDEX IF NOT EXISTS idx_glossary_first_seen ON glossary_terms(first_seen_date);
"""


class GlossaryStore:
    """
    Manages glossary term storage and retrieval.
    """

    def __init__(self, config: Config):
        self.config = config
        self.db_path = Path(config.database.path)
        self._init_glossary_db()

    def _init_glossary_db(self):
        """Initialize glossary tables."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_GLOSSARY)
        conn.commit()
        conn.close()
        log_stage("SQLite", "Glossary tables initialized")

    def insert_term(self, term_data: dict) -> int:
        """Insert a glossary term."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO glossary_terms (
                term_devanagari, term_romanized, first_seen_date,
                occurrence_count, last_seen_date, inferred_meaning,
                example_transcript, conversation_ids, is_validated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            term_data['term_devanagari'],
            term_data['term_romanized'],
            term_data['first_seen_date'],
            term_data['occurrence_count'],
            term_data['last_seen_date'],
            term_data.get('inferred_meaning', ''),
            term_data.get('example_transcript', ''),
            json.dumps(term_data.get('conversation_ids', []))
        ))

        row_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return row_id

    def get_all_terms(self) -> List[Dict]:
        """Get all glossary terms."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM glossary_terms
            ORDER BY occurrence_count DESC, term_romanized ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_term(self, term_romanized: str) -> Optional[Dict]:
        """Get a specific term by romanized form."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM glossary_terms WHERE term_romanized = ?
        """, (term_romanized,))

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None


class BacklogTracker:
    """
    Tracks backlog depth and processing progress.
    Raises warnings when backlog grows instead of shrinking.
    """

    def __init__(self, config: Config):
        self.config = config
        self.db_path = Path(config.database.path)

        self._init_backlog_db()

    def _init_backlog_db(self):
        """Initialize backlog tables."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_BACKLOG)
        conn.executescript(SCHEMA_BACKLOG_SUMMARY)

        # Ensure summary row exists
        conn.execute("""
            INSERT OR IGNORE INTO backlog_summary (id, last_updated)
            VALUES (1, datetime('now'))
        """)
        conn.commit()
        conn.close()

    def add_segment(self, segment_id: str, duration_seconds: float):
        """Add a segment to the backlog."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO backlog_tracking
            (segment_id, duration_seconds, captured_at, processing_attempts)
            VALUES (?, ?, datetime('now'), 0)
        """, (segment_id, duration_seconds))

        # Update summary
        self._update_summary(conn)

        conn.commit()
        conn.close()

    def remove_segment(self, segment_id: str):
        """Mark a segment as processed (remove from backlog)."""
        conn = sqlite3.connect(self.db_path)

        conn.execute("""
            UPDATE backlog_tracking
            SET processed_at = datetime('now')
            WHERE segment_id = ?
        """, (segment_id,))

        # Update summary
        self._update_summary(conn)

        conn.commit()
        conn.close()

    def _update_summary(self, conn):
        """Update backlog summary and check for growth."""
        from datetime import datetime, timedelta

        # Calculate current total
        result = conn.execute("""
            SELECT COALESCE(SUM(duration_seconds), 0) / 3600.0,
                   COUNT(*)
            FROM backlog_tracking
            WHERE processed_at IS NULL
        """).fetchone()

        total_hours = result[0]
        segment_count = result[1]

        # Get previous day's hours
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        prev_result = conn.execute("""
            SELECT total_hours
            FROM backlog_summary
        """).fetchone()

        prev_hours = prev_result[0] if prev_result else 0

        # Check for growth
        growth_warning = False
        if prev_hours > 0 and total_hours > prev_hours:
            growth_warning = True
            logger.warning(
                f"Backlog growing: {total_hours:.1f}h (was {prev_hours:.1f}h yesterday)"
            )

        # Update summary
        conn.execute("""
            UPDATE backlog_summary SET
                total_hours = ?,
                segment_count = ?,
                last_updated = datetime('now'),
                growth_warning = ?
            WHERE id = 1
        """, (total_hours, segment_count, growth_warning))

    def get_status(self) -> Dict[str, Any]:
        """Get current backlog status."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Get summary
        summary = conn.execute("""
            SELECT * FROM backlog_summary WHERE id = 1
        """).fetchone()

        # Get oldest unprocessed segment
        oldest = conn.execute("""
            SELECT MIN(captured_at) as oldest
            FROM backlog_tracking
            WHERE processed_at IS NULL
        """).fetchone()

        conn.close()

        return {
            "total_hours": summary["total_hours"] if summary else 0,
            "segment_count": summary["segment_count"] if summary else 0,
            "estimated_cleanup_hours": (
                (summary["segment_count"] if summary else 0)
                * self.config.cleanup.estimated_seconds_per_conversation / 3600
            ),
            "estimated_processing_hours": (
                (summary["total_hours"] if summary else 0)
                + (summary["segment_count"] if summary else 0)
                * self.config.cleanup.estimated_seconds_per_conversation / 3600
            ),
            "estimated_audio_cache_mb": (
                (summary["total_hours"] if summary else 0)
                * self.config.dashboard.audio_bitrate_kbps * 0.45
            ),
            "last_updated": summary["last_updated"] if summary else None,
            "growth_warning": bool(summary["growth_warning"]) if summary else False,
            "oldest_segment": oldest["oldest"] if oldest and oldest["oldest"] else None,
            "overflow_threshold": self.config.scheduler.backlog_overflow_hours,
            "is_overflow": (summary["total_hours"] if summary else 0) >= self.config.scheduler.backlog_overflow_hours
        }


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

    # Test backlog tracker
    backlog = BacklogTracker(config)
    status = backlog.get_status()
    print(f"\nBacklog status: {status}")
