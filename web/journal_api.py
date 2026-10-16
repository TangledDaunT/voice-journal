"""Journal audio, live status, validated CSV exchange and explicit user-data deletion."""

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from flask import Response, jsonify, request, send_file

from storage.journal_store import CSV_FIELDS, JournalStore
from utils.data_lock import capture_lock, data_lock, media_lock, write_json


def register_journal_api(app, config, db_connection):
    root = Path(config.database.path).parent.parent

    def read_state(name):
        try:
            return json.loads((root / "runtime" / name).read_text())
        except (OSError, ValueError):
            return {}

    @app.get("/api/runtime")
    def runtime():
        capture = read_state("capture.json")
        processing = read_state("processing.json")
        capture_path = root / "runtime/capture.json"
        capture["fresh"] = capture_path.exists() and time.time() - capture_path.stat().st_mtime < 15
        conn = db_connection()
        try:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            usage = {"requests": 0, "audio_seconds": 0, "billed_seconds": 0}
            if "groq_requests" in tables:
                from datetime import datetime
                from zoneinfo import ZoneInfo

                day = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
                row = conn.execute(
                    """SELECT COUNT(*) AS requests,COALESCE(SUM(audio_seconds),0) AS audio_seconds,
                    COALESCE(SUM(billed_seconds),0) AS billed_seconds FROM groq_requests WHERE day=?""",
                    (day,),
                ).fetchone()
                usage = dict(row)
            speakers = {"enabled": 0, "excluded_sources": 0}
            if "speaker_profiles" in tables:
                speakers["enabled"] = conn.execute(
                    "SELECT COUNT(*) FROM speaker_profiles WHERE enabled=1"
                ).fetchone()[0]
            if "speaker_filter_decisions" in tables:
                speakers["excluded_sources"] = conn.execute(
                    "SELECT COUNT(*) FROM speaker_filter_decisions WHERE status='excluded'"
                ).fetchone()[0]
            latest = conn.execute("SELECT MAX(created_at) FROM conversations").fetchone()[0]
        finally:
            conn.close()
        return jsonify(
            capture=capture,
            speakers=speakers,
            enrolled_only=config.speaker.enrolled_only,
            processing=processing,
            usage=usage,
            last_note_at=latest,
            groq_configured=bool(os.environ.get("GROQ_API_KEY")),
            quarantined_files=len(
                list((Path(config.audio.audio_storage_path) / "quarantine").glob("*.json"))
            ),
        )

    def segment_row(cid):
        conn = db_connection()
        try:
            return conn.execute(
                "SELECT * FROM journal_segments WHERE conversation_id=?", (cid,)
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()

    @app.get("/api/conversation/<int:cid>/audio/<variant>")
    def journal_audio(cid, variant):
        if variant not in ("original", "clean", "full"):
            return jsonify(error="Unknown audio variant"), 404
        conn = db_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM journal_segments WHERE conversation_id=? ORDER BY start_ts,id",
                (cid,),
            ).fetchall()
            if variant == "full":
                sources = {}
                for member in rows:
                    source_id = member["id"].split("__")[0]
                    decision = conn.execute(
                        "SELECT * FROM speaker_filter_decisions WHERE source_id=?", (source_id,)
                    ).fetchone()
                    if decision:
                        details = json.loads(decision["details_json"])
                        sources[source_id] = dict(id=source_id, conversation_id=cid,
                            start_ts=details["start_ts"], end_ts=details["end_ts"],
                            audio_path=decision["audio_path"], clean_path=None)
                rows = sorted(sources.values(), key=lambda row: row["start_ts"])
        finally:
            conn.close()
        if variant == "full" and not rows:
            return jsonify(error="Full recording is unavailable"), 404
        if len(rows) > 1 or variant == "full":
            from storage.conversation_audio import conversation_audio

            try:
                with media_lock(config):
                    path = conversation_audio(rows, variant, config)
                return send_file(path, conditional=True, mimetype="audio/wav")
            except (OSError, ValueError, subprocess.SubprocessError):
                return jsonify(
                    error="Conversation audio is unavailable; original clips are retained"
                ), 503
        row = segment_row(cid)
        if row:
            path = (
                Path(row["audio_path"] or "")
                if variant == "original"
                else Path(row["clean_path"] or "")
            )
            # Recreate a missing clean cache from the preserved original on demand.
            if variant == "clean" and not path.is_file() and row["audio_path"]:
                source = Path(row["audio_path"])
                if source.is_file() and source.resolve().is_relative_to(root.resolve()):
                    path = (
                        Path(config.dashboard.audio_cache_path)
                        / source.parent.name
                        / (row["id"] + ".ogg")
                    )
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with media_lock(config):
                        result = subprocess.run(
                            [
                                "ffmpeg",
                                "-nostdin",
                                "-v",
                                "error",
                                "-y",
                                "-i",
                                str(source),
                                "-af",
                                "highpass=f=70,lowpass=f=7400,afftdn=nr=6:nf=-45,volume=2,alimiter=limit=0.89:level=false",
                                "-ar",
                                "16000",
                                "-ac",
                                "1",
                                "-c:a",
                                "libopus",
                                "-b:a",
                                "32k",
                                str(path),
                            ],
                            capture_output=True,
                            timeout=30,
                        )
                        if result.returncode:
                            return jsonify(error="Audio enhancement failed; use original"), 503
            if path.is_file() and path.resolve().is_relative_to(root.resolve()):
                return send_file(path, conditional=True)
        # Existing conversations have cached audio but no segment provenance row.
        if not row:
            conn = db_connection()
            try:
                legacy = conn.execute(
                    "SELECT date FROM conversations WHERE conversation_id=?", (cid,)
                ).fetchone()
            finally:
                conn.close()
            if legacy:
                directory = Path(config.dashboard.audio_cache_path) / legacy["date"]
                sources = sorted(directory.glob(f"*-{cid}.ogg"))
                if sources:
                    source = sources[0]
                    if variant == "original":
                        return send_file(source, conditional=True)
                    clean = directory / "enhanced" / f"{cid}.ogg"
                    if not clean.exists():
                        clean.parent.mkdir(parents=True, exist_ok=True)
                        with media_lock(config):
                            temporary = clean.with_suffix(".tmp.ogg")
                            result = subprocess.run(
                                [
                                    "ffmpeg",
                                    "-nostdin",
                                    "-v",
                                    "error",
                                    "-y",
                                    "-i",
                                    str(source),
                                    "-af",
                                    "highpass=f=70,lowpass=f=7400,afftdn=nr=6:nf=-45,volume=2,alimiter=limit=0.89:level=false",
                                    "-ar",
                                    "16000",
                                    "-ac",
                                    "1",
                                    "-c:a",
                                    "libopus",
                                    "-b:a",
                                    "32k",
                                    str(temporary),
                                ],
                                capture_output=True,
                                timeout=30,
                            )
                            if result.returncode:
                                return jsonify(
                                    error="Audio enhancement failed; original is available"
                                ), 503
                            os.replace(temporary, clean)
                    return send_file(clean, conditional=True)
        return jsonify(error="This entry has no stored audio"), 404

    @app.get("/api/data/export.csv")
    def export_csv():
        with data_lock(config):
            content = JournalStore(config).export_csv()
        return Response(
            content,
            content_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="voice-journal.csv"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/data/template.csv")
    def csv_template():
        return Response(
            ",".join(CSV_FIELDS) + "\n",
            content_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="voice-journal-template.csv"'},
        )

    @app.get("/api/data/export.zip")
    def export_archive():
        exports = root / "exports"
        exports.mkdir(exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="voice-journal-", suffix=".zip", dir=exports)
        os.close(fd)
        with data_lock(config):
            with zipfile.ZipFile(name, "w", compression=zipfile.ZIP_STORED) as archive:
                store = JournalStore(config)
                archive.writestr("voice-journal.csv", store.export_csv())
                fd, snapshot_name = tempfile.mkstemp(suffix=".db", dir=exports)
                os.close(fd)
                try:
                    with store.connect() as source, sqlite3.connect(snapshot_name) as target:
                        source.backup(target)
                    archive.write(snapshot_name, "voice_journal.db")
                finally:
                    Path(snapshot_name).unlink(missing_ok=True)
                for folder in [
                    "audio",
                    "audio_filtered",
                    "asr_review",
                    "audio_cache",
                    "daily_journal",
                    "transcripts",
                    "peaks",
                    "calibration",
                ]:
                    base = root / folder
                    if base.exists():
                        for path in base.rglob("*"):
                            if path.is_file() and not path.is_symlink():
                                archive.write(path, str(path.relative_to(root)))
        response = send_file(
            name, as_attachment=True, download_name="voice-journal.zip", conditional=True
        )
        response.headers["Cache-Control"] = "no-store"
        response.call_on_close(lambda: Path(name).unlink(missing_ok=True))
        return response

    @app.post("/api/data/import")
    def import_csv():
        upload = request.files.get("file")
        if not upload or not (upload.filename or "").lower().endswith(".csv"):
            return jsonify(error="Choose a UTF-8 CSV file"), 400
        content = upload.stream.read(5 * 1024 * 1024 + 1)
        try:
            with data_lock(config):
                result = JournalStore(config).import_csv(content)
        except (ValueError, UnicodeError) as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(result)

    @app.post("/api/data/clear")
    def clear_all():
        body = request.get_json(silent=True) or {}
        if body.get("confirmation") != "DELETE ALL USER DATA":
            return jsonify(error="Type DELETE ALL USER DATA to confirm permanent deletion"), 400
        with data_lock(config), capture_lock(config), media_lock(config):
            from audio_capture.monitor_buffer import MonitorBuffer

            buffer = MonitorBuffer(config)
            try:
                buffer.lease(False)
            finally:
                buffer.close()
            store = JournalStore(config)
            with store.connect() as conn:
                conn.execute("PRAGMA secure_delete=ON")
                # Delete user rows, never tables/schema or the SQLite file. FTS triggers run normally.
                names = {
                    r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                for table in [
                    "speaker_filter_decisions",
                    "speaker_profiles",
                    "journal_segments",
                    "conversations",
                    "daily_journals",
                    "backlog_tracking",
                    "backlog_summary",
                    "groq_requests",
                    "service_state",
                    "glossary_terms",
                    "glossary_occurrences",
                    "speakers",
                    "utterances",
                    "days",
                    "engine_decisions",
                    "usage_daily",
                    "settings",
                ]:
                    if table in names:
                        conn.execute('DELETE FROM "' + table + '"')
                if "backlog_summary" in names:
                    conn.execute(
                        "INSERT OR IGNORE INTO backlog_summary (id,last_updated) VALUES (1,datetime('now'))"
                    )
            for name in [
                "audio",
                "audio_filtered",
                "asr_review",
                "audio_cache",
                "daily_journal",
                "transcripts",
                "peaks",
                "exports",
                "backups",
                "calibration",
                "validation",
                "runtime",
            ]:
                path = root / name
                if path.exists():
                    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                        raise ValueError("Refusing to clear a directory outside journal storage")
                    shutil.rmtree(path)
            (root / "runtime").mkdir(exist_ok=True)
            (root / "runtime/reset_epoch").write_text(str(time.time()))
            (root / "runtime/data_generation").write_text(str(time.time_ns()))
            write_json(
                root / "runtime/processing.json",
                {"status": "waiting_for_speech", "engine": None, "last_success_at": None},
            )
        return jsonify(cleared=True, database_preserved=True)

    @app.post("/api/groq/test")
    def groq_test():
        import requests

        key = os.environ.get("GROQ_API_KEY")
        if not key:
            return jsonify(configured=False, ok=False, error="Groq key is not configured"), 400
        try:
            response = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": "Bearer " + key, "User-Agent": "voice-journal/2.1"},
                timeout=10,
            )
            return jsonify(
                configured=True, ok=response.status_code == 200, status=response.status_code
            )
        except requests.RequestException:
            return jsonify(configured=True, ok=False, error="Groq connection failed"), 503

    @app.errorhandler(TimeoutError)
    def busy_error(exc):
        return jsonify(error=str(exc)), 409
