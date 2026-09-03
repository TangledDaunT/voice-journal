"""Manually compare stock Whisper and Hinglish ASR on real audio clips.

Usage:
    python compare_asr_models.py path/to/clips

The folder may contain wav/mp3/m4a/flac files or staged .npy files. This is
intentionally a readable comparison report, not an automated accuracy score.
"""

import argparse
from pathlib import Path
from typing import Iterable

import librosa
import numpy as np
from faster_whisper import WhisperModel

from audio_capture.preprocess import AudioPreprocessor
from config.settings import Config


OLD_MODEL = "large-v3"
NEW_MODEL = "Hub84/faster-whisper-hinglish-prime"
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".npy"}


def find_clips(folder: Path) -> Iterable[Path]:
    return sorted(path for path in folder.iterdir() if path.suffix.lower() in AUDIO_EXTENSIONS)


def load_audio(path: Path, sample_rate: int) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        audio = np.load(path)
        if audio.ndim == 2:
            audio = audio[:, 0]
        return audio.astype(np.float32)
    audio, _ = librosa.load(path, sr=sample_rate, mono=True)
    return audio.astype(np.float32)


def transcribe(model: WhisperModel, audio: np.ndarray, config: Config) -> list[dict]:
    segments, _ = model.transcribe(
        audio,
        language=config.asr.language,
        beam_size=config.asr.beam_size,
        vad_filter=config.asr.vad_filter,
        condition_on_previous_text=config.asr.condition_on_previous_text,
        temperature=0.0,
        initial_prompt=config.asr.initial_prompt,
    )
    return [
        {
            "text": segment.text.strip(),
            "avg_logprob": getattr(segment, "avg_logprob", None),
            "no_speech_prob": getattr(segment, "no_speech_prob", None),
        }
        for segment in segments
    ]


def format_segments(segments: list[dict]) -> str:
    if not segments:
        return "(no segments)"
    return " | ".join(
        f'{item["text"]} [avg_logprob={item["avg_logprob"]}, '
        f'no_speech_prob={item["no_speech_prob"]}]'
        for item in segments
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips", type=Path, help="Folder containing real audio clips")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--config", type=Path, help="Optional YAML config for ASR settings")
    args = parser.parse_args()

    config = Config.from_yaml(str(args.config)) if args.config else Config()
    clips = list(find_clips(args.clips))
    if not clips:
        parser.error(f"No supported audio clips found in {args.clips}")

    preprocessor = AudioPreprocessor(config)
    models = {
        OLD_MODEL: WhisperModel(OLD_MODEL, device=args.device, compute_type=args.compute_type),
        NEW_MODEL: WhisperModel(NEW_MODEL, device=args.device, compute_type=args.compute_type),
    }

    for clip in clips:
        raw_audio = load_audio(clip, config.audio.sample_rate)
        print(f"\n=== {clip.name} ===")
        for denoise in (True, False):
            preprocessor.enable_denoising = denoise
            processed = preprocessor.preprocess(raw_audio, config.audio.sample_rate).audio
            print(f"\n--- denoise={'on' if denoise else 'off'} ---")
            for model_name, model in models.items():
                print(f"{model_name}: {format_segments(transcribe(model, processed, config))}")


if __name__ == "__main__":
    main()