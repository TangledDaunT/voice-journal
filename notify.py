#!/usr/bin/env python3
"""
WhatsApp Daily Summary Sender.
Sends daily voice journal summaries to Shreyansh via WhatsApp.
"""

import sys
import os
import sqlite3
import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "voice_journal.db"
SHREYANSH_NUMBER = "+917754008079"  # WhatsApp number to send to


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def generate_daily_summary(date_str=None):
    """Generate daily summary for WhatsApp."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get today's stats
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_shivangi_conversation = 1 THEN 1 ELSE 0 END) as with_shivangi,
            SUM(duration_seconds) as total_duration,
            SUM(CASE WHEN source_type = 'self_talk' THEN 1 ELSE 0 END) as self_talk,
            SUM(CASE WHEN source_type = 'media_or_unknown' THEN 1 ELSE 0 END) as media
        FROM conversations
        WHERE date = ?
    """, (date_str,))

    stats = cursor.fetchone()

    if not stats or stats["total"] == 0:
        conn.close()
        return None

    total_minutes = round((stats["total_duration"] or 0) / 60)

    # Get Shivangi conversations
    cursor.execute("""
        SELECT start_time, summary, quality, duration_seconds
        FROM conversations
        WHERE date = ? AND is_shivangi_conversation = 1
        ORDER BY start_time
    """, (date_str,))

    shivangi_convs = cursor.fetchall()

    # Get quality distribution
    cursor.execute("""
        SELECT quality, COUNT(*) as count
        FROM conversations
        WHERE date = ? AND quality != 'not_applicable'
        GROUP BY quality
    """, (date_str,))

    quality_stats = {row["quality"]: row["count"] for row in cursor.fetchall()}
    conn.close()

    # Build message
    message = f"""📱 *Voice Journal - Daily Summary*
📅 {date_str}

📊 *Today's Stats:*
• Total Conversations: {stats['total']}
• Total Time: {total_minutes} minutes
• Self-talk sessions: {stats['self_talk']}
• Media detected: {stats['media']}

💕 *With Shivangi:* {stats['with_shivangi']} conversations
"""

    if shivangi_convs:
        message += "\n_Recent moments with Shivangi:_\n"
        for conv in shivangi_convs[:3]:
            emoji = "😊" if conv["quality"] == "good" else ("😔" if conv["quality"] == "tense" else "💬")
            summary = conv["summary"][:50] + "..." if conv["summary"] and len(conv["summary"]) > 50 else conv["summary"]
            message += f"{emoji} {conv['start_time']}: {summary or 'Conversation logged'}\n"

    # Quality summary
    if quality_stats:
        message += f"\n📈 *Quality:* "
        quality_parts = []
        for q, count in quality_stats.items():
            if q == "good":
                quality_parts.append(f"😊 {count} good")
            elif q == "tense":
                quality_parts.append(f"😔 {count} tense")
            elif q == "neutral":
                quality_parts.append(f"😐 {count} neutral")
        message += " | ".join(quality_parts)

    message += "\n\n_Keep journaling! 🎙️_"

    return message


def send_whatsapp_message(message, number=SHREYANSH_NUMBER):
    """
    Send WhatsApp message using wacli.

    Args:
        message: Message text to send
        number: WhatsApp number (default: Shreyansh's number)

    Returns:
        bool: True if successful
    """
    try:
        # Clean number format (remove + and formatting)
        clean_number = number.replace("+", "").replace("-", "").replace(" ", "")

        # Use wacli to send message with correct syntax
        result = subprocess.run(
            ["wacli", "send", "text", "--to", clean_number, "--message", message],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print(f"✓ Message sent to {number}")
            return True
        else:
            print(f"✗ Failed to send: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("✗ Timeout sending message")
        return False
    except FileNotFoundError:
        print("✗ wacli not found. Please install it.")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def send_daily_summary():
    """Send daily summary to WhatsApp."""
    print(f"\n{'='*60}")
    print("Voice Journal - WhatsApp Daily Summary")
    print(f"{'='*60}")

    message = generate_daily_summary()

    if not message:
        print("No conversations recorded today. Nothing to send.")
        return False

    print(f"\nMessage preview:\n{'-'*40}")
    print(message)
    print(f"{'-'*40}\n")

    success = send_whatsapp_message(message)

    if success:
        print(f"\n✓ Daily summary sent successfully!")
    else:
        print(f"\n✗ Failed to send daily summary")

    return success


def send_test_message():
    """Send a test message to verify WhatsApp is working."""
    test_msg = """📱 Voice Journal Test

👋 This is a test message from Voice Journal!

If you received this, WhatsApp notifications are working correctly.

_Voice Journal_"""
    return send_whatsapp_message(test_msg)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Send voice journal summaries via WhatsApp")
    parser.add_argument("--test", action="store_true", help="Send test message")
    parser.add_argument("--date", type=str, help="Specific date (YYYY-MM-DD)")
    parser.add_argument("--number", type=str, default=SHREYANSH_NUMBER, help="WhatsApp number")

    args = parser.parse_args()

    if args.test:
        send_test_message()
    else:
        send_daily_summary()


if __name__ == "__main__":
    main()
