.PHONY: test install clean lint format

install:
	python -m venv venv
	source venv/bin/activate && pip install -r requirements.txt

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

lint:
	ruff check .

format:
	black .

test:
	pytest tests/ -v

run:
	source venv/bin/activate && python -m voice_journal.daemon

setup:
	./setup.sh

status:
	./vj-control.sh status

mute:
	./vj-control.sh mute

unmute:
	./vj-control.sh unmute

logs:
	tail -f logs/voice_journal.log

download-model:
	mkdir -p models
	wget -O models/silero_vad.onnx https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx
