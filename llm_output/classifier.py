"""
Stage 6: LLM Classification via Ollama.
Classifies conversation units semantically using local LLM.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any
import requests

from config.settings import Config
from conversation.grouping import ConversationUnit
from utils.logger import logger, log_stage, log_metric


# Classification schema for structured output
CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "source_type": {
            "type": "string",
            "enum": ["live_conversation", "self_talk", "media_or_unknown"]
        },
        "participants": {
            "type": "array",
            "items": {"type": "string", "enum": ["shreyansh", "shivangi", "unknown"]}
        },
        "is_shivangi_conversation": {"type": "boolean"},
        "quality": {
            "type": "string",
            "enum": ["good", "neutral", "tense", "not_applicable"]
        },
        "summary": {"type": "string"},
        "confidence_note": {"type": "string"}
    },
    "required": ["source_type", "participants", "is_shivangi_conversation", "quality", "summary"]
}


CLASSIFICATION_PROMPT = """You are analyzing a transcript from a personal voice journal.

The transcript comes from automatic speech recognition and may contain errors. The speakers are tagged as:
- "Shreyansh" - the user (male)
- "Shivangi" - his girlfriend (female)
- "Unknown" - unrecognized voice (could be media, another person, or background noise)

IMPORTANT: I will also provide a pre-flag based on audio analysis indicating whether this is likely media/playback or a real conversation.

Classify this conversation and return JSON with:
1. "source_type": One of "live_conversation", "self_talk", "media_or_unknown"
   - RESPECT the pre-flag: if it's "media_or_unknown", you need strong evidence to override
   - "self_talk" = only Shreyansh speaking (monologue)
   - "media_or_unknown" = movie/TV/video playing, or unclear source

2. "participants": Array of speakers present (e.g., ["shreyansh", "shivangi"])

3. "is_shivangi_conversation": true ONLY if there's real back-and-forth between Shreyansh and Shivangi

4. "quality": For live_conversation only - one of "good", "neutral", "tense", "not_applicable"
   - Based on tone, engagement, mutual exchange
   - Use "not_applicable" for self-talk or media

5. "summary": 1-2 sentence plain-language summary of what was discussed

6. "confidence_note": Optional note if you're uncertain about any classification

Pre-flag information: {preflag_info}
Speaker confidence scores: {speaker_info}

TRANSCRIPT:
{transcript}

