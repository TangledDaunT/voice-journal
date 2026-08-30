#!/bin/bash
# Run all tests with coverage

source venv/bin/activate

echo "Running all tests..."
pytest tests/ -v --tb=short

echo ""
echo "Running coverage..."
pytest tests/ --cov=. --cov-report=term-missing --cov-report=html

echo ""
echo "Coverage report: htmlcov/index.html"
