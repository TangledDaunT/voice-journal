"""
Web Dashboard for Voice Journal.
Provides real-time monitoring and daily summaries via Tailscale.
"""

import sys
import os
import time
import json
import threading
from queue import Queue
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import subprocess

app = Flask(__name__)
CORS(app)

# Configuration
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "voice_journal.db"
VAULT_PATH = BASE_DIR / "obsidian_vault"
CONFIG_PATH = BASE_DIR / "config" / "default_config.yaml"

# Real-time update subscribers
subscribers = []
subscriber_lock = threading.Lock()

# Recent conversations cache for real-time updates
recent_conversations = []
recent_lock = threading.Lock()


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')


@app.route('/api/stats')
def get_stats():
    """Get daily statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        today = datetime.now().strftime("%Y-%m-%d")

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
            "last_updated": datetime.now().isoformat(),
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
    """Get recent conversations."""
    date_filter = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
    limit = min(int(request.args.get('limit', 50)), 200)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id, conversation_id, date, start_time, end_time,
            duration_seconds, participants, source_type,
            is_shivangi_conversation, quality, languages, summary
        FROM conversations
        WHERE date = ?
        ORDER BY start_time DESC
        LIMIT ?
    """, (date_filter, limit))

    rows = cursor.fetchall()

    conversations = []
    for row in rows:
        conversations.append({
            "id": row["id"],
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
        })

    conn.close()
    return jsonify(conversations)


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
        return jsonify({"error": "Not found"}), 404

    return jsonify({
        "id": row["id"],
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
        "summary": row["summary"],
        "transcript": row["transcript"]
    })


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
            ORDER BY date DESC, start_time DESC
            LIMIT 50
        """, (f'%{query}%', f'%{query}%'))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "date": row["date"],
            "start_time": row["start_time"],
            "summary": row["summary"][:100] + "..." if row["summary"] and len(row["summary"]) > 100 else row["summary"]
        })

    return jsonify(results)


@app.route('/api/weekly_summary')
def weekly_summary():
    """Get weekly summary."""
    end_date = datetime.now()
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
    end_date = datetime.now()
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
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"

        # Keep connection alive and send updates
        last_check = datetime.now()
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
                    yield f"data: {json.dumps({'type': 'new_conversation', 'conversation': conv, 'timestamp': datetime.now().isoformat()})}\n\n"

                    # Also send updated stats
                    stats = get_current_stats()
                    yield f"data: {json.dumps({'type': 'stats_update', 'stats': stats, 'timestamp': datetime.now().isoformat()})}\n\n"

                # Send heartbeat every 30 seconds
                if (datetime.now() - last_check).seconds >= 30:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now().isoformat()})}\n\n"
                    last_check = datetime.now()

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
        cursor.execute("SELECT MAX(conversation_id) as max_id FROM conversations")
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
        today = datetime.now().strftime("%Y-%m-%d")

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


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Voice Journal Web Dashboard")
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to listen on')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    # Create templates directory if not exists
    os.makedirs(BASE_DIR / "web" / "templates", exist_ok=True)

    app.run(host=args.host, port=args.port, debug=args.debug)
