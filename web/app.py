"""
Web Dashboard for Voice Journal.
Provides real-time monitoring and daily summaries via Tailscale.
"""

import sys
import os
import time
import json
import threading
import subprocess
from functools import wraps
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, send_from_directory, Response, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sqlite3
from config.settings import Config
from utils.storage_guard import StorageUnavailableError, require_external_storage

app = Flask(__name__, static_folder='dist', static_url_path='')
CORS(app)

@app.errorhandler(StorageUnavailableError)
def storage_unavailable(error):
    return jsonify(error="Journal drive unavailable. Reconnect the external drive; capture will recover automatically."), 503


@app.errorhandler(OSError)
def storage_io_error(error):
    return jsonify(error="Journal storage or audio device unavailable. Check the external drive and microphone."), 503


# Configuration
BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "default_config.yaml"
APP_CONFIG = Config.from_yaml(str(CONFIG_PATH)) if CONFIG_PATH.exists() else Config()
DB_PATH = Path(APP_CONFIG.database.path)
VAULT_PATH = BASE_DIR / "obsidian_vault"
AUDIO_CACHE_PATH = Path(APP_CONFIG.dashboard.audio_cache_path)

# Remote daemon control - runs locally since web server is on same machine
REMOTE_HOST = "localhost"
MUTE_FILE = Path(APP_CONFIG.daemon.mute_file)
DAEMON_SERVICE = "vj-daemon"

# Authentication
AUTH_USERNAME = os.environ.get("WEB_AUTH_USERNAME", "Shreyansh")
AUTH_PASSWORD = os.environ.get("WEB_AUTH_PASSWORD", "")

