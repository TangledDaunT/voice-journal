#!/usr/bin/env python3
"""
eval/correct_ui.py

Flask web UI for correcting draft transcripts.
- Splits SPONT_* takes into ~15s chunks at silence boundaries
- Audio player with loop + 0.75x/1x speed
- Editable textarea per chunk, prefilled with draft text
- Saves eval/<tag>/<take>.ref.txt (one line per chunk)
- Marks unintelligible chunks for exclusion from scoring
- Reference convention: Roman-script Hinglish, lowercase, no punctuation required
"""

import argparse
import sys
import json
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from flask import Flask, render_template_string, request, jsonify, send_file
from werkzeug.serving import run_simple

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

# Add parent for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================
# Flask App & Config
# ============================
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# Global state (per tag)
CURRENT_TAG = None
TAG_DIR = None
SCENARIOS = [
    "SPONT_SOLO",
    "SPONT_CONVO",
    "SPONT_QUIET_FAR",
    "SPONT_NOISY",
]

CHUNK_TARGET_DURATION = 15.0  # seconds
MIN_CHUNK_DURATION = 3.0
MAX_CHUNK_DURATION = 30.0
SILENCE_THRESHOLD_DB = -45.0
SILENCE_MIN_DURATION = 0.3  # seconds


# ============================
# Reference Convention (documented at top of page)
# ============================
REFERENCE_CONVENTION = """
**Reference Transcript Convention:**
- **Script**: Roman-script Hinglish (Devanagari will be transliterated automatically)
- **Case**: lowercase only
- **Punctuation**: not required (commas, periods optional)
- **Numbers**: write as words (e.g., "ek", "do", "teen") or digits, both accepted
- **Unintelligible**: mark chunk as "unintelligible" — will be excluded from scoring
- **Hesitation sounds**: include if clear (e.g., "umm", "hmm", "achha")
- **Code-switching**: natural mix of Hindi and English words in Roman script
"""


# ============================
# Audio & Chunking Utilities
# ============================
def load_audio_16k(wav_path: Path) -> np.ndarray:
    """Load 16kHz WAV as float32 mono."""
    audio, sr = sf.read(wav_path, dtype='float32')
    if sr != 16000:
        # Resample if needed
        audio = resample_poly(audio, 16000, sr)
    if audio.ndim == 2:
        audio = audio[:, 0]
    return audio


def rms_db(audio: np.ndarray) -> float:
    """RMS in dBFS."""
    rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
    if rms <= 0:
        return -120.0
    return 20.0 * np.log10(rms)


def find_silence_boundaries(audio: np.ndarray, sr: int = 16000) -> List[float]:
    """Find silence boundaries (in seconds) for chunking."""
    frame_ms = 50
    hop_ms = 25
    frame_samples = int(sr * frame_ms / 1000)
    hop_samples = int(sr * hop_ms / 1000)

    n_frames = (len(audio) - frame_samples) // hop_samples + 1
    silence_frames = []

    for i in range(n_frames):
        start = i * hop_samples
        end = start + frame_samples
        frame = audio[start:end]
        if rms_db(frame) < SILENCE_THRESHOLD_DB:
            silence_frames.append(i)

    # Group consecutive silence frames
    boundaries = []
    if not silence_frames:
        return boundaries

    group_start = silence_frames[0]
    for i in range(1, len(silence_frames)):
        if silence_frames[i] > silence_frames[i-1] + 1:
            # Gap in silence - end of group
            group_end = silence_frames[i-1]
            mid_frame = (group_start + group_end) // 2
            boundaries.append(mid_frame * hop_samples / sr)
            group_start = silence_frames[i]

    # Last group
    group_end = silence_frames[-1]
    mid_frame = (group_start + group_end) // 2
    boundaries.append(mid_frame * hop_samples / sr)

    return boundaries


