#!/usr/bin/env python3
"""
Voice Journal Status CLI.
Check backlog, processing status, and system health.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from config.settings import Config
from storage.database import SQLiteStore, BacklogTracker
from processing.batch_processor import BatchProcessor


def get_status(config: Config) -> Dict[str, Any]:
    """
    Get comprehensive system status.

    Returns:
        Dict with backlog, database, and config info
    """
    status = {
        "timestamp": datetime.now().isoformat(),
        "backlog": {},
        "database": {},
        "config": {}
    }

    # Backlog status
    try:
        backlog = BacklogTracker(config)
        status["backlog"] = backlog.get_status()
    except Exception as e:
        status["backlog"]["error"] = str(e)

    # Database status
    try:
        db = SQLiteStore(config)
        stats = db.get_stats(days=7)
        status["database"] = {
            "total_last_7_days": stats.get("total", 0),
            "with_shivangi": stats.get("with_shivangi", 0),
            "by_quality": stats.get("by_quality", {}),
            "db_path": str(db.db_path)
        }
    except Exception as e:
        status["database"]["error"] = str(e)

    # Config summary
    status["config"] = {
        "asr_model": config.asr.model_size,
        "compute_type": config.asr.compute_type,
        "segment_merging_gap": config.segment_merging.merge_gap_seconds,
        "min_transcription_unit": config.segment_merging.min_transcription_unit_seconds,
        "backlog_threshold": config.scheduler.backlog_overflow_hours,
        "fallback_model": config.scheduler.fallback_model,
        "guaranteed_window": f"{config.scheduler.guaranteed_window_start_hour}:00 - {config.scheduler.guaranteed_window_end_hour}:00"
    }

    return status


def format_status(status: Dict[str, Any], format: str = "text") -> str:
    """Format status for output."""
    if format == "json":
        return json.dumps(status, indent=2)

    # Text format
    lines = []
    lines.append("="*60)
    lines.append("VOICE JOURNAL STATUS")
    lines.append("="*60)
    lines.append(f"Timestamp: {status['timestamp']}")
    lines.append("")

    # Backlog
    backlog = status.get("backlog", {})
    lines.append("--- BACKLOG ---")
    lines.append(f"  Total queued: {backlog.get('total_hours', 0):.1f} hours")
    lines.append(f"  Segments pending: {backlog.get('segment_count', 0)}")

    if backlog.get('growth_warning'):
        lines.append("  ⚠️  WARNING: Backlog growing (not shrinking)")

    overflow_threshold = backlog.get('overflow_threshold', 24.0)
    is_overflow = backlog.get('is_overflow', False)
    lines.append(f"  Overflow threshold: {overflow_threshold:.1f}h")

    if is_overflow:
        lines.append("  🔄 USING FALLBACK MODEL (overflow active)")

    lines.append("")

    # Database
    db = status.get("database", {})
    lines.append("--- DATABASE (LAST 7 DAYS) ---")
    lines.append(f"  Total conversations: {db.get('total_last_7_days', 0)}")
    lines.append(f"  With Shivangi: {db.get('with_shivangi', 0)}")

    by_quality = db.get("by_quality", {})
    if by_quality:
        lines.append("  By quality:")
        for quality, count in by_quality.items():
            lines.append(f"    {quality}: {count}")

    lines.append("")

    # Config
    cfg = status.get("config", {})
    lines.append("--- CONFIGURATION ---")
    lines.append(f"  ASR model: {cfg.get('asr_model', 'unknown')} ({cfg.get('compute_type', 'unknown')})")
    lines.append(f"  Segment merge gap: {cfg.get('segment_merging_gap', 2.5)}s")
    lines.append(f"  Min transcription unit: {cfg.get('min_transcription_unit', 5.0)}s")
    lines.append(f"  Fallback model: {cfg.get('fallback_model', 'unknown')}")
    lines.append(f"  Guaranteed window: {cfg.get('guaranteed_window', 'unknown')}")
    lines.append("")

    # Summary
    lines.append("--- SUMMARY ---")
    backlog_hours = backlog.get('total_hours', 0)
    if backlog_hours < 1:
        lines.append("  ✅ Backlog under control (< 1h)")
    elif backlog_hours < overflow_threshold:
        lines.append(f"  ⚠️  Backlog moderate ({backlog_hours:.1f}h), will clear soon")
    else:
        lines.append(f"  🔄 Backlog high ({backlog_hours:.1f}h), using fallback model")

    # Estimated catch-up time
    if backlog_hours > 0 and not is_overflow:
        # Assume ~2x RTF for large-v3 on i3 (conservative)
        rtf_estimate = 2.0
        catchup_hours = backlog_hours * rtf_estimate
        lines.append(f"  Estimated catch-up: {catchup_hours:.1f}h of processing")

    lines.append("="*60)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Check Voice Journal status"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config file"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format"
    )

    args = parser.parse_args()

    # Load config
    if args.config:
        config = Config.from_yaml(args.config)
    else:
        config = Config()

    # Get status
    status = get_status(config)

    # Format and print
    output = format_status(status, format=args.format)
    print(output)

    # Exit with warning code if backlog is problematic
    backlog_hours = status.get("backlog", {}).get("total_hours", 0)
    if backlog_hours > config.scheduler.backlog_overflow_hours:
        sys.exit(2)  # Warning exit code

    return 0


if __name__ == "__main__":
    sys.exit(main())