def require_auth(f):
    """Decorator to require HTTP Basic Auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not AUTH_PASSWORD or not auth or auth.username != AUTH_USERNAME or auth.password != AUTH_PASSWORD:
            return jsonify({"error": "Authentication required"}), 401, {
                'WWW-Authenticate': 'Basic realm="Voice Journal"'
            }
        return f(*args, **kwargs)
    return decorated

# Apply auth to all routes except health check
@app.before_request
def check_auth():
    if request.path in ['/api/health', '/health']:
        return None
    auth = request.authorization
    if not AUTH_PASSWORD or not auth or auth.username != AUTH_USERNAME or auth.password != AUTH_PASSWORD:
        return jsonify({"error": "Authentication required"}), 401, {
            'WWW-Authenticate': 'Basic realm="Voice Journal"'
        }
    if request.path.startswith('/api/') and request.path != '/api/storage':
        try:
            require_external_storage(APP_CONFIG)
        except StorageUnavailableError as exc:
            app.logger.error("%s", exc)
            return jsonify({"error": str(exc), "status": "drive_missing"}), 503
        if request.path.startswith('/api/calibration/'):
            CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    return None


@app.route('/api/storage')
def storage_status():
    try:
        root = require_external_storage(APP_CONFIG)
        import shutil
        usage = shutil.disk_usage(root)
        return jsonify({"available": True, "free_bytes": usage.free, "total_bytes": usage.total})
    except StorageUnavailableError as exc:
        return jsonify({"available": False, "error": str(exc)}), 503


# Real-time update subscribers
subscribers = []
subscriber_lock = threading.Lock()

# Recent conversations cache for real-time updates
recent_conversations = []
recent_lock = threading.Lock()


def get_db_connection():
    """Get database connection."""
    require_external_storage(APP_CONFIG)
    conn = sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/api/audio/<date>/<path:filename>')
def serve_conversation_audio(date, filename):
    """Serve cached conversation audio with HTTP range support."""
    audio_dir = AUDIO_CACHE_PATH / date
    requested = (audio_dir / filename).resolve()
    if audio_dir.resolve() not in requested.parents or not requested.is_file():
        return jsonify({"error": "Audio not found"}), 404
    return send_file(requested, conditional=True, mimetype="audio/ogg")


def audio_url_for(row):
    date = row["date"]
    cache_dir = AUDIO_CACHE_PATH / date
    matches = list(cache_dir.glob(f"*-{row['conversation_id']}.ogg")) if cache_dir.exists() else []
    return f"/api/audio/{date}/{matches[0].name}" if matches else None


from web.microphone_api import register_microphone_api
register_microphone_api(app, APP_CONFIG)
from web.journal_api import register_journal_api
register_journal_api(app, APP_CONFIG, get_db_connection)
from web.speaker_api import register_speaker_api
register_speaker_api(app, APP_CONFIG, get_db_connection)


def conversation_payload(row, members=None, legacy_urls=None):
    """Return source-backed transcript data consistently for list, detail and search."""
    raw = row["raw_transcript"] or row["transcript"] or ""
    patterns = ("thanks for watching", "amara.org", "use only hindi and english",
                "do not output any other language")
    flags = ["suspected_hallucination"] if any(p in raw.lower() for p in patterns) else []
    segment = None
    turns = []
    if members is None:
        conn = get_db_connection()
        try:
            members = conn.execute('SELECT * FROM journal_segments WHERE conversation_id=? ORDER BY start_ts,id', (row['conversation_id'],)).fetchall()
        except sqlite3.OperationalError:
            members = []
        finally:
            conn.close()
    segment = members[0] if members else None
    turns = [dict(start_ts=m['start_ts'], end_ts=m['end_ts'], text=m['text_raw'],
                  speaker=json.loads(m['raw_json']).get('journal_speaker', 'unknown'), status=m['status']) for m in members]
    from asr.language_policy import violation, prompt_echo
    flags = sorted({m['status'] for m in members if m['status'] not in ('ok', 'imported')} |
                   {reason for m in members if not m['imported']
                    if (reason := violation(dict(text=m['text_raw'], language=m['language'])))}) or flags
    if any(prompt_echo(m["text_raw"] or "") for m in members):
        flags = sorted(set(flags) | {"suspected_prompt_echo"})
    full_url = f"/api/conversation/{row['conversation_id']}/audio/full" if any("__" in m["id"] for m in members) else None
    audio_url = None if segment else (legacy_urls.get(row['conversation_id']) if legacy_urls is not None else audio_url_for(row))
    original_url = audio_url
    if audio_url:
        original_url = f"/api/conversation/{row['conversation_id']}/audio/original"
        audio_url = f"/api/conversation/{row['conversation_id']}/audio/clean"
    if segment and segment['audio_path']:
        original_url = f"/api/conversation/{row['conversation_id']}/audio/original"
        audio_url = f"/api/conversation/{row['conversation_id']}/audio/clean"
    return {
        "id": row["id"], "conversation_id": row["conversation_id"],
        "date": row["date"], "start_time": row["start_time"], "end_time": row["end_time"],
        "duration_seconds": row["duration_seconds"],
        "participants": json.loads(row["participants"]) if row["participants"] else [],
        "source_type": row["source_type"],
        "is_shivangi_conversation": bool(row["is_shivangi_conversation"]),
        "quality": row["quality"],
        "languages": json.loads(row["languages"]) if row["languages"] else [],
        "summary": row["summary"], "raw_transcript": raw, "turns": turns,
        "cleaned_transcript": row["cleaned_transcript"] or "",
        "audio_url": audio_url, "original_audio_url": original_url, "full_audio_url": full_url, "review_flags": flags,
        "engine": segment['engine'] if segment else 'legacy',
        "status": segment['status'] if segment else ('suspected_hallucination' if flags else 'legacy'),
        "segment_id": segment['id'] if segment else None,
        "speaker_id": segment['speaker_id'] if segment and 'speaker_id' in segment.keys() else None,
        "speaker_similarity": segment['speaker_similarity'] if segment and 'speaker_similarity' in segment.keys() else None,
    }


def conversation_payloads(rows):
    """Fetch provenance once per page, avoiding per-card external-drive connections."""
    members = {}
    if rows:
        conn = get_db_connection()
        try:
            placeholders = ','.join('?' for _ in rows)
            for member in conn.execute(f'SELECT * FROM journal_segments WHERE conversation_id IN ({placeholders}) ORDER BY start_ts,id', [row['conversation_id'] for row in rows]):
                members.setdefault(member['conversation_id'], []).append(member)
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
    legacy_urls = {}
    dates = {row['date'] for row in rows if not members.get(row['conversation_id'])}
    for date in dates:
        directory = AUDIO_CACHE_PATH / date
        if not directory.is_dir():
            continue
        for path in directory.glob('*.ogg'):
            suffix = path.stem.rsplit('-', 1)[-1]
            if suffix.isdigit():
                legacy_urls.setdefault(int(suffix), f'/api/audio/{date}/{path.name}')
    return [conversation_payload(row, members.get(row['conversation_id'], []), legacy_urls) for row in rows]


@app.route('/')
def index():
    """Main dashboard page - serve React app."""
    dist_path = BASE_DIR / "web" / "dist" / "index.html"
    if dist_path.exists():
        return send_from_directory(BASE_DIR / "web" / "dist", "index.html")
    return render_template('index.html')


# SPA routes - must serve index.html for client-side routing
SPA_ROUTES = ['/dashboard', '/conversations', '/calibration', '/settings']

@app.route('/conversations/<int:id>')
@app.route('/conversations')
def serve_conversations(id=None):
    """Serve React app for conversations route."""
    dist_path = BASE_DIR / "web" / "dist" / "index.html"
    if dist_path.exists():
        return send_from_directory(BASE_DIR / "web" / "dist", "index.html")
    return render_template('index.html')


@app.route('/calibration')
def serve_calibration():
    """Serve React app for calibration route."""
    dist_path = BASE_DIR / "web" / "dist" / "index.html"
    if dist_path.exists():
        return send_from_directory(BASE_DIR / "web" / "dist", "index.html")
    return render_template('index.html')


@app.route('/settings')
def serve_settings():
    """Serve React app for settings route."""
    dist_path = BASE_DIR / "web" / "dist" / "index.html"
    if dist_path.exists():
        return send_from_directory(BASE_DIR / "web" / "dist", "index.html")
    return render_template('index.html')


@app.route('/audio-test')
def serve_audio_test():
    """Serve React app for audio test route."""
    dist_path = BASE_DIR / "web" / "dist" / "index.html"
    if dist_path.exists():
        return send_from_directory(BASE_DIR / "web" / "dist", "index.html")
    return render_template('index.html')


@app.route('/<path:path>')
def serve_frontend(path):
    """Serve static files or fall back to index.html for SPA routing."""
    # Only serve actual files from dist, not routes
    static_path = BASE_DIR / "web" / "dist" / path
    if static_path.exists() and static_path.is_file():
        return send_from_directory(BASE_DIR / "web" / "dist", path)
    # For any other path, serve index.html (SPA fallback)
    dist_path = BASE_DIR / "web" / "dist" / "index.html"
    if dist_path.exists():
        return send_from_directory(BASE_DIR / "web" / "dist", "index.html")
    return "Not Found", 404


@app.route('/api/stats')
def get_stats():
    """Get daily statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        today = datetime.now(ZoneInfo('Asia/Kolkata')).strftime("%Y-%m-%d")

        # Today's stats
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_shivangi_conversation = 1 THEN 1 ELSE 0 END) as with_shivangi,
                SUM(CASE WHEN source_type = 'self_talk' THEN 1 ELSE 0 END) as self_talk,
                SUM(CASE WHEN source_type = 'media_or_unknown' THEN 1 ELSE 0 END) as media
            FROM conversations
            WHERE date = ?
        """, (today,))

        row = cursor.fetchone()

        stats = {
            "date": today,
            "total_conversations": row["total"] if row and row["total"] else 0,
            "with_shivangi": row["with_shivangi"] if row and row["with_shivangi"] else 0,
            "self_talk": row["self_talk"] if row and row["self_talk"] else 0,
            "media_flagged": row["media"] if row and row["media"] else 0,
            "last_updated": datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(),
            "status": "operational"
        }

        conn.close()
        return jsonify(stats)
    except Exception as e:
        return jsonify({
            "error": str(e),
            "total_conversations": 0,
            "with_shivangi": 0,
            "self_talk": 0,
            "media_flagged": 0
        })


@app.route('/api/conversations')
def get_conversations():
    """Get conversations, optionally filtered by date."""
    date_filter = request.args.get('date')
    limit = min(int(request.args.get('limit', 50)), 200)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id, conversation_id, date, start_time, end_time,
            duration_seconds, participants, source_type,
            is_shivangi_conversation, quality, languages, summary,
            transcript, raw_transcript, cleaned_transcript
        FROM conversations
        WHERE (? IS NULL OR date = ?)
        ORDER BY date DESC, start_time DESC, id DESC
        LIMIT ?
    """, (date_filter, date_filter, limit))

    rows = cursor.fetchall()

    conn.close()
    return jsonify(conversation_payloads(rows))


