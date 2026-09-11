#!/bin/bash
cd /home/shreyansh/voice-journal
source venv/bin/activate
hermes -z "$(cat mission.txt)" >> /home/shreyansh/voice-journal/mission.log 2>&1
