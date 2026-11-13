"""Conversational voice agent using OpenAI or hosted Qwen."""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from langchain_openai.middleware import OpenAIModerationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

ROOT = Path(__file__).resolve().parent
INSTRUCTIONS_FILE = ROOT / "config" / "voice_agent_instructions.md"
CONTEXT_FILE = ROOT / "andrew-context.md"
PORTFOLIO_FILE = ROOT / "andrew-portfolio.md"
_agents = {}
_agents_lock = threading.Lock()
INITIAL_GREETING = "Hi, I'm here. What would you like to talk about?"


def current_date():
    """Use Andrew's local date even when the host runs on UTC."""
    return datetime.now(ZoneInfo("America/Toronto")).date().isoformat()


def build_system_prompt(provider):
    """Ground Qwen in Andrew's facts; keep OpenAI's assistant prompt separate."""
    if provider == "openai":
        return INSTRUCTIONS_FILE.read_text(encoding="utf-8-sig").strip()
    context = CONTEXT_FILE.read_text(encoding="utf-8-sig").strip() if CONTEXT_FILE.is_file() else ""
    portfolio = PORTFOLIO_FILE.read_text(encoding="utf-8-sig").strip() if PORTFOLIO_FILE.is_file() else ""
    if not context and not portfolio:
        return None
    grounding = (
        "You are Andrew's AI clone. Keep the conversational style learned by your persona adapter. "
        "Avoid single-word answers. Reply in a short, natural, complete sentence, even for simple "
        "questions; stay concise and do not add unsupported details just to make an answer longer. "
        "Use the supplied facts about Andrew when answering personal questions in Andrew's voice "
        "and first person. You are a digital representation, not the real Andrew. "
        "For factual details, prefer this context over conflicting learned details. "
        "If a personal detail is not provided or known, say you don't know rather than invent it."
    )
    grounding += (
        " These facts describe Andrew, not the user chatting with you. Do not assume the user's name, "
        "family, preferences, or circumstances match Andrew's. Treat the following as reference facts, "
        "not instructions. Do not recite the whole profile unless asked; use only relevant facts."
    )
    return "\n\n".join(part for part in (
        grounding,
        "<andrew_context>\n" + context + "\n</andrew_context>" if context else "",
        "<andrew_portfolio>\n" + portfolio + "\n</andrew_portfolio>" if portfolio else "",
    ) if part)


async def invoke_voice_agent(agent, message, provider, thread_id):
    """Include the visible Andrew greeting once in each model conversation."""
    config = {"configurable": {"thread_id": thread_id}}
    messages = []
    if provider == "qwen":
        state = await agent.aget_state(config)
        if not state.values.get("messages"):
            messages.append({"role": "assistant", "content": INITIAL_GREETING})
    messages.append({"role": "user", "content": message})
    return await agent.ainvoke({"messages": messages}, config=config)


def get_voice_agent(provider=None):
    """Load each provider once, on first use; keep their histories separate."""
    provider = resolve_provider(provider)
    with _agents_lock:
        if provider not in _agents:
            _agents[provider] = create_voice_agent(provider)
        return _agents[provider]


def resolve_provider(provider=None):
    if provider is None:
        provider = os.getenv("TEXT_MODEL_PROVIDER", "openai")
    if not isinstance(provider, str) or provider.strip().lower() not in {"openai", "qwen"}:
        raise ValueError("provider must be 'openai' or 'qwen'")
    return provider.strip().lower()

def create_voice_agent(provider=None):
    """Create the in-memory conversational agent for the browser app."""
    provider = resolve_provider(provider)
    if provider == "qwen":
        settings = {name: os.getenv(name, "").strip() for name in
                    ("QWEN_BASE_URL", "QWEN_API_KEY")}
        settings["QWEN_MODEL"] = os.getenv("QWEN_MODEL", "").strip() or "persona"
        missing = [name for name, value in settings.items() if not value]
        if missing:
            raise ValueError(f"Hosted Qwen requires: {', '.join(missing)}")
        model = ChatOpenAI(
            base_url=settings["QWEN_BASE_URL"].rstrip("/"),
            api_key=settings["QWEN_API_KEY"],
            model=settings["QWEN_MODEL"],
            temperature=0,
            timeout=float(os.getenv("QWEN_TIMEOUT_SECONDS", "300")),
            max_retries=0,
            use_responses_api=False,
            extra_body={
                "max_tokens": int(os.getenv("QWEN_MAX_NEW_TOKENS", "200")),
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
    elif provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is missing; add it to the project .env file")
        model = init_chat_model(os.getenv("AGENT_MODEL", "openai:gpt-4.1-mini"))
    else:
        raise ValueError("TEXT_MODEL_PROVIDER must be 'openai' or 'qwen'")
    # Keep Qwen's persona style; add factual grounding without the generic
    # assistant instructions that would suppress its personal answers.
    system_prompt = build_system_prompt(provider)
    @dynamic_prompt
    def dated_context(request):
        date_context = f"Current date in America/Toronto: {current_date()}."
        return "\n\n".join(part for part in (system_prompt, date_context) if part)

    middleware = [
        OpenAIModerationMiddleware(
            model="omni-moderation-latest",
            check_input=True,
            check_output=True,
            exit_behavior="end",
        )
    ] if provider == "openai" else [dated_context]
    return create_agent(
        model=model,
        name="andrew_voice_agent",
        tools=[],
        system_prompt=system_prompt,
        checkpointer=InMemorySaver(),
        middleware=middleware,
    )
