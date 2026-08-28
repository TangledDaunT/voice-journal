# Manual Deployment Instructions

## On your Mac (local), run this to push code:
```bash
cd /Users/shreyansh/Documents/sound_transcribe/voice_journal
git push origin main
```

## Then SSH into your laptop and run these commands:

### Step 1: SSH into laptop
```bash
ssh shreyansh@100.99.161.57
```
(Enter password when prompted)

### Step 2: Navigate to project directory
```bash
cd ~/voice_journal
```

### Step 3: Pull latest code
```bash
git pull origin main
```

### Step 4: Activate virtual environment
```bash
source venv/bin/activate
```

### Step 5: Install updated package
```bash
pip install -e .
```

### Step 6: Run integration tests
```bash
python test_integration.py
```

### Step 7: Check if Ollama is running
```bash
ollama list
```
If not running:
```bash
ollama serve &
ollama pull llama3.2:3b
```

### Step 8: Kill old daemon if running
```bash
pkill -f "python.*daemon.py"
```

### Step 9: Start the daemon
```bash
nohup python daemon.py > logs/daemon.log 2>&1 &
```

### Step 10: Check if it's running
```bash
tail -f logs/voice_journal.log
```

Press Ctrl+C to stop viewing logs

---

## To configure external microphone:

```bash
# List audio devices
python -c "import sounddevice as sd; print(sd.query_devices())"

# Look for your external microphone in the list
# Note the device index number
```

Then update the config file (if needed) to specify the device.

---

## Quick deployment (copy-paste everything):

```bash
cd ~/voice_journal && \
git pull origin main && \
source venv/bin/activate && \
pip install -e . && \
python test_integration.py && \
pkill -f "python.*daemon.py" ; \
nohup python daemon.py > logs/daemon.log 2>&1 & \
sleep 2 && \
tail -n 20 logs/voice_journal.log
```

---

## Check status anytime:
```bash
ps aux | grep daemon.py
tail -f logs/voice_journal.log
```

## Stop daemon:
```bash
pkill -f "python.*daemon.py"
```

## Mute/unmute processing:
```bash
python -m utils.mute toggle
```