def chunk_audio(
    audio: np.ndarray,
    draft_segments: List[Dict],
    sr: int = 16000
) -> List[Dict[str, Any]]:
    """
    Split audio into ~15s chunks at silence boundaries.
    Align with draft segments where possible.
    Returns list of chunks with: start, end, audio, draft_text, index.
    """
    duration = len(audio) / sr
    silence_bounds = find_silence_boundaries(audio, sr)

    chunks = []
    chunk_start = 0.0
    chunk_idx = 0

    while chunk_start < duration:
        # Target end
        target_end = min(chunk_start + CHUNK_TARGET_DURATION, duration)

        # Find best silence boundary near target
        best_boundary = target_end
        for bound in silence_bounds:
            if chunk_start + MIN_CHUNK_DURATION <= bound <= chunk_start + MAX_CHUNK_DURATION:
                if abs(bound - target_end) < abs(best_boundary - target_end):
                    best_boundary = bound

        chunk_end = best_boundary

        # Extract chunk audio
        start_sample = int(chunk_start * sr)
        end_sample = int(chunk_end * sr)
        chunk_audio = audio[start_sample:end_sample]

        # Find overlapping draft segments
        chunk_text_parts = []
        for seg in draft_segments:
            seg_start = seg['start']
            seg_end = seg['end']
            # Overlap check
            if seg_end > chunk_start and seg_start < chunk_end:
                chunk_text_parts.append(seg['text'].strip())

        draft_text = " ".join(chunk_text_parts).strip()

        chunks.append({
            "index": chunk_idx,
            "start": chunk_start,
            "end": chunk_end,
            "duration": chunk_end - chunk_start,
            "audio_samples": chunk_audio,
            "draft_text": draft_text,
            "unintelligible": False
        })

        chunk_start = chunk_end
        chunk_idx += 1

    return chunks


def save_chunk_wav(chunk: Dict, tag_dir: Path, scenario_id: str) -> Path:
    """Save chunk audio as WAV for web player."""
    chunk_dir = tag_dir / "chunks" / scenario_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunk_dir / f"chunk_{chunk['index']:03d}.wav"
    sf.write(chunk_path, chunk['audio_samples'], 16000, subtype='PCM_16')
    return chunk_path


