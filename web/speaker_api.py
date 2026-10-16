"""Authenticated speaker enrollment control; biometric embeddings never leave SQLite."""

import importlib.util
import json
import re
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import jsonify, request

from speaker_id.enrollment import ACTIVE
from speaker_id.voice_gate import MODEL_ID, SCHEMA
from storage.journal_store import JournalStore
from utils.data_lock import data_lock, write_json


def register_speaker_api(app, config, db_connection):
    root = Path(config.database.path).parent.parent
    state_path = root / "runtime/enrollment.json"
    request_path = root / "runtime/enrollment_request.json"

    def model_installed():
        spec = importlib.util.find_spec("resemblyzer")
        return bool(spec and spec.origin and (Path(spec.origin).parent / "pretrained.pt").is_file())

    def enrollment_state():
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError):
            return {"status": "idle", "seconds_recorded": 0}
        # Paths and embeddings are internal; only progress and safe quality metadata are returned.
        state.pop("audio_path", None)
        return state

    @app.get("/api/speakers")
    def list_speakers():
        conn = db_connection()
        try:
            rows = conn.execute(
                "SELECT id,name,model,enabled,recorded_seconds,voiced_seconds,quality_json,updated_at FROM speaker_profiles ORDER BY name"
            ).fetchall()
            profiles = [dict(row) for row in rows]
            for profile in profiles:
                profile["quality"] = json.loads(profile.pop("quality_json"))
                profile["enabled"] = bool(profile["enabled"])
        except Exception as exc:
            import sqlite3

            if not isinstance(exc, sqlite3.OperationalError):
                raise
            profiles = []
        finally:
            conn.close()
        return jsonify(
            profiles=profiles,
            enrolled_only=config.speaker.enrolled_only,
            model=MODEL_ID,
            model_installed=model_installed(),
            enrollment=enrollment_state(),
            similarity_threshold=config.speaker.similarity_threshold,
            similarity_margin=config.speaker.similarity_margin,
        )

    @app.get("/api/speakers/enrollment")
    def get_enrollment():
        return jsonify(enrollment_state())

    @app.post("/api/speakers/enroll")
    def start_speaker_enrollment():
        body = request.get_json(silent=True) or {}
        name = body.get("name", "")
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z '\-]{0,47}", name.strip()
        ):
            return jsonify(
                error="Enter a speaker name using 1–48 letters, spaces, apostrophes or hyphens"
            ), 400
        name = " ".join(name.split())
        if not model_installed():
            return jsonify(
                error="Speaker encoder is not installed; enrollment and transcription are blocked"
            ), 503
        capture_path = root / "runtime/capture.json"
        if not capture_path.exists() or time.time() - capture_path.stat().st_mtime > 15:
            return jsonify(
                error="The HP capture daemon is unavailable. Start it before enrolling."
            ), 503
        capture = json.loads(capture_path.read_text())
        if not capture.get("stream_active") or capture.get("device_error"):
            return jsonify(
                error=capture.get("device_error") or "The HP microphone stream is inactive"
            ), 503
        with data_lock(config):
            existing = enrollment_state()
            if existing.get("status") in ACTIVE:
                return jsonify(error="A calibration is already in progress"), 409
            store = JournalStore(config)
            with store.connect() as conn:
                conn.executescript(SCHEMA)
            data = {
                "id": uuid4().hex,
                "name": name,
                "status": "queued",
                "seconds_recorded": 0,
                "requested_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
            }
            write_json(state_path, data)
            write_json(
                request_path, {"id": data["id"], "name": name, "requested_at": data["requested_at"]}
            )
        return jsonify(data), 202

    @app.post("/api/speakers/enrollment/cancel")
    def cancel_enrollment():
        state = enrollment_state()
        if state.get("status") not in ("queued", "recording"):
            return jsonify(error="Only a queued or recording calibration can be cancelled"), 409
        with data_lock(config):
            try:
                data = json.loads(request_path.read_text())
            except (OSError, ValueError):
                return jsonify(error="Calibration request no longer exists"), 409
            data["cancel"] = True
            write_json(request_path, data)
            write_json(state_path, dict(state, status="cancelled"))
        return jsonify(cancelled=True)

    @app.patch("/api/speakers/<profile_id>")
    def set_speaker_enabled(profile_id):
        body = request.get_json(silent=True) or {}
        if not isinstance(body.get("enabled"), bool):
            return jsonify(error="enabled must be a boolean"), 400
        with data_lock(config):
            store = JournalStore(config)
            with store.connect() as conn:
                updated = conn.execute(
                    "UPDATE speaker_profiles SET enabled=? WHERE id=?",
                    (int(body["enabled"]), profile_id),
                )
                if not updated.rowcount:
                    return jsonify(error="Speaker not found"), 404
        return jsonify(enabled=body["enabled"])
