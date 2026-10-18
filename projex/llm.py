"""Thin LLM wrapper. PROJEX works fully WITHOUT an LLM (rule-based explanations); if a key is configured the
agents ask the LLM to write the explanations, but only from evidence that the code computed (no invented facts).

Env vars:  ANTHROPIC_API_KEY  or  GOOGLE_API_KEY (Gemini)   |  PROJEX_LLM_PROVIDER = anthropic | gemini | none
"""
from __future__ import annotations
import json
import os
import re
from typing import Optional

from . import config


class LLMClient:
    def __init__(self, provider: Optional[str] = None):
        self.provider = (provider or config.LLM_PROVIDER).lower()
        self._client = None
        self.error: Optional[str] = None
        if self.provider == "anthropic":
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key:
                self.error = "ANTHROPIC_API_KEY not set"
            else:
                try:
                    import anthropic
                    self._client = anthropic.Anthropic(api_key=key)
                except Exception as e:                       # package missing etc.
                    self.error = f"anthropic package unavailable: {e}"
        elif self.provider == "gemini":
            key = os.getenv("GOOGLE_API_KEY")
            if not key:
                self.error = "GOOGLE_API_KEY not set"
            else:
                try:
                    from google import genai
                    self._client = genai.Client(api_key=key)
                except Exception as e:
                    self.error = f"google-genai package unavailable: {e}"
        else:
            self.error = "LLM disabled"

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete(self, system: str, prompt: str, max_tokens: int = 700) -> Optional[str]:
        """Returns text, or None on any failure (callers then fall back to rule-based text)."""
        if not self.available:
            return None
        try:
            if self.provider == "anthropic":
                msg = self._client.messages.create(model=config.ANTHROPIC_MODEL, max_tokens=max_tokens, system=system,
                                                   messages=[{"role": "user", "content": prompt}])
                return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
            if self.provider == "gemini":
                resp = self._client.models.generate_content(model=config.GEMINI_MODEL, contents=f"{system}\n\n{prompt}")
                return (resp.text or "").strip()
        except Exception as e:
            self.error = str(e)
        return None

    def complete_json(self, system: str, prompt: str, max_tokens: int = 700) -> Optional[dict]:
        text = self.complete(system + "\nReply with a single JSON object and nothing else.", prompt, max_tokens)
        if not text:
            return None
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
        return None
