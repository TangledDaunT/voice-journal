"""Authenticated listening routes; a browser lease expires after disconnection."""

from flask import Response, jsonify, request

from audio_capture.monitor_buffer import MonitorBuffer
from utils.storage_guard import require_external_storage


def register_microphone_api(app, config):
    @app.post("/api/microphone/listen")
    def listen():
        require_external_storage(config)
        enabled = (request.get_json(silent=True) or {}).get("enabled") is True
        buffer = MonitorBuffer(config)
        try:
            buffer.lease(enabled)
        finally:
            buffer.close()
        return jsonify(listening=enabled)

    @app.get("/api/microphone/audio")
    def monitor_audio():
        try:
            after = int(request.args.get("after", "0"))
        except ValueError:
            return jsonify(error="Invalid sequence"), 400
        buffer = MonitorBuffer(config)
        try:
            part = buffer.read(after)
        finally:
            buffer.close()
        if part is None:
            return "", 204
        sequence, blob = part
        response = Response(blob, mimetype="audio/wav")
        response.headers["X-Audio-Sequence"] = str(sequence)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/api/microphone/settings", methods=["GET", "PUT"])
    def sound_settings():
        from audio_capture.sound_profile import load, save
        from utils.data_lock import media_lock
        if request.method == "GET":
            return jsonify(load(config))
        try:
            require_external_storage(config)
            with media_lock(config):
                return jsonify(save(config, request.get_json(silent=True)))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @app.route("/api/microphone/hardware", methods=["GET", "PUT"])
    def hardware_gain():
        from audio_capture.mixer import control, CONTROLS
        from utils.data_lock import capture_lock
        try:
            if request.method == "PUT":
                values = request.get_json(silent=True)
                if not isinstance(values, dict) or not values or set(values)-set(CONTROLS):
                    raise ValueError("Unknown hardware control")
                # Validate all requested values before changing any control.
                limits = {key: control(config.audio.input_card, key) for key in values}
                for key, value in values.items():
                    if type(value) is not int or not limits[key]['min'] <= value <= limits[key]['max']:
                        raise ValueError("Hardware gain outside supported range")
                with capture_lock(config):
                    for key, value in values.items(): control(config.audio.input_card, key, value)
            return jsonify(available=True, controls={key: control(config.audio.input_card, key) for key in CONTROLS})
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except OSError:
            return jsonify(available=False, error="Hardware gain controls unavailable for this microphone"), 503