@app.route('/api/conversation/<int:conv_id>')
def get_conversation(conv_id):
    """Get single conversation details."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM conversations WHERE conversation_id = ?
    """, (conv_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Journal note not found"}), 404
    return jsonify(conversation_payload(row))


@app.route('/api/search')
def search_conversations():
    """Search conversations."""
    query = request.args.get('q', '')
    if not query:
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor()

    # Use FTS5 if available
    try:
        cursor.execute("""
            SELECT c.* FROM conversations c
            JOIN conversations_fts fts ON c.id = fts.rowid
            WHERE conversations_fts MATCH ?
            ORDER BY rank
            LIMIT 50
        """, (query,))
    except:
        cursor.execute("""
            SELECT * FROM conversations
            WHERE summary LIKE ? OR transcript LIKE ?
               OR raw_transcript LIKE ? OR cleaned_transcript LIKE ?
            ORDER BY date DESC, start_time DESC
            LIMIT 50
        """, (f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%'))

    rows = cursor.fetchall()
    conn.close()

    return jsonify(conversation_payloads(rows))


@app.route('/api/weekly_summary')
def weekly_summary():
    """Get weekly summary."""
    end_date = datetime.now(ZoneInfo('Asia/Kolkata'))
    start_date = end_date - timedelta(days=7)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            date,
            COUNT(*) as total,
            SUM(CASE WHEN is_shivangi_conversation = 1 THEN 1 ELSE 0 END) as with_shivangi,
            SUM(CASE WHEN source_type = 'live_conversation' THEN 1 ELSE 0 END) as live,
            AVG(duration_seconds) as avg_duration
        FROM conversations
        WHERE date >= ? AND date <= ?
        GROUP BY date
        ORDER BY date
    """, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))

    rows = cursor.fetchall()
    conn.close()

    daily_data = []
    for row in rows:
        daily_data.append({
            "date": row["date"],
            "total": row["total"],
            "with_shivangi": row["with_shivangi"],
            "live": row["live"],
            "avg_duration": round(row["avg_duration"] or 0, 1)
        })

    return jsonify(daily_data)


@app.route('/api/quality_distribution')
def quality_distribution():
    """Get quality distribution for conversations."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT quality, COUNT(*) as count
        FROM conversations
        WHERE source_type = 'live_conversation'
        AND quality != 'not_applicable'
        GROUP BY quality
    """)

    rows = cursor.fetchall()
    conn.close()

    return jsonify([{"quality": row["quality"], "count": row["count"]} for row in rows])


@app.route('/api/shivangi_stats')
def shivangi_stats():
    """Get Shivangi conversation statistics."""
    days = int(request.args.get('days', 30))
    end_date = datetime.now(ZoneInfo('Asia/Kolkata'))
    start_date = end_date - timedelta(days=days)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(duration_seconds) as total_duration,
            AVG(duration_seconds) as avg_duration,
            SUM(CASE WHEN quality = 'good' THEN 1 ELSE 0 END) as good_count,
            SUM(CASE WHEN quality = 'tense' THEN 1 ELSE 0 END) as tense_count
        FROM conversations
        WHERE is_shivangi_conversation = 1
        AND date >= ?
    """, (start_date.strftime("%Y-%m-%d"),))

    row = cursor.fetchone()
    conn.close()

    return jsonify({
        "total_conversations": row["total"] if row else 0,
        "total_duration_minutes": round((row["total_duration"] or 0) / 60, 1),
        "avg_duration_seconds": round(row["avg_duration"] or 0, 1),
        "good_count": row["good_count"] if row else 0,
        "tense_count": row["tense_count"] if row else 0
    })


@app.route('/api/backlog')
def get_backlog():
    staging_path = Path(APP_CONFIG.audio.audio_storage_path) / "staging"
    paths = list(staging_path.glob("*.json"))
    seconds = 0.0
    invalid = 0
    for path in paths:
        try:
            data = json.loads(path.read_text())
            duration = float(data['duration_seconds'])
            if duration < 0: raise ValueError()
            seconds += duration
        except (ValueError, OSError, KeyError, TypeError):
            invalid += 1
    return jsonify(total_queued_hours=seconds/3600, segments_pending=len(paths),
        invalid_segments=invalid, status='needs_attention' if invalid else 'operational',
        overflow_threshold=APP_CONFIG.scheduler.backlog_overflow_hours)


@app.route('/health')
@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    try:
        # Check database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM conversations")
        count = cursor.fetchone()[0]
        conn.close()

        # Check staging dir
        staging_path = Path(APP_CONFIG.audio.audio_storage_path) / "staging"
        staging_count = len(list(staging_path.glob("*.json"))) if staging_path.exists() else 0

        return jsonify({
            "status": "healthy",
            "database": "connected",
            "total_conversations": count,
            "staging_segments": staging_count,
            "timestamp": datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()
        }), 500


def _daily_journal_db():
    return get_db_connection()


@app.route('/api/days')
def list_daily_journals():
        """List available daily recordings and transcripts."""
        with _daily_journal_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT date, speech_seconds, segment_count, updated_at "
                "FROM daily_journals ORDER BY date DESC"
            ).fetchall()
        return jsonify([dict(row) for row in rows])


@app.route('/api/days/<day>')
def get_daily_journal(day):
        """Return one day's transcript and MP3 URL."""
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Date must use YYYY-MM-DD"}), 400
        with _daily_journal_db() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT date, transcript, speech_seconds, segment_count, updated_at "
                "FROM daily_journals WHERE date = ?",
                (day,),
            ).fetchone()
        if not row:
            return jsonify({"error": "Daily journal not found"}), 404
        result = dict(row)
        result["audio_url"] = f"/api/days/{day}/audio"
        return jsonify(result)


