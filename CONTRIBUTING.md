# Contributing to Voice Journal

Thank you for your interest in contributing!

## Development Setup

1. Fork and clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install pytest black ruff  # dev dependencies
   ```

## Running Tests

```bash
pytest tests/ -v
```

## Code Style

- Use Black for formatting
- Use Ruff for linting
- Follow PEP 8 guidelines

## Pull Request Process

1. Create a feature branch
2. Make your changes
3. Run tests and linting
4. Submit a pull request

## Code of Conduct

Be respectful and constructive in all interactions.