def load_draft(tag_dir: Path, scenario_id: str) -> Optional[Dict]:
    """Load draft JSON for a scenario."""
    draft_path = tag_dir / f"{scenario_id}.draft.json"
    if not draft_path.exists():
        return None
    with open(draft_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_ref(tag_dir: Path, scenario_id: str) -> Optional[List[Dict]]:
    """Load existing reference corrections."""
    ref_path = tag_dir / f"{scenario_id}.ref.txt"
    if not ref_path.exists():
        return None
    with open(ref_path, 'r', encoding='utf-8') as f:
        lines = f.read().strip().split('\n')
    chunks = []
    for i, line in enumerate(lines):
        if line.startswith("[[UNINTELLIGIBLE]]"):
            chunks.append({"index": i, "text": "", "unintelligible": True})
        else:
            chunks.append({"index": i, "text": line, "unintelligible": False})
    return chunks


def save_ref(tag_dir: Path, scenario_id: str, chunks: List[Dict]):
    """Save reference corrections to .ref.txt."""
    ref_path = tag_dir / f"{scenario_id}.ref.txt"
    lines = []
    for chunk in chunks:
        if chunk.get('unintelligible', False):
            lines.append("[[UNINTELLIGIBLE]]")
        else:
            lines.append(chunk.get('text', '').strip())
    with open(ref_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


# ============================
# Routes
# ============================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voice Journal - Transcript Correction</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px; margin: 0 auto; padding: 20px;
            background: #f5f5f5; color: #333; line-height: 1.5;
        }
        h1 { color: #2c3e50; margin-bottom: 0.5rem; }
        .subtitle { color: #666; margin-bottom: 2rem; }
        .convention {
            background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px;
            padding: 15px; margin-bottom: 2rem; font-size: 0.9rem;
            white-space: pre-wrap;
        }
        .scenario-selector {
            display: flex; gap: 10px; margin-bottom: 2rem; flex-wrap: wrap;
        }
        .scenario-btn {
            padding: 10px 20px; border: 2px solid #ddd; background: white;
            border-radius: 6px; cursor: pointer; font-size: 0.9rem;
            transition: all 0.2s;
        }
        .scenario-btn:hover { border-color: #3498db; }
        .scenario-btn.active { background: #3498db; color: white; border-color: #3498db; }
        .scenario-btn.completed { background: #27ae60; color: white; border-color: #27ae60; }
        .progress-bar {
            height: 8px; background: #ecf0f1; border-radius: 4px; overflow: hidden; margin-bottom: 1rem;
        }
        .progress-fill {
            height: 100%; background: #3498db; transition: width 0.3s;
        }
        .progress-text { font-size: 0.9rem; color: #666; margin-bottom: 1.5rem; }
        .chunk {
            background: white; border-radius: 8px; padding: 20px; margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .chunk-header {
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;
        }
        .chunk-meta { font-size: 0.85rem; color: #666; }
        .unintelligible-badge {
            background: #e74c3c; color: white; padding: 2px 8px; border-radius: 12px;
            font-size: 0.75rem; font-weight: bold;
        }
        .audio-player { width: 100%; margin-bottom: 10px; }
        .controls {
            display: flex; gap: 10px; align-items: center; margin-bottom: 10px;
        }
        .speed-btn {
            padding: 5px 12px; border: 1px solid #ddd; background: white;
            border-radius: 4px; cursor: pointer; font-size: 0.85rem;
        }
        .speed-btn.active { background: #3498db; color: white; border-color: #3498db; }
        .unintelligible-toggle {
            display: flex; align-items: center; gap: 8px; font-size: 0.9rem;
        }
        textarea {
            width: 100%; min-height: 80px; padding: 10px; border: 1px solid #ddd;
            border-radius: 6px; font-family: 'Monaco', 'Menlo', monospace; font-size: 0.95rem;
            resize: vertical; transition: border-color 0.2s;
        }
        textarea:focus { outline: none; border-color: #3498db; box-shadow: 0 0 0 3px rgba(52,152,219,0.2); }
        .save-section {
            position: sticky; bottom: 20px; background: white; padding: 20px;
            border-radius: 8px; box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
            display: flex; justify-content: space-between; align-items: center;
        }
        .btn {
            padding: 12px 24px; border: none; border-radius: 6px; font-size: 1rem;
            cursor: pointer; font-weight: 500; transition: all 0.2s;
        }
        .btn-primary { background: #3498db; color: white; }
        .btn-primary:hover { background: #2980b9; }
        .btn-primary:disabled { background: #bdc3c7; cursor: not-allowed; }
        .btn-secondary { background: #95a5a6; color: white; }
        .status { padding: 10px; border-radius: 6px; margin-bottom: 1rem; }
        .status.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .status.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .status.info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .keyboard-hint { font-size: 0.8rem; color: #888; margin-top: 5px; }
    </style>
</head>
<body>
    <h1>🎙️ Voice Journal Transcript Correction</h1>
    <p class="subtitle">Tag: <strong>{{ tag }}</strong> | {{ convention }}</p>

    <div class="convention">{{ convention_text }}</div>

    <div class="scenario-selector" id="scenarioSelector">
        {% for scenario in scenarios %}
        <button class="scenario-btn {% if scenario.completed %}completed{% elif scenario.current %}active{% endif %}"
                data-scenario="{{ scenario.id }}" onclick="loadScenario('{{ scenario.id }}')">
            {{ scenario.name }} ({{ scenario.id }})
        </button>
        {% endfor %}
    </div>

    <div id="status"></div>

    <div class="progress-bar">
        <div class="progress-fill" id="progressFill" style="width: 0%"></div>
    </div>
    <div class="progress-text" id="progressText">Select a scenario to begin</div>

    <div id="chunksContainer"></div>

    <div class="save-section">
        <div>
            <button class="btn btn-secondary" onclick="saveProgress()">Save Progress</button>
            <span class="keyboard-hint">Ctrl+S to save | ←/→ to navigate chunks</span>
        </div>
        <button class="btn btn-primary" id="saveBtn" onclick="saveAndNext()">Save & Next Chunk</button>
    </div>

    <script>
        let currentScenario = null;
        let chunks = [];
        let currentChunkIndex = 0;
        let hasUnsavedChanges = false;

        const scenariosData = {{ scenarios_json|safe }};

        function showStatus(message, type = 'info') {
            const div = document.getElementById('status');
            div.innerHTML = `<div class="status ${type}">${message}</div>`;
        }

        function updateProgress() {
            const completed = chunks.filter(c => c.saved || c.unintelligible).length;
            const total = chunks.length;
            const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
            document.getElementById('progressFill').style.width = pct + '%';
            document.getElementById('progressText').textContent = `Chunk ${currentChunkIndex + 1}/${total} (${completed}/${total} corrected)`;
        }

        async function loadScenario(scenarioId) {
            currentScenario = scenarioId;
            currentChunkIndex = 0;
            showStatus(`Loading ${scenarioId}...`, 'info');

            try {
                const resp = await fetch(`/api/chunks/${scenarioId}`);
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.error || 'Failed to load');

                chunks = data.chunks;
                renderChunks();
                updateProgress();
                showChunk(0);
                showStatus(`Loaded ${scenarioId}: ${chunks.length} chunks`, 'success');

                // Update button states
                document.querySelectorAll('.scenario-btn').forEach(btn => {
                    btn.classList.remove('active');
                    if (btn.dataset.scenario === scenarioId) btn.classList.add('active');
                });
            } catch (e) {
                showStatus('Error: ' + e.message, 'error');
            }
        }

        function renderChunks() {
            const container = document.getElementById('chunksContainer');
            container.textContent = ''; // Clear safely
            chunks.forEach((chunk, i) => {
                const div = document.createElement('div');
                div.className = 'chunk';
                div.id = `chunk-${i}`;
                div.style.display = 'none';
                div.innerHTML = `
                    <div class="chunk-header">
                        <span class="chunk-meta">
                            Chunk ${i+1}/${chunks.length} &bull;
                            ${chunk.start.toFixed(1)}s&ndash;${chunk.end.toFixed(1)}s &bull;
                            ${chunk.duration.toFixed(1)}s
                        </span>
                        <span class="unintelligible-badge" id="unintBadge-${i}" style="display: none;">Unintelligible</span>
                    </div>
                    <audio class="audio-player" id="audio-${i}" controls preload="metadata">
                        <source src="/api/audio/${currentScenario}/${i}" type="audio/wav">
                    </audio>
                    <div class="controls">
                        <button class="speed-btn" onclick="setSpeed(${i}, 0.75)" id="speed-075-${i}">0.75&times;</button>
                        <button class="speed-btn active" onclick="setSpeed(${i}, 1.0)" id="speed-100-${i}">1&times;</button>
                        <button class="speed-btn" onclick="setSpeed(${i}, 1.25)" id="speed-125-${i}">1.25&times;</button>
                        <button class="speed-btn" onclick="setSpeed(${i}, 1.5)" id="speed-150-${i}">1.5&times;</button>
                        <label class="unintelligible-toggle">
                            <input type="checkbox" id="unint-${i}" onchange="toggleUnintelligible(${i})">
                            Mark unintelligible
                        </label>
                    </div>
                    <textarea id="text-${i}" oninput="onTextChange(${i})" placeholder="Type correction here..."></textarea>
                `;
                // Safely set draft text via textContent (not user-controlled, but safe practice)
                const textarea = div.querySelector(`#text-${i}`);
                textarea.value = chunk.draft_text || '';
                container.appendChild(div);
            });
        }

        function showChunk(index) {
            if (index < 0 || index >= chunks.length) return;
            chunks.forEach((_, i) => {
                document.getElementById(`chunk-${i}`).style.display = i === index ? 'block' : 'none';
            });
            currentChunkIndex = index;
            updateProgress();
            // Focus textarea
            setTimeout(() => document.getElementById(`text-${index}`)?.focus(), 50);
        }

        function setSpeed(chunkIdx, speed) {
            const audio = document.getElementById(`audio-${chunkIdx}`);
            audio.playbackRate = speed;
            document.querySelectorAll(`#chunk-${chunkIdx} .speed-btn`).forEach(btn => {
                btn.classList.toggle('active', parseFloat(btn.textContent) === speed);
            });
        }

        function toggleUnintelligible(chunkIdx) {
            const checkbox = document.getElementById(`unint-${chunkIdx}`);
            const badge = document.getElementById(`unintBadge-${chunkIdx}`);
            const textarea = document.getElementById(`text-${chunkIdx}`);
            chunks[chunkIdx].unintelligible = checkbox.checked;
            badge.style.display = checkbox.checked ? 'inline-block' : 'none';
            textarea.disabled = checkbox.checked;
            if (checkbox.checked) textarea.value = '';
            hasUnsavedChanges = true;
        }

        function onTextChange(chunkIdx) {
            chunks[chunkIdx].text = document.getElementById(`text-${chunkIdx}`).value;
            chunks[chunkIdx].saved = false;
            hasUnsavedChanges = true;
        }

        async function saveProgress() {
            if (!currentScenario) return;
            showStatus('Saving...', 'info');
            try {
                const resp = await fetch(`/api/save/${currentScenario}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chunks })
                });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.error || 'Save failed');

                chunks.forEach(c => c.saved = true);
                hasUnsavedChanges = false;
                updateProgress();
                showStatus('Progress saved ✓', 'success');
            } catch (e) {
                showStatus('Save failed: ' + e.message, 'error');
            }
        }

        async function saveAndNext() {
            await saveProgress();
            if (currentChunkIndex < chunks.length - 1) {
                showChunk(currentChunkIndex + 1);
            } else {
                showStatus('All chunks completed for this scenario! 🎉', 'success');
                // Mark scenario as completed in UI
                document.querySelectorAll('.scenario-btn').forEach(btn => {
                    if (btn.dataset.scenario === currentScenario) {
                        btn.classList.add('completed');
                        btn.classList.remove('active');
                    }
                });
            }
        }

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'TEXTAREA') return;
            if (e.key === 'ArrowRight' && currentChunkIndex < chunks.length - 1) {
                showChunk(currentChunkIndex + 1);
            } else if (e.key === 'ArrowLeft' && currentChunkIndex > 0) {
                showChunk(currentChunkIndex - 1);
            } else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                saveProgress();
            }
        });

        // Warn on unsaved changes
        window.addEventListener('beforeunload', (e) => {
            if (hasUnsavedChanges) {
                e.preventDefault();
                e.returnValue = '';
            }
        });
    </script>
</body>
</html>
"""


def create_app(tag: str):
    """Create and configure the Flask app for a specific tag."""
    global CURRENT_TAG, TAG_DIR
    CURRENT_TAG = tag
    TAG_DIR = Path(__file__).parent / tag

    if not TAG_DIR.exists():
        raise FileNotFoundError(f"Tag directory not found: {TAG_DIR}")

    # Pre-load chunks for all scenarios
    for scenario_id in SCENARIOS:
        draft = load_draft(TAG_DIR, scenario_id)
        if not draft:
            continue
        audio = load_audio_16k(TAG_DIR / f"{scenario_id}.wav")
        chunks = chunk_audio(audio, draft.get('segments', []))
        # Save chunk WAVs
        for chunk in chunks:
            save_chunk_wav(chunk, TAG_DIR, scenario_id)
        # Load existing ref if any
        ref_chunks = load_ref(TAG_DIR, scenario_id)
        if ref_chunks:
            for i, rc in enumerate(ref_chunks):
                if i < len(chunks):
                    chunks[i]['text'] = rc.get('text', chunks[i]['draft_text'])
                    chunks[i]['unintelligible'] = rc.get('unintelligible', False)
                    chunks[i]['saved'] = True

    @app.route('/')
    def index():
        scenarios_info = []
        for scenario_id in SCENARIOS:
            draft = load_draft(TAG_DIR, scenario_id)
            ref = load_ref(TAG_DIR, scenario_id)
            completed = ref is not None and len(ref) > 0
            current = False  # Will be set by JS
            scenarios_info.append({
                'id': scenario_id,
                'name': scenario_id.replace('SPONT_', '').replace('_', ' ').title(),
                'completed': completed,
                'current': current,
                'has_draft': draft is not None
            })
        return render_template_string(HTML_TEMPLATE,
            tag=tag,
            convention="Reference Convention",
            convention_text=REFERENCE_CONVENTION,
            scenarios=scenarios_info,
            scenarios_json=json.dumps(scenarios_info)
        )

    @app.route('/api/chunks/<scenario_id>')
    def get_chunks(scenario_id):
        draft = load_draft(TAG_DIR, scenario_id)
        if not draft:
            return jsonify({'error': 'No draft found'}), 404
        audio = load_audio_16k(TAG_DIR / f"{scenario_id}.wav")
        chunks = chunk_audio(audio, draft.get('segments', []))
        # Load existing ref
        ref_chunks = load_ref(TAG_DIR, scenario_id)
        if ref_chunks:
            for i, rc in enumerate(ref_chunks):
                if i < len(chunks):
                    chunks[i]['text'] = rc.get('text', chunks[i]['draft_text'])
                    chunks[i]['unintelligible'] = rc.get('unintelligible', False)
                    chunks[i]['saved'] = True
        else:
            for chunk in chunks:
                chunk['text'] = chunk['draft_text']
                chunk['unintelligible'] = False
                chunk['saved'] = False
        # Remove audio_samples from response (sent via separate endpoint)
        for chunk in chunks:
            chunk.pop('audio_samples', None)
        return jsonify({'chunks': chunks})

    @app.route('/api/audio/<scenario_id>/<int:chunk_idx>')
    def get_chunk_audio(scenario_id, chunk_idx):
        chunk_path = TAG_DIR / "chunks" / scenario_id / f"chunk_{chunk_idx:03d}.wav"
        if not chunk_path.exists():
            return jsonify({'error': 'Chunk not found'}), 404
        return send_file(chunk_path, mimetype='audio/wav')

    @app.route('/api/save/<scenario_id>', methods=['POST'])
    def save_scenario(scenario_id):
        data = request.get_json()
        chunks = data.get('chunks', [])
        save_ref(TAG_DIR, scenario_id, chunks)
        return jsonify({'success': True, 'saved': len(chunks)})

    return app


def main():
    parser = argparse.ArgumentParser(
        description="Flask UI for correcting draft transcripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eval/correct_ui.py --tag desk
  python eval/correct_ui.py --tag lav --port 5001 --host 0.0.0.0
        """
    )
    parser.add_argument('--tag', required=True, help="Tag for the recording session")
    parser.add_argument('--port', type=int, default=5001, help="Port to run on (default: 5001)")
    parser.add_argument('--host', default='0.0.0.0', help="Host to bind (default: 0.0.0.0 for LAN/Tailscale)")
    parser.add_argument('--debug', action='store_true', help="Enable debug mode")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"🌐 CORRECTION UI: {args.tag}")
    print(f"   Starting on http://{args.host}:{args.port}")
    print(f"   Scenarios: {', '.join(SCENARIOS)}")
    print(f"{'='*60}")
    print(f"\n📋 Reference Convention:")
    print(REFERENCE_CONVENTION.strip())
    print(f"\n🔗 Open in browser: http://<your-tailscale-ip>:{args.port}")
    print(f"   Or locally: http://localhost:{args.port}")
    print(f"{'='*60}\n")

    app = create_app(args.tag)
    run_simple(args.host, args.port, app, use_reloader=args.debug, use_debugger=args.debug)


if __name__ == "__main__":
    sys.exit(main())