@app.route('/api/days/<day>/audio')
def get_daily_audio(day):
        """Stream the MP3 recording for a day."""
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Date must use YYYY-MM-DD"}), 400
        audio_path = Path(APP_CONFIG.journal.storage_path) / "audio" / f"{day}.mp3"
        if not audio_path.is_file():
            return jsonify({"error": "Audio recording not found"}), 404
        return send_file(audio_path, mimetype="audio/mpeg", conditional=True)


# Serve Obsidian notes
@app.route('/notes/<path:filename>')
def serve_note(filename):
    """Serve Obsidian markdown notes."""
    note_path = VAULT_PATH / filename

    if not note_path.exists():
        return jsonify({"error": "Note not found"}), 404

    with open(note_path, 'r') as f:
        content = f.read()

    return jsonify({"content": content, "path": filename})


@app.route('/api/stream')
def stream():
    """Server-Sent Events endpoint for real-time updates."""
    def event_stream():
        # Send initial data
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()})}\n\n"

        # Keep connection alive and send updates
        last_check = datetime.now(ZoneInfo('Asia/Kolkata'))
        last_conversation_id = get_last_conversation_id()

        while True:
            time.sleep(2)  # Check every 2 seconds

            try:
                current_last_id = get_last_conversation_id()

                # Check for new conversations
                if current_last_id and current_last_id != last_conversation_id:
                    # New conversation detected!
                    last_conversation_id = current_last_id

                    # Get latest conversation details
                    conv = get_conversation_details(current_last_id)

                    # Send update to client
                    yield f"data: {json.dumps({'type': 'new_conversation', 'conversation': conv, 'timestamp': datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()})}\n\n"

                    # Also send updated stats
                    stats = get_current_stats()
                    yield f"data: {json.dumps({'type': 'stats_update', 'stats': stats, 'timestamp': datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()})}\n\n"

                # Send heartbeat every 30 seconds
                if (datetime.now(ZoneInfo('Asia/Kolkata')) - last_check).seconds >= 30:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now(ZoneInfo('Asia/Kolkata')).isoformat()})}\n\n"
                    last_check = datetime.now(ZoneInfo('Asia/Kolkata'))

            except Exception as e:
                # Send error but keep connection
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


