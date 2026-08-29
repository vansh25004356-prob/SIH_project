"""LLM-powered helpers using Emergent Universal Key.

- explain_risk(): concise, plain-language "Why is this zone at risk?" narrative
  built strictly from the numeric factors we pass in — the LLM is instructed
  NOT to invent facts.
- translate_alert(): translate a short alert template into supported NER
  languages (English, Assamese, Khasi, Mizo, Nepali, Bodo).

Both functions degrade gracefully — if the key is missing or the LLM call
fails, we return a rule-based fallback so the platform keeps working.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

log = logging.getLogger("llm_service")

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    _CHAT_AVAILABLE = True
except Exception:  # pragma: no cover
    LlmChat = None  # type: ignore
    UserMessage = None  # type: ignore
    _CHAT_AVAILABLE = False


SUPPORTED_LANGUAGES = {
    "en": "English",
    "as": "Assamese",
    "kha": "Khasi",
    "lus": "Mizo",
    "ne": "Nepali",
    "brx": "Bodo",
}


def _key() -> str:
    return os.environ.get("EMERGENT_LLM_KEY", "").strip()


def _rule_based_explanation(severity: str, factors: List[Dict[str, Any]]) -> str:
    if not factors:
        return f"{severity} risk. No individual driver exceeded its alert threshold; the combined pattern of recent rainfall and terrain drove the score."
    top = ", ".join(f'{f["label"]} = {f["value"]} {f["unit"]}' for f in factors[:3])
    return f"{severity} risk driven by: {top}."


async def explain_risk(severity: str, factors: List[Dict[str, Any]], zone_name: str) -> str:
    fallback = _rule_based_explanation(severity, factors)
    if not (_CHAT_AVAILABLE and _key()):
        return fallback
    try:
        chat = LlmChat(
            api_key=_key(),
            session_id=f"risk-explain-{zone_name}",
            system_message=(
                "You are a disaster-management analyst. Given a risk severity and a JSON list of "
                "numeric drivers (rainfall totals, slope, elevation, sensor status), write a single "
                "2-3 sentence plain-language explanation. Do NOT invent facts, weather events, or numbers "
                "beyond those provided. Speak in operational tone."
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        msg = UserMessage(text=(
            f"Zone: {zone_name}\nSeverity: {severity}\nFactors: {factors}"
        ))
        reply = await chat.send_message(msg)
        text = (reply or "").strip()
        return text or fallback
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM explain_risk failed: %s", exc)
        return fallback


async def translate_alert(text_en: str, langs: List[str] | None = None) -> Dict[str, str]:
    langs = langs or list(SUPPORTED_LANGUAGES.keys())
    out: Dict[str, str] = {"en": text_en}
    if not (_CHAT_AVAILABLE and _key()):
        for l in langs:
            out.setdefault(l, text_en)
        return out
    try:
        chat = LlmChat(
            api_key=_key(),
            session_id=f"alert-tx-{hash(text_en) & 0xFFFF}",
            system_message=(
                "You translate short emergency alerts. Output valid JSON only with the requested "
                "language codes as keys. Keep the meaning exact and the tone urgent but calm. "
                "If a language script is unavailable, use romanized transliteration."
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        target = [l for l in langs if l != "en"]
        msg = UserMessage(text=(
            f"Alert (English): {text_en}\n"
            f"Translate into these languages and return JSON with keys {target}: "
            f"{ {l: SUPPORTED_LANGUAGES[l] for l in target} }"
        ))
        reply = await chat.send_message(msg)
        import json, re
        m = re.search(r"\{.*\}", reply or "", re.S)
        if m:
            try:
                data = json.loads(m.group(0))
                for l in target:
                    if l in data and isinstance(data[l], str):
                        out[l] = data[l]
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM translate_alert failed: %s", exc)
    for l in langs:
        out.setdefault(l, text_en)
    return out
