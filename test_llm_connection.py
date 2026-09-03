#!/usr/bin/env python3
"""
Test script to diagnose LLM connection issues.
"""

import sys
import json
import requests
from config.settings import Config

def test_ollama_connection():
    """Test if Ollama is accessible."""
    config = Config()

    print(f"Testing connection to: {config.llm.ollama_host}")
    print(f"Model configured: {config.llm.model}")
    print()

    # Test 1: Check if server is running
    try:
        response = requests.get(f"{config.llm.ollama_host}/api/tags", timeout=5)
        if response.status_code == 200:
            print("✓ Ollama server is running")
            models = response.json().get("models", [])
            print(f"  Available models: {[m.get('name') for m in models]}")
        else:
            print(f"✗ Ollama server returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to Ollama server - Is it running?")
        print(f"  Expected at: {config.llm.ollama_host}")
        print("\nTo start Ollama:")
        print("  1. Install: brew install ollama")
        print("  2. Start: ollama serve")
        print("  3. Pull model: ollama pull llama3.2:3b")
        return False
    except Exception as e:
        print(f"✗ Error checking Ollama: {e}")
        return False

    # Test 2: Check if model is available
    try:
        response = requests.get(f"{config.llm.ollama_host}/api/tags", timeout=5)
        models = response.json().get("models", [])
        model_names = [m.get("name", "") for m in models]

        if any(config.llm.model in name for name in model_names):
            print(f"✓ Model '{config.llm.model}' is available")
        else:
            print(f"✗ Model '{config.llm.model}' is NOT pulled")
            print(f"\nTo pull the model: ollama pull {config.llm.model}")
            return False
    except Exception as e:
        print(f"✗ Error checking model: {e}")
        return False

    # Test 3: Test actual classification
    print("\nTesting classification with sample input...")
    test_prompt = """You are analyzing a transcript from a personal voice journal.

Classify this conversation and return JSON with:
1. "source_type": One of "live_conversation", "self_talk", "media_or_unknown"
2. "summary": 1-2 sentence summary

TRANSCRIPT:
Testing the LLM connection.

Return ONLY valid JSON.
"""

    try:
        payload = {
            "model": config.llm.model,
            "messages": [{"role": "user", "content": test_prompt}],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 100
            }
        }

        response = requests.post(
            f"{config.llm.ollama_host}/api/chat",
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            content = result.get("message", {}).get("content", "")
            print("✓ LLM responded successfully")
            print(f"  Response: {content[:100]}...")
            return True
        else:
            print(f"✗ LLM request failed with status {response.status_code}")
            return False

    except requests.Timeout:
        print("✗ LLM request timed out (30s)")
        return False
    except Exception as e:
        print(f"✗ Error calling LLM: {e}")
        return False

if __name__ == "__main__":
    success = test_ollama_connection()
    sys.exit(0 if success else 1)
