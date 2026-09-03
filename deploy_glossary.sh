#!/bin/bash
# Deploy glossary pipeline to HP laptop

set -e

HP_USER="shreyansh"
HP_IP="100.99.161.57"
REMOTE_DIR="$HP_USER@$HP_IP:~/voice_journal_src"

echo "Deploying glossary pipeline to HP laptop..."

# Stop daemon if running
echo "Stopping daemon..."
sshpass -p '38000' ssh $HP_USER@$HP_IP "pkill -f daemon_v2.py" || true

# Sync new glossary module
echo "Syncing glossary module..."
sshpass -p '38000' scp -r voice-journal/glossary $REMOTE_DIR/

# Sync updated modules
echo "Syncing updated modules..."
sshpass -p '38000' scp voice-journal/storage/database.py $REMOTE_DIR/storage/
sshpass -p '38000' scp voice-journal/scripts/run_glossary_weekly.py $REMOTE_DIR/scripts/

# Sync config
sshpass -p '38000' scp voice-journal/config/default_config.yaml $REMOTE_DIR/config/

# Install new dependency
echo "Installing indic-transliteration..."
sshpass -p '38000' ssh $HP_USER@$HP_IP "cd ~/voice_journal_src && source venv/bin/activate && pip install indic-transliteration"

# Test import
echo "Testing imports..."
sshpass -p '38000' ssh $HP_USER@$HP_IP "cd ~/voice_journal_src && source venv/bin/activate && python3 -c 'from glossary import extract_candidates; print(\"✓ Glossary module imported successfully\")'"

echo ""
echo "Deployment complete!"
echo "To test: ssh $HP_USER@$HP_IP 'cd ~/voice_journal_src && source venv/bin/activate && python3 scripts/run_glossary_weekly.py --dry-run'"
