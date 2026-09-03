#!/usr/bin/env python3
"""Quick test of LLM classification on HP laptop."""

import json
import requests

# Test LLM with sample classification
def test_qwen_classification():
    print("Testing qwen2.5:7b classification...")

    prompt = """You are analyzing a candidate slang/term from Hindi-English code-switched conversations.

TERM: बेटा (beta)
OCCURRENCES: 5 times across 4 conversations
EXAMPLE: "arey beta, tu kab aa rahi hai?"

Should this be added to a PERSONAL glossary?

EXCLUSION (reject if common Hindi word known to all speakers):
- Common words: यार, मतलब, अच्छा, ठीक, etc.

INCLUSION (accept if personal/shared meaning):
- Nickname, inside joke, private shorthand
- Special meaning between these two people

Return JSON:
{
  "should_include": true or false,
  "reason": "explanation",
  "inferred_meaning": "if true, explain the meaning"
}
"""

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen2.5:1.5b",  # Use smaller, faster model
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.2}
            },
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            content = result.get("message", {}).get("content", "")
            print(f"\nResponse:\n{content}")

            # Try to parse JSON
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end > 0:
                data = json.loads(content[start:end])
                print(f"\nParsed result:")
                print(json.dumps(data, indent=2))
                return True
        else:
            print(f"Error: {response.status_code}")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    # Check if Ollama is running
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            print("✓ Ollama is running")
            models = r.json().get("models", [])
            print(f"Available models: {[m['name'] for m in models]}")
            test_qwen_classification()
        else:
            print("✗ Ollama not responding")
    except:
        print("✗ Cannot connect to Ollama at localhost:11434")
