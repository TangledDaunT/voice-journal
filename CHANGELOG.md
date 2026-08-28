# Changelog

## [1.0.0] - 2024-01-XX

### Added
- 8-stage pipeline for voice journaling
- Continuous audio capture with ring buffer
- Silero VAD for speech detection
- Voice profile calibration for Shreyansh and Shivangi
- faster-whisper ASR with Hindi+English support
- Conversation grouping with media detection
- LLM classification via Ollama
- Obsidian vault integration
- SQLite FTS5 search index
- Mute control with desktop notifications
- Systemd service for daemon management

### Security
- All processing is local - no cloud APIs
- Voice profiles stored locally
- Audio files not included in repository