def get_last_conversation_id():
    """Get the ID of the most recent conversation."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT conversation_id AS max_id FROM conversations ORDER BY date DESC,start_time DESC,id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        return row["max_id"] if row and row["max_id"] else 0
    except:
        return 0


def get_conversation_details(conv_id):
    """Get details for a specific conversation."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT conversation_id, date, start_time, end_time,
                   duration_seconds, participants, source_type,
                   is_shivangi_conversation, quality, languages, summary
            FROM conversations WHERE conversation_id = ?
        """, (conv_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "conversation_id": row["conversation_id"],
                "date": row["date"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "duration_seconds": row["duration_seconds"],
                "participants": json.loads(row["participants"]) if row["participants"] else [],
                "source_type": row["source_type"],
                "is_shivangi_conversation": bool(row["is_shivangi_conversation"]),
                "quality": row["quality"],
                "languages": json.loads(row["languages"]) if row["languages"] else [],
                "summary": row["summary"] or ""
            }
        return None
    except:
        return None


def get_current_stats():
    """Get current day stats."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        today = datetime.now(ZoneInfo('Asia/Kolkata')).strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_shivangi_conversation = 1 THEN 1 ELSE 0 END) as with_shivangi,
                SUM(CASE WHEN source_type = 'self_talk' THEN 1 ELSE 0 END) as self_talk,
                SUM(CASE WHEN source_type = 'media_or_unknown' THEN 1 ELSE 0 END) as media
            FROM conversations
            WHERE date = ?
        """, (today,))

        row = cursor.fetchone()
        conn.close()

        return {
            "total_conversations": row["total"] if row and row["total"] else 0,
            "with_shivangi": row["with_shivangi"] if row and row["with_shivangi"] else 0,
            "self_talk": row["self_talk"] if row and row["self_talk"] else 0,
            "media_flagged": row["media"] if row and row["media"] else 0
        }
    except:
        return {
            "total_conversations": 0,
            "with_shivangi": 0,
            "self_talk": 0,
            "media_flagged": 0
        }


def run_local_command(command):
    """Run a command locally on this machine."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return {"error": f"Command failed: {result.stderr}", "returncode": result.returncode}

        return {"success": True, "output": result.stdout}

    except subprocess.TimeoutExpired:
        return {"error": "Command timeout"}
    except Exception as e:
        return {"error": str(e)}


@app.route('/api/mute/status')
def get_mute_status():
    return jsonify({"muted": MUTE_FILE.exists()})


@app.route('/api/mute', methods=['POST'])
def toggle_mute():
    try:
        data = request.get_json(silent=True) or {}
        muted = data.get("muted", not MUTE_FILE.exists())
        if not isinstance(muted, bool):
            return jsonify({"error": "muted must be a boolean"}), 400
        if muted:
            MUTE_FILE.parent.mkdir(parents=True, exist_ok=True)
            MUTE_FILE.write_text("muted")
        else:
            MUTE_FILE.unlink(missing_ok=True)
        return jsonify({"muted": MUTE_FILE.exists()})
    except OSError:
        return jsonify({"error": "Could not change microphone state"}), 503


# ============================================================================
# CALIBRATION ENDPOINTS
# ============================================================================

CALIBRATION_DIR = Path(APP_CONFIG.database.path).parent.parent / "calibration"

# Calibration state (in-memory)
calibration_state = {
    "silent_baseline": None,
    "voice_samples": {},
    "status": "idle"
}


@app.route('/api/calibration/status')
def get_calibration_status():
    """Get current calibration status."""
    try:
        # Load existing calibration if exists
        profile_path = CALIBRATION_DIR / "room_profile.json"
        voice_path = CALIBRATION_DIR / "voice_profiles.json"

        profile = None
        if profile_path.exists():
            with open(profile_path) as f:
                profile = json.load(f)

        voices = {}
        if voice_path.exists():
            with open(voice_path) as f:
                voices = json.load(f)

        # Get audio device info
        import sounddevice as sd
        try:
            input_device = sd.query_devices(kind='input')
            device_name = input_device['name']
        except Exception:
            # Fallback: try hw:0,0 directly
            try:
                hw_dev = sd.query_devices(device='hw:0,0')
                device_name = hw_dev['name']
            except Exception:
                device_name = "hw:0,0 (ALC236 Analog)"

        return jsonify({
            "status": calibration_state["status"],
            "has_silent_baseline": profile is not None,
            "silent_baseline": profile,
            "voice_profiles": voices,
            "current_input_device": device_name
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"})


@app.route('/api/calibration/start_silent', methods=['POST'])
def start_silent_calibration():
    """Record a 5-second silent room baseline."""
    try:
        import sounddevice as sd
        import numpy as np

        calibration_state["status"] = "recording_silent"

        # Record 5 seconds of "silence"
        duration = 5
        sample_rate = 16000

        # Try to find an available input device that's not exclusively used by the daemon
        devices = sd.query_devices()
        input_device_idx = None
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0 and d['name'] != 'default':
                input_device_idx = i
                break

        if input_device_idx is None:
            input_device_idx = sd.default.device[0]

        try:
            recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, device=input_device_idx)
            sd.wait()
        except (sd.PortAudioError, ValueError):
            try:
                recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, device='sysdefault')
                sd.wait()
            except (sd.PortAudioError, ValueError):
                calibration_state["status"] = "error"
                return jsonify({
                    "success": False,
                    "error": "Audio device is in use by the daemon. The daemon is actively capturing audio.",
                    "device_in_use": True
                })

        # Calculate noise floor metrics
        rms = float(np.sqrt(np.mean(recording**2)))
        max_amp = float(np.max(np.abs(recording)))
        peak_freq = _get_peak_frequency(recording.flatten(), sample_rate)

        # Dynamic threshold calculation
        # VAD threshold should be above noise floor
        recommended_vad_threshold = min(0.7, max(0.3, rms * 5))

        profile = {
            "recorded_at": datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(),
            "duration_seconds": duration,
            "sample_rate": sample_rate,
            "rms_level": round(rms, 6),
            "max_amplitude": round(max_amp, 6),
            "peak_frequency_hz": round(peak_freq, 1),
            "recommended_vad_threshold": round(recommended_vad_threshold, 2),
            "noise_floor_db": round(20 * np.log10(rms) if rms > 0 else -60, 1)
        }

        # Save profile
        profile_path = CALIBRATION_DIR / "room_profile.json"
        with open(profile_path, 'w') as f:
            json.dump(profile, f, indent=2)

        calibration_state["silent_baseline"] = profile
        calibration_state["status"] = "idle"

        return jsonify({
            "success": True,
            "profile": profile,
            "message": "Silent baseline recorded successfully"
        })
    except Exception as e:
        calibration_state["status"] = "error"
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/calibration/start_voice', methods=['POST'])
def start_voice_calibration():
    """Compatibility endpoint: use the same real 30-second daemon enrollment."""
    return app.view_functions['start_speaker_enrollment']()


