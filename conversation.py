"""OpenAI-backed conversational voice agent, following the marathon assistant pattern."""

from __future__ import annotations

import json
import os
from pathlib import Path

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_openai.middleware import OpenAIModerationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

ROOT = Path(__file__).resolve().parent
INSTRUCTIONS_FILE = ROOT / "config" / "voice_agent_instructions.md"

SPEECH_REWRITE_PROMPT = """Rewrite the supplied assistant text so it sounds natural when spoken aloud.
Keep the meaning, facts, names, numbers, and intent unchanged. Use clear conversational
phrasing, natural sentence breaks, and punctuation that helps spoken delivery. Do not add
stage directions, markup, or information. Return only a JSON array of strings with one
rewritten item for each input item, in the same order. If an item should not change, repeat it."""


async def improve_spoken_text(raw_parts: list[str], model) -> list[str]:
    """Improve text segments for speech while keeping a list-shaped tool response."""
    if not raw_parts:
        return []
    prompt = json.dumps(raw_parts, ensure_ascii=False)
    try:
        result = await model.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
        processed = json.loads(str(result["messages"][-1].content))
        if (isinstance(processed, list) and len(processed) == len(raw_parts)
                and all(isinstance(item, str) and item.strip() for item in processed)):
            return [item.strip() for item in processed]
    except Exception:
        pass
    # Speech enhancement must never prevent the original response from being used.
    return raw_parts


def create_voice_agent():
    """Create the in-memory conversational agent for the browser app."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing; add it to the project .env file")

    model = init_chat_model(os.getenv("AGENT_MODEL", "openai:gpt-4.1-mini"))
    system_prompt = INSTRUCTIONS_FILE.read_text(encoding="utf-8")
    middleware = [
        OpenAIModerationMiddleware(
            model="omni-moderation-latest",
            check_input=True,
            check_output=True,
            exit_behavior="end",
        )
    ]
    return create_agent(
        model=model,
        name="andrew_voice_agent",
        tools=[],
        system_prompt=system_prompt,
        checkpointer=InMemorySaver(),
        middleware=middleware,
    )


def create_speech_rewriter():
    """Create a moderated LLM agent to polish assistant text before it is spoken."""
    middleware = [
        OpenAIModerationMiddleware(
            model="omni-moderation-latest",
            check_input=True,
            check_output=True,
            exit_behavior="end",
        )
    ]
    return create_agent(
        model=init_chat_model(os.getenv("AGENT_MODEL", "openai:gpt-4.1-mini")),
        name="spoken_text_rewriter",
        tools=[],
        system_prompt=SPEECH_REWRITE_PROMPT,
        middleware=middleware,
    )
