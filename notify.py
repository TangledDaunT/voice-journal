""
WhatsApp notification module - DISABLED in refactor
""

import logging
logger = logging.getLogger(__name__)

def send_daily_summary():
    """Send daily summary via WhatsApp - DISABLED"""
    logger.info("WhatsApp daily summary disabled in refactor")
    return False

if __name__ == "__main__":
    send_daily_summary()