@app.route('/api/calibration/test_levels', methods=['POST'])
def test_audio_levels():
    """Real-time audio level test for 3 seconds."""
    try:
        import sounddevice as sd
        import numpy as np

        duration = 3
        sample_rate = 16000

        # Try to find an available input device that's not exclusively used by the daemon
        devices = sd.query_devices()
        input_device_idx = None
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0 and d['name'] != 'default':
                input_device_idx = i
                break

        # If no alternative device, try default but handle gracefully
        if input_device_idx is None:
            input_device_idx = sd.default.device[0]

        try:
            recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, device=input_device_idx)
            sd.wait()
        except (sd.PortAudioError, ValueError):
            # Device is in use by daemon - try with sysdefault
            try:
                recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, device='sysdefault')
                sd.wait()
            except (sd.PortAudioError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "Audio device is in use by the daemon. The daemon is actively capturing audio. You can verify audio is being captured by checking the dashboard for new conversations.",
                    "device_in_use": True
                })

        # Calculate levels
        rms = float(np.sqrt(np.mean(recording**2)))
        max_amp = float(np.max(np.abs(recording)))
        peak_db = round(20 * np.log10(max_amp) if max_amp > 0 else -60, 1)

        # Determine quality
        if max_amp < 0.05:
            quality = "too_low"
            message = "Audio level too low. Increase mic volume or get closer."
        elif max_amp < 0.3:
            quality = "acceptable"
            message = "Audio level acceptable. Could be improved."
        elif max_amp < 0.8:
            quality = "good"
            message = "Audio level good!"
        else:
            quality = "clipping"
            message = "Audio clipping! Reduce mic volume."

        return jsonify({
            "success": True,
            "rms": round(rms, 4),
            "max_amplitude": round(max_amp, 4),
            "peak_db": peak_db,
            "quality": quality,
            "message": message
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/calibration/apply', methods=['POST'])
def apply_calibration():
    """Apply calibration settings to system."""
    try:
        # This would update config.yaml or send signal to daemon
        # For now, just return success
        profile_path = CALIBRATION_DIR / "room_profile.json"
        voice_path = CALIBRATION_DIR / "voice_profiles.json"

        if not profile_path.exists():
            return jsonify({"success": False, "error": "No silent baseline recorded"})

        with open(profile_path) as f:
            profile = json.load(f)

        # TODO: Send signal to daemon to reload calibration
        # For now, just log it

        return jsonify({
            "success": True,
            "message": "Calibration applied. Restart daemon for full effect.",
            "profile": profile
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/calibration/audio_devices')
def get_audio_devices():
    """Get list of available audio input devices."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()

        input_devices = []
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                input_devices.append({
                    "index": i,
                    "name": d['name'],
                    "channels": d['max_input_channels'],
                    "default_sample_rate": d['default_samplerate'],
                    "is_default": i == sd.default.device[0]
                })

        # If no input devices found via default enumeration, try hw:0,0 directly
        if not input_devices:
            try:
                hw_dev = sd.query_devices(device='hw:0,0')
                if hw_dev and hw_dev['max_input_channels'] > 0:
                    input_devices.append({
                        "index": 0,
                        "name": hw_dev['name'],
                        "channels": hw_dev['max_input_channels'],
                        "default_sample_rate": hw_dev['default_samplerate'],
                        "is_default": True
                    })
            except Exception:
                pass

        return jsonify(input_devices)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/calibration/set_device', methods=['POST'])
def set_audio_device():
    """Set the default audio input device."""
    try:
        import sounddevice as sd

        data = request.get_json() or {}
        device_index = data.get('device_index')

        if device_index is not None:
            sd.default.device[0] = device_index
            return jsonify({"success": True, "message": f"Device set to {device_index}"})

        return jsonify({"success": False, "error": "No device index provided"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ============================================================================
# AUDIO TEST AND TALKBACK ENDPOINTS
# ============================================================================

AUDIO_TEST_DIR = BASE_DIR / "audio_test"
AUDIO_TEST_DIR.mkdir(parents=True, exist_ok=True)

# Talkback state
talkback_stream = None
talkback_active = False


@app.route('/api/audio/record_test', methods=['POST'])
def record_audio_test():
    """Record a test audio sample and return it for playback."""
    try:
        import sounddevice as sd
        import numpy as np
        import wave
        import uuid

        data = request.get_json() or {}
        duration = data.get('duration', 5)  # seconds
        sample_rate = data.get('sample_rate', 16000)

        # Try to find an available input device that's not exclusively used by the daemon
        devices = sd.query_devices()
        input_device_idx = None
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0 and d['name'] != 'default':
                input_device_idx = i
                break

        if input_device_idx is None:
            input_device_idx = sd.default.device[0]

        try:
            recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, device=input_device_idx)
            sd.wait()
        except (sd.PortAudioError, ValueError):
            try:
                recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, device='sysdefault')
                sd.wait()
            except (sd.PortAudioError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "Audio device is in use by the daemon. The daemon is actively capturing audio.",
                    "device_in_use": True
                })

        # Save to WAV file
        filename = f"test_{uuid.uuid4().hex[:8]}.wav"
        filepath = AUDIO_TEST_DIR / filename

        with wave.open(str(filepath), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes((recording * 32767).astype(np.int16).tobytes())

        # Calculate audio stats
        max_amp = float(np.max(np.abs(recording)))
        rms = float(np.sqrt(np.mean(recording**2)))

        return jsonify({
            "success": True,
            "filename": filename,
            "url": f"/api/audio/play_test/{filename}",
            "duration_seconds": duration,
            "sample_rate": sample_rate,
            "max_amplitude": round(max_amp, 4),
            "rms": round(rms, 4),
            "peak_db": round(20 * np.log10(max_amp) if max_amp > 0 else -60, 1)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/audio/play_test/<filename>')
def play_audio_test(filename):
    """Serve recorded test audio file."""
    try:
        filepath = AUDIO_TEST_DIR / filename
        if not filepath.exists():
            return jsonify({"error": "File not found"}), 404

        return send_from_directory(AUDIO_TEST_DIR, filename, mimetype='audio/wav')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/audio/test_files')
def list_test_files():
    """List all test audio files."""
    try:
        files = []
        for f in AUDIO_TEST_DIR.glob("*.wav"):
            stat = f.stat()
            files.append({
                "filename": f.name,
                "url": f"/api/audio/play_test/{f.name}",
                "size_bytes": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
        return jsonify({"files": sorted(files, key=lambda x: x['created'], reverse=True)})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/audio/delete_test/<filename>', methods=['DELETE'])
def delete_audio_test(filename):
    """Delete a test audio file."""
    try:
        filepath = AUDIO_TEST_DIR / filename
        if filepath.exists():
            filepath.unlink()
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "File not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ============================================================================
# TALKBACK - Real-time audio streaming
# ============================================================================

talkback_connections = set()
talkback_output_stream = None
talkback_audio_lock = threading.RLock()


def serialize_talkback(function):
    """PortAudio stream lifecycle and writes must never overlap across HTTP threads."""
    @wraps(function)
    def locked(*args, **kwargs):
        with talkback_audio_lock:
            return function(*args, **kwargs)
    return locked


@app.route('/api/talkback/start', methods=['POST'])
@serialize_talkback
def start_talkback():
    """Initialize talkback mode - HP will play audio from remote mic."""
    global talkback_output_stream, talkback_active

    try:
        import sounddevice as sd

        if talkback_active:
            return jsonify({"success": True, "message": "Talkback already active"})

        # Initialize output stream (HP speaker)
        talkback_output_stream = sd.OutputStream(
            samplerate=16000,
            channels=1,
            dtype='float32'
        )
        talkback_output_stream.start()
        talkback_active = True

        return jsonify({
            "success": True,
            "message": "Talkback started - HP speaker ready",
            "sample_rate": 16000
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/talkback/stop', methods=['POST'])
@serialize_talkback
def stop_talkback():
    """Stop talkback mode."""
    global talkback_output_stream, talkback_active

    try:
        talkback_active = False
        if talkback_output_stream:
            talkback_output_stream.stop()
            talkback_output_stream.close()
            talkback_output_stream = None

        return jsonify({"success": True, "message": "Talkback stopped"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/talkback/status')
@serialize_talkback
def talkback_status():
    """Get talkback status."""
    return jsonify({
        "active": talkback_active,
        "output_stream_ready": talkback_output_stream is not None
    })


@app.route('/api/talkback/stream', methods=['POST'])
@serialize_talkback
def talkback_stream():
    """Receive audio chunk and play it immediately on HP speaker."""
    global talkback_output_stream, talkback_active

    try:
        import numpy as np

        if not talkback_active or talkback_output_stream is None:
            return jsonify({"success": False, "error": "Talkback not started"}), 400

        # Get audio data from request
        audio_data = request.get_data()

        if not audio_data:
            return jsonify({"success": False, "error": "No audio data"}), 400

        # Convert bytes to float32 numpy array
        # Assume 16-bit PCM input
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32767.0

        # Play immediately
        talkback_output_stream.write(audio_array)

        return jsonify({"success": True, "samples_received": len(audio_array)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/talkback/ws')
def talkback_websocket():
    """WebSocket endpoint for real-time talkback (alternative to HTTP streaming)."""
    # Note: Flask doesn't natively support WebSockets well
    # This is a placeholder - for production use Flask-SocketIO or FastAPI
    return jsonify({"error": "Use HTTP POST to /api/talkback/stream instead"}), 400


@app.route('/api/audio/speaker_test', methods=['POST'])
def speaker_test():
    """Play a test tone on the HP speaker to verify output works."""
    try:
        import sounddevice as sd
        import numpy as np

        data = request.get_json() or {}
        duration = data.get('duration', 2)  # seconds
        frequency = data.get('frequency', 440)  # Hz (A4 note)

        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        tone = np.sin(frequency * 2 * np.pi * t) * 0.5  # 50% volume

        try:
            sd.play(tone, sample_rate)
            sd.wait()
        except sd.PortAudioError as e:
            return jsonify({
                "success": False,
                "error": f"Audio output device error: {e}. The daemon may be using the audio device."
            })

        return jsonify({
            "success": True,
            "message": f"Played {frequency}Hz tone for {duration}s",
            "frequency": frequency,
            "duration": duration
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/audio/output_devices')
def get_output_devices():
    """Get list of available audio output devices."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()

        output_devices = []
        for i, d in enumerate(devices):
            if d['max_output_channels'] > 0:
                output_devices.append({
                    "index": i,
                    "name": d['name'],
                    "channels": d['max_output_channels'],
                    "default_sample_rate": d['default_samplerate'],
                    "is_default": i == sd.default.device[1]
                })

        return jsonify(output_devices)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/audio/set_output_device', methods=['POST'])
def set_output_device():
    """Set the default audio output device."""
    try:
        import sounddevice as sd

        data = request.get_json() or {}
        device_index = data.get('device_index')

        if device_index is not None:
            sd.default.device[1] = device_index
            return jsonify({"success": True, "message": f"Output device set to {device_index}"})

        return jsonify({"success": False, "error": "No device index provided"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ============================================================================
# GLOSSARY ENDPOINTS
# ============================================================================

@app.route('/api/glossary')
def get_glossary():
    """Get all glossary terms."""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM glossary_terms
            ORDER BY occurrence_count DESC, term_romanized ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        terms = []
        for row in rows:
            terms.append({
                "id": row['id'],
                "term_devanagari": row['term_devanagari'],
                "term_romanized": row['term_romanized'],
                "first_seen_date": row['first_seen_date'],
                "occurrence_count": row['occurrence_count'],
                "last_seen_date": row['last_seen_date'],
                "inferred_meaning": row['inferred_meaning'],
                "example_transcript": row['example_transcript'],
                "is_validated": bool(row['is_validated'])
            })

        return jsonify(terms)
    except Exception as e:
        return jsonify({"error": str(e), "terms": []})


@app.route('/api/glossary/search')
def search_glossary():
    """Search glossary terms."""
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify([])

    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM glossary_terms
            WHERE LOWER(term_devanagari) LIKE ?
               OR LOWER(term_romanized) LIKE ?
               OR LOWER(inferred_meaning) LIKE ?
            ORDER BY occurrence_count DESC
            LIMIT 20
        """, (f'%{query}%', f'%{query}%', f'%{query}%'))

        rows = cursor.fetchall()
        conn.close()

        return jsonify([dict(row) for row in rows])
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/glossary/run_weekly', methods=['POST'])
def trigger_weekly_job():
    """Manually trigger weekly glossary job."""
    try:
        import subprocess

        # Run job in background
        subprocess.Popen(
            ['python3', 'scripts/run_glossary_weekly.py'],
            cwd=str(BASE_DIR),
            stdout=open(str(BASE_DIR / 'logs' / 'glossary_job.log'), 'w'),
            stderr=subprocess.STDOUT
        )

        return jsonify({
            "success": True,
            "message": "Glossary job started in background"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/glossary/stats')
def glossary_stats():
    """Get glossary statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM glossary_terms")
        total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT SUM(occurrence_count) FROM glossary_terms
        """)
        total_occurrences = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*) FROM glossary_terms
            WHERE is_validated = 1
        """)
        validated = cursor.fetchone()[0]

        conn.close()

        return jsonify({
            "total_terms": total,
            "total_occurrences": total_occurrences,
            "validated_terms": validated,
            "pending_validation": total - validated
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# Helper functions for audio analysis
def _get_peak_frequency(audio, sample_rate):
    """Get the dominant frequency in the audio."""
    try:
        import numpy as np
        if len(audio) < 100:
            return 0

        # FFT
        fft = np.abs(np.fft.rfft(audio))
        freqs = np.fft.rfftfreq(len(audio), 1/sample_rate)

        # Find peak
        peak_idx = np.argmax(fft)
        return float(freqs[peak_idx])
    except:
        return 0


def _estimate_pitch(audio, sample_rate):
    """Estimate fundamental frequency using autocorrelation."""
    try:
        import numpy as np
        if len(audio) < 100:
            return 0

        # Simple autocorrelation-based pitch detection
        corr = np.correlate(audio, audio, mode='full')
        corr = corr[len(corr)//2:]

        # Find first peak after first minimum
        d = np.diff(corr)
        start = np.where(d > 0)[0]
        if len(start) == 0:
            return 0

        start = start[0]
        peak = np.argmax(corr[start:]) + start

        if peak > 0:
            return sample_rate / peak
        return 0
    except:
        return 0


def _get_spectral_centroid(audio, sample_rate):
    """Calculate spectral centroid (brightness measure)."""
    try:
        import numpy as np
        if len(audio) < 100:
            return 0

        magnitudes = np.abs(np.fft.rfft(audio))
        freqs = np.fft.rfftfreq(len(audio), 1/sample_rate)

        return float(np.sum(magnitudes * freqs) / (np.sum(magnitudes) + 1e-10))
    except:
        return 0


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Voice Journal Web Dashboard")
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to listen on')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--ssl', action='store_true', help='Enable HTTPS')
    parser.add_argument('--cert', default=None, help='Path to SSL certificate')
    parser.add_argument('--key', default=None, help='Path to SSL private key')

    args = parser.parse_args()

    ssl_context = None
    if args.ssl:
        cert_file = args.cert or "/app/tls/cert.pem"
        key_file = args.key or "/app/tls/key.pem"
        ssl_context = (cert_file, key_file)

    # Create templates directory if not exists
    os.makedirs(BASE_DIR / "web" / "templates", exist_ok=True)

    app.run(host=args.host, port=args.port, debug=args.debug, ssl_context=ssl_context)
