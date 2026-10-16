"""Durable segment provenance alongside the backward-compatible conversation schema."""

import csv
import hashlib
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from storage.database import SQLiteStore

IST = ZoneInfo("Asia/Kolkata")
CSV_FIELDS = ["date", "start_time", "end_time", "text", "language", "speaker", "engine"]
SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_segments (
    id TEXT PRIMARY KEY, conversation_id INTEGER, start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL, audio_path TEXT, clean_path TEXT, text_raw TEXT NOT NULL,
    raw_json TEXT NOT NULL, engine TEXT NOT NULL, model TEXT, status TEXT NOT NULL,
    language TEXT, imported INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS journal_segments_date ON journal_segments(start_ts);
CREATE TABLE IF NOT EXISTS groq_requests (
    id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, day TEXT NOT NULL,
    audio_seconds REAL NOT NULL, billed_seconds REAL NOT NULL,
    status TEXT NOT NULL, headers TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS service_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class JournalStore:
    def __init__(self, config):
        self.config = config
        self.path = Path(config.database.path)
        SQLiteStore(config)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(journal_segments)")}
            for name, kind in [("speaker_id", "TEXT"), ("speaker_similarity", "REAL")]:
                if name not in columns:
                    conn.execute(f"ALTER TABLE journal_segments ADD COLUMN {name} {kind}")
            self._migrate_membership(conn)

    def _migrate_membership(self, conn):
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='journal_segments'"
        ).fetchone()[0]
        if "INTEGER UNIQUE" not in sql:
            return
        # Transactional rebuild removes only the legacy one-card-per-segment constraint.
        conn.execute("ALTER TABLE journal_segments RENAME TO journal_segments_old")
        table_sql = SCHEMA.split(";")[0].replace("IF NOT EXISTS ", "")
        conn.execute(table_sql)
        conn.execute("ALTER TABLE journal_segments ADD COLUMN speaker_id TEXT")
        conn.execute("ALTER TABLE journal_segments ADD COLUMN speaker_similarity REAL")
        columns = ",".join(
            row[1] for row in conn.execute("PRAGMA table_info(journal_segments_old)")
        )
        conn.execute(
            f"INSERT INTO journal_segments ({columns}) SELECT {columns} FROM journal_segments_old"
        )
        conn.execute("DROP TABLE journal_segments_old")
        conn.execute("CREATE INDEX journal_segments_date ON journal_segments(start_ts)")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def has_segment(self, segment_id):
        with self.connect() as conn:
            return (
                conn.execute("SELECT 1 FROM journal_segments WHERE id=?", (segment_id,)).fetchone()
                is not None
            )

    def save(
        self,
        segment_id,
        start,
        end,
        text,
        raw,
        engine,
        model="",
        language="",
        status="ok",
        audio_path=None,
        clean_path=None,
        imported=False,
        speaker="unknown",
        speaker_id=None,
        speaker_similarity=None,
    ):
        start = start.replace(tzinfo=IST) if start.tzinfo is None else start.astimezone(IST)
        end = end.replace(tzinfo=IST) if end.tzinfo is None else end.astimezone(IST)
        cid = int.from_bytes(hashlib.sha256(segment_id.encode()).digest()[:6], "big")
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM journal_segments WHERE id=?", (segment_id,)).fetchone():
                return conn.execute(
                    "SELECT conversation_id FROM journal_segments WHERE id=?", (segment_id,)
                ).fetchone()[0]
            previous = None
            if not imported:
                previous = conn.execute("""SELECT j.*,c.date FROM journal_segments j
                    JOIN conversations c ON c.conversation_id=j.conversation_id
                    WHERE j.imported=0 AND j.engine!='imported'
                    ORDER BY j.end_ts DESC LIMIT 1""").fetchone()
            join = False
            if previous and previous["date"] == start.date().isoformat():
                gap = (start - datetime.fromisoformat(previous["end_ts"])).total_seconds()
                first = conn.execute(
                    "SELECT MIN(start_ts) FROM journal_segments WHERE conversation_id=?",
                    (previous["conversation_id"],),
                ).fetchone()[0]
                join = (
                    0 <= gap <= 12 and (end - datetime.fromisoformat(first)).total_seconds() <= 1800
                )
                if join:
                    cid = previous["conversation_id"]
            conn.execute(
                """INSERT OR IGNORE INTO conversations
                (conversation_id,date,start_time,end_time,duration_seconds,participants,source_type,
                 is_shivangi_conversation,quality,languages,summary,transcript,raw_transcript,cleaned_transcript,slug)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    cid,
                    start.date().isoformat(),
                    start.strftime("%H:%M:%S"),
                    end.strftime("%H:%M:%S"),
                    max(0, (end - start).total_seconds()),
                    json.dumps([speaker]),
                    "unknown",
                    0,
                    status,
                    json.dumps([language] if language else []),
                    None,
                    text,
                    text,
                    None,
                    "",
                ),
            )
            conn.execute(
                """INSERT INTO journal_segments
                (id,conversation_id,start_ts,end_ts,audio_path,clean_path,text_raw,raw_json,engine,model,status,language,imported)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    segment_id,
                    cid,
                    start.isoformat(),
                    end.isoformat(),
                    str(audio_path) if audio_path else None,
                    str(clean_path) if clean_path else None,
                    text,
                    json.dumps(dict(raw, journal_speaker=speaker), ensure_ascii=False),
                    engine,
                    model,
                    status,
                    language,
                    int(imported),
                ),
            )
            conn.execute(
                "UPDATE journal_segments SET speaker_id=?,speaker_similarity=? WHERE id=?",
                (speaker_id, speaker_similarity, segment_id),
            )
            if join:
                rows = conn.execute(
                    "SELECT * FROM journal_segments WHERE conversation_id=? ORDER BY start_ts,id",
                    (cid,),
                ).fetchall()
                labels = json.loads(
                    conn.execute(
                        "SELECT participants FROM conversations WHERE conversation_id=?", (cid,)
                    ).fetchone()[0]
                )
                if speaker not in labels:
                    labels.append(speaker)
                languages = sorted({r["language"] for r in rows if r["language"]})
                # Speaker turns and exact offsets remain in segment provenance; render ordered text.
                combined = "\n".join(r["text_raw"] for r in rows)
                last = max(datetime.fromisoformat(r["end_ts"]) for r in rows)
                first = min(datetime.fromisoformat(r["start_ts"]) for r in rows)
                quality = "ok" if all(r["status"] == "ok" for r in rows) else "needs_review"
                conn.execute(
                    """UPDATE conversations SET end_time=?,duration_seconds=?,participants=?,languages=?,
                    transcript=?,raw_transcript=?,quality=? WHERE conversation_id=?""",
                    (
                        last.strftime("%H:%M:%S"),
                        (last - first).total_seconds(),
                        json.dumps(labels),
                        json.dumps(languages),
                        combined,
                        combined,
                        quality,
                        cid,
                    ),
                )
        return cid

    def import_csv(self, content):
        if len(content) > 5 * 1024 * 1024:
            raise ValueError("CSV must be at most 5 MB")
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        required = {"date", "start_time", "end_time", "text"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                "Required columns: date,start_time,end_time,text; optional: language,speaker,engine"
            )
        rows = []
        for index, row in enumerate(reader, 2):
            if len(rows) >= 10000:
                raise ValueError("CSV must contain at most 10000 rows")
            try:
                day = datetime.strptime(row["date"], "%Y-%m-%d").date()
                if day.isoformat() != row["date"]:
                    raise ValueError()
                start = datetime.fromisoformat(row["date"] + "T" + row["start_time"])
                end = datetime.fromisoformat(row["date"] + "T" + row["end_time"])
                start = start.replace(tzinfo=IST) if start.tzinfo is None else start.astimezone(IST)
                end = end.replace(tzinfo=IST) if end.tzinfo is None else end.astimezone(IST)
                if end < start or not row["text"].strip() or len(row["text"]) > 100000:
                    raise ValueError()
                if start.date() != day or end.date() != day:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise ValueError(
                    f"Row {index}: use YYYY-MM-DD, valid same-day start/end times and nonempty text"
                ) from None
            rows.append((row, start, end))
        # Validate every row before writing. A single transaction makes import atomic.
        imported = 0
        with self.connect() as conn:
            for row, start, end in rows:
                payload = [
                    start.isoformat(),
                    end.isoformat(),
                    row["text"],
                    row.get("speaker", "unknown"),
                    row.get("language", ""),
                ]
                sid = (
                    "csv-"
                    + hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()
                )
                if conn.execute("SELECT 1 FROM journal_segments WHERE id=?", (sid,)).fetchone():
                    continue
                cid = int.from_bytes(hashlib.sha256(sid.encode()).digest()[:6], "big")
                conn.execute(
                    """INSERT INTO conversations
                    (conversation_id,date,start_time,end_time,duration_seconds,participants,source_type,
                     is_shivangi_conversation,quality,languages,transcript,raw_transcript)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        cid,
                        start.date().isoformat(),
                        start.strftime("%H:%M:%S"),
                        end.strftime("%H:%M:%S"),
                        (end - start).total_seconds(),
                        json.dumps([row.get("speaker") or "unknown"]),
                        "unknown",
                        0,
                        "imported",
                        json.dumps([row["language"]] if row.get("language") else []),
                        row["text"],
                        row["text"],
                    ),
                )
                conn.execute(
                    """INSERT INTO journal_segments
                    (id,conversation_id,start_ts,end_ts,text_raw,raw_json,engine,status,language,imported)
                    VALUES (?,?,?,?,?,?,?,?,?,1)""",
                    (
                        sid,
                        cid,
                        start.isoformat(),
                        end.isoformat(),
                        row["text"],
                        "{}",
                        "imported",
                        "imported",
                        row.get("language", ""),
                    ),
                )
                imported += 1
        return {"imported": imported, "duplicates": len(rows) - imported}

    def export_csv(self):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, CSV_FIELDS)
        writer.writeheader()
        with self.connect() as conn:
            rows = conn.execute("""SELECT c.*,(SELECT engine FROM journal_segments j WHERE j.conversation_id=c.conversation_id LIMIT 1) AS engine FROM conversations c
                ORDER BY c.date,c.start_time,c.conversation_id""")
            for row in rows:
                writer.writerow(
                    {
                        "date": row["date"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "text": row["raw_transcript"] or row["transcript"] or "",
                        "language": ",".join(json.loads(row["languages"] or "[]")),
                        "speaker": ",".join(json.loads(row["participants"] or "[]")),
                        "engine": row["engine"] or "legacy",
                    }
                )
        return output.getvalue()
