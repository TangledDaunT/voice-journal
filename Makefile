.PHONY: help install test lint format clean status batch benchmark validate

help:
	@echo "Voice Journal - Available commands:"
	@echo ""
	@echo "  make install     Install dependencies"
	@echo "  make test         Run all tests"
	@echo "  make lint         Run linters"
	@echo "  make format       Format code"
	@echo "  make clean        Clean build artifacts"
	@echo "  make status       Check system status"
	@echo "  make batch        Run batch processor manually"
	@echo "  make benchmark    Run benchmark on sample audio"
	@echo "  make validate     Validate configuration"
	@echo ""

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

lint:
	ruff check .
	mypy .

format:
	ruff format .
	ruff check --fix .

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache .mypy_cache
	rm -rf *.egg-info build dist
	find . -type d -name "__pycache__" -exec rm -rf {} +

status:
	python status.py

batch:
	python -m processing.batch_processor

benchmark:
	@echo "Usage: python benchmark_asr.py <audio_file>"
	@echo "Example: python benchmark_asr.py test_audio.m4a"

validate:
	python scripts/validate_config.py

daemon:
	python daemon_v2.py

check_backlog:
	python status.py --format json | jq '.backlog'