Return ONLY valid JSON matching this schema:
{schema}
"""


@dataclass
class ClassificationResult:
    """Result of LLM classification."""
    source_type: str
    participants: List[str]
    is_shivangi_conversation: bool
    quality: str
    summary: str
    confidence_note: str = ""
    raw_response: str = ""
    processing_time_ms: float = 0.0
    error: Optional[str] = None


class LLMClassifier:
    """
    Stage 6: Semantic classification using Ollama.
    Sends conversation transcripts to local LLM for classification.
    """

    def __init__(self, config: Config):
        self.config = config
        self.model = config.llm.model
        self.host = config.llm.ollama_host
        self.timeout = config.llm.timeout_seconds
        self.max_retries = config.llm.max_retries
        self.temperature = config.llm.temperature
        self.max_tokens = config.llm.max_tokens

        self.session = requests.Session()
        self.request_count = 0

        logger.info(f"LLMClassifier initialized: model={self.model}, host={self.host}")

    def _check_ollama_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            response = self.session.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

    def _build_prompt(
        self,
        conversation: ConversationUnit
    ) -> str:
        """Build the classification prompt."""
        # Build pre-flag info
        preflag_info = {
            "source_type": conversation.preflag_source_type,
            "unknown_ratio": conversation.preflag_unknown_ratio,
            "rapid_alternation": conversation.preflag_rapid_alternation
        }

        # Build speaker confidence info
        speaker_info = {}
        for seg in conversation.transcript_segments:
            if seg.speaker not in speaker_info:
                speaker_info[seg.speaker] = []
            speaker_info[seg.speaker].append(seg.speaker_confidence)

        # Average confidence per speaker
        for speaker in speaker_info:
            confidences = speaker_info[speaker]
            speaker_info[speaker] = sum(confidences) / len(confidences)

        prompt = CLASSIFICATION_PROMPT.format(
            preflag_info=json.dumps(preflag_info, indent=2),
            speaker_info=json.dumps(speaker_info, indent=2),
            transcript=conversation.full_transcript,
            schema=json.dumps(CLASSIFICATION_SCHEMA, indent=2)
        )

        return prompt

    def classify(
        self,
        conversation: ConversationUnit,
        retry_count: int = 0
    ) -> ClassificationResult:
        """
        Classify a conversation unit using the local LLM.

        Args:
            conversation: ConversationUnit to classify
            retry_count: Current retry attempt

        Returns:
            ClassificationResult with all fields populated
        """
        start_time = time.time()

        # Check Ollama availability
        if not self._check_ollama_available():
            logger.error("Ollama server not available")
            return self._fallback_classification(
                conversation,
                "Ollama server not available"
            )

        # Build prompt
        prompt = self._build_prompt(conversation)

        try:
            # API endpoint for chat completion
            url = f"{self.host}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            }

            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code}")
                return self._fallback_classification(
                    conversation,
                    f"API error: {response.status_code}"
                )

            # Parse response
            result = response.json()
            raw_content = result.get("message", {}).get("content", "")

            self.request_count += 1
            processing_time = (time.time() - start_time) * 1000

            # Try to parse JSON from response
            classification = self._parse_llm_response(raw_content)

            if classification.error:
                # Retry once on parse failure
                if retry_count < self.max_retries:
                    log_stage("LLM", f"Retrying classification (attempt {retry_count + 1})")
                    return self.classify(conversation, retry_count + 1)
                else:
                    return classification

            log_metric("LLM", "classification_time", processing_time, "ms")
            log_stage("LLM", f"#{conversation.conversation_id}: "
                      f"{classification.source_type}, quality={classification.quality}, "
                      f"shivangi_conv={classification.is_shivangi_conversation}")

            classification.processing_time_ms = processing_time
            classification.raw_response = raw_content

            return classification

        except requests.Timeout:
            logger.error("LLM request timed out")
            return self._fallback_classification(conversation, "Request timeout")

        except Exception as e:
            logger.error(f"LLM error: {e}")
            return self._fallback_classification(conversation, str(e))

    def _parse_llm_response(self, raw_content: str) -> ClassificationResult:
        """Parse JSON from LLM response."""
        # Try to extract JSON from response
        try:
            # Find JSON object in response
            start = raw_content.find("{")
            end = raw_content.rfind("}") + 1

            if start == -1 or end == 0:
                raise ValueError("No JSON found in response")

            json_str = raw_content[start:end]
            data = json.loads(json_str)

            return ClassificationResult(
                source_type=data.get("source_type", "live_conversation"),
                participants=data.get("participants", ["unknown"]),
                is_shivangi_conversation=data.get("is_shivangi_conversation", False),
                quality=data.get("quality", "not_applicable"),
                summary=data.get("summary", ""),
                confidence_note=data.get("confidence_note", "")
            )

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return ClassificationResult(
                source_type="live_conversation",
                participants=["unknown"],
                is_shivangi_conversation=False,
                quality="not_applicable",
                summary="",
                confidence_note="Failed to parse LLM response",
                error=str(e)
            )

    def _fallback_classification(
        self,
        conversation: ConversationUnit,
        reason: str
    ) -> ClassificationResult:
        """Create fallback classification when LLM fails."""
        # Use pre-flag info for basic classification
        source_type = conversation.preflag_source_type
        participants = list(conversation.participants)
        is_shivangi = "shreyansh" in participants and "shivangi" in participants

        return ClassificationResult(
            source_type=source_type,
            participants=participants,
            is_shivangi_conversation=is_shivangi,
            quality="not_applicable",
            summary="",
            confidence_note=f"LLM fallback: {reason}",
            error=reason
        )

    def classify_batch(
        self,
        conversations: List[ConversationUnit]
    ) -> List[ClassificationResult]:
        """Classify multiple conversations."""
        results = []
        for conv in conversations:
            result = self.classify(conv)
            results.append(result)
        return results


def check_ollama_model(model: str, host: str = "http://localhost:11434") -> bool:
    """Check if the specified model is available in Ollama."""
    try:
        response = requests.get(f"{host}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            for m in models:
                if m.get("name", "").startswith(model):
                    return True
    except:
        pass
    return False


def pull_ollama_model(model: str, host: str = "http://localhost:11434"):
    """Pull a model from Ollama registry."""
    logger.info(f"Pulling model: {model}")
    response = requests.post(
        f"{host}/api/pull",
        json={"name": model},
        stream=True
    )

    for line in response.iter_lines():
        if line:
            data = json.loads(line)
            status = data.get("status", "")
            if "completed" in data:
                logger.info(f"  {status}: {data.get('completed', '')}%")
            elif status == "success":
                logger.info(f"  ✓ Model pulled successfully")
            elif "error" in data:
                logger.error(f"  ✗ Pull failed: {data['error']}")
                return False

    return True


if __name__ == "__main__":
    import sys

    # Check if Ollama is available
    print("Checking Ollama server...")
    if check_ollama_model("llama3.2:3b"):
        print("✓ Ollama is running with llama3.2:3b")
    else:
        print("✗ Ollama not available or model not pulled")
        print("  Run: ollama pull llama3.2:3b")
