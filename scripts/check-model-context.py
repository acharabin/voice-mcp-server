"""Check factual grounding and the outgoing Qwen request without live credentials."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from langchain_openai import ChatOpenAI
import conversation


class ContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.context_file = Path(self.directory.name) / "andrew-context.md"
        self.context_file.write_text("Favourite colour: Blue", encoding="utf-8-sig")
        context_patch = patch.object(conversation, "CONTEXT_FILE", self.context_file)
        context_patch.start()
        self.addCleanup(context_patch.stop)

    def test_only_qwen_receives_personal_context(self):
        qwen = conversation.build_system_prompt("qwen")
        openai = conversation.build_system_prompt("openai")
        self.assertIn("Favourite colour: Blue", qwen)
        self.assertIn("not the user chatting", qwen)
        self.assertNotIn("Favourite colour: Blue", openai)
        self.assertNotIn("<andrew_context>", openai)
        self.assertIn("first person", qwen)
        self.assertNotIn("Do not claim to be human", qwen)
        self.assertIn("Do not claim to be human", openai)

    def test_missing_and_empty_context_preserve_existing_behavior(self):
        for missing in (False, True):
            if missing:
                self.context_file.unlink()
            else:
                self.context_file.write_text("  \n")
            self.assertIsNone(conversation.build_system_prompt("qwen"))
            self.assertIn("warm, thoughtful", conversation.build_system_prompt("openai"))

    def test_updated_file_is_used_when_building_a_new_prompt(self):
        conversation.build_system_prompt("qwen")
        self.context_file.write_text("Favourite colour: Green", encoding="utf-8")
        self.assertIn("Favourite colour: Green", conversation.build_system_prompt("qwen"))

    async def test_context_is_sent_to_qwen_with_greeting_and_user_message(self):
        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={
                "id": "test", "object": "chat.completion", "created": 1,
                "model": "persona", "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Blue."}}],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            def model(**kwargs):
                return ChatOpenAI(**kwargs, http_async_client=client)

            with patch.dict(os.environ, {
                "QWEN_BASE_URL": "https://example.test/v1", "QWEN_API_KEY": "test",
                "LANGSMITH_TRACING": "false",
            }, clear=True), patch.object(conversation, "ChatOpenAI", side_effect=model):
                agent = conversation.create_voice_agent("qwen")
                reply = await conversation.invoke_voice_agent(agent, "Your favourite colour?", "qwen", "context-test")
                self.assertEqual(reply["messages"][-1].content, "Blue.")
        self.assertEqual(len(requests), 1)
        body = requests[0]
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "assistant", "user"])
        self.assertIn("Favourite colour: Blue", body["messages"][0]["content"])
        self.assertEqual(body["messages"][1]["content"], conversation.INITIAL_GREETING)
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["model"], "persona")


if __name__ == "__main__":
    unittest.main()
