# Model setup

This guide covers the speech models used by the Voice AI server. The model checkpoints are not included in the repository and must be downloaded separately.

## Models and checkpoints

Speech generation uses two models in sequence:

1. [Tacotron 2](https://arxiv.org/pdf/1712.05884) converts text into a mel spectrogram, a time-frequency representation of audio.
2. [UnivNet](https://arxiv.org/abs/2106.07889) synthesizes audio from that mel spectrogram.

The AC voice Tacotron 2 and UnivNet checkpoints are available in this [Google Drive folder](https://drive.google.com/drive/folders/1Mp3I33caVRm7YkGYd5z3TXNdgIUF10U-). Place them at these paths from the project root:

```text
models/voice/checkpoint_Tacotron2_1000.pt
models/voice/univ_c32_AC_2141.pt
```

The environment configuration expects those exact paths:

```dotenv
TACOTRON2_CHECKPOINT=models/voice/checkpoint_Tacotron2_1000.pt
UNIVNET_CHECKPOINT=models/voice/univ_c32_AC_2141.pt
```

Details on training are in the forked [NVIDIA Tacotron 2 repository](https://github.com/acharabin/DeepLearningExamples). The Ubuntu installation guide covers fetching the Tacotron 2 source, installing inference dependencies, and running the server.

## Text model provider

The browser's **Talk to** selector offers **Andrew** (hosted Qwen, selected by default) and **OpenAI**. It remembers your choice through sign-in and page reloads. API clients can pass `provider: "openai"` / `provider: "qwen"` with each request. Switching requires no restart. `TEXT_MODEL_PROVIDER` sets the fallback for `/api/chat` requests that omit a provider; the browser always sends its selection. MCP `generate_reply` defaults to OpenAI when its provider is omitted.

OpenAI uses `AGENT_MODEL` and `OPENAI_API_KEY`. Qwen calls an OpenAI-compatible hosted Chat Completions endpoint using its own URL, key, and served model name. The droplet does not load Qwen weights or need Transformers/PEFT. Speech synthesis still uses local Tacotron2 and UnivNet. OpenAI moderation runs only for the OpenAI provider.

### Runpod Serverless setup and access

1. Deploy an OpenAI-compatible vLLM Serverless worker with your trained model. For a straightforward deployment, merge the LoRA adapter from `models/text` into its original `Qwen/Qwen3-8B` base model on a machine with sufficient memory and upload the complete merged model to a private Hugging Face repository. Set the worker's `MODEL_NAME` to that repository and provide a read-only `HF_TOKEN` as a worker secret. Alternatively, configure vLLM LoRA serving and use its exposed adapter name; deploying the base Qwen model alone does not include your persona training.
2. Copy your Serverless endpoint ID. No dedicated public IP or inbound connection to the droplet is needed. The vLLM worker provides this base URL: `https://api.runpod.ai/v2/<ENDPOINT_ID>/openai/v1`. Do not use its `/run` or `/runsync` job API URL with this app.
3. In Runpod **Credentials ? API Keys**, create a dedicated **Restricted** API key with permission to invoke only this endpoint. This is a Runpod-issued key, not a secret invented locally. Keep unrelated account permissions disabled.
4. Configure the droplet's `.env`:

```dotenv
TEXT_MODEL_PROVIDER=openai
QWEN_BASE_URL=https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/openai/v1
QWEN_API_KEY=your-runpod-issued-key
QWEN_MODEL=persona
QWEN_MAX_NEW_TOKENS=200
QWEN_TIMEOUT_SECONDS=300
```

`QWEN_MODEL` defaults to `persona` when omitted or blank. Override it if your endpoint uses a different served model or LoRA adapter name. This is not the endpoint ID. It can be checked with the endpoint's authenticated `/models` API. The client requests non-thinking responses using vLLM's `chat_template_kwargs`.

Restart once after configuring credentials or deploying code. Models/clients are initialized lazily and cached; subsequent provider switches require no restart. A first request after the worker scales to zero can be slow. Automatic client retries are disabled to avoid repeating inference after a timeout. Set the minimum worker count to zero for scale-to-zero and cap maximum workers to control concurrency/cost; keeping a worker warm trades idle charges for lower latency.

The browser and MCP client never receive the Runpod key. They authenticate to this application; only the backend calls Runpod over HTTPS using Bearer authentication. Keep the key in the server `.env`, protect that file, and rotate/revoke the key in Runpod if needed. A private model repository's `HF_TOKEN` belongs on the Runpod worker, not in browser code.

See the [Runpod vLLM worker setup](https://github.com/runpod-workers/worker-vllm) and [Runpod credential permissions](https://docs.runpod.io/get-started/credentials).

### Andrew's factual context

The project-root `andrew-context.md` is included as reference context only in Qwen's system prompt. Qwen answers as Andrew's AI clone using these facts and its trained style, without assuming the person chatting is Andrew. OpenAI keeps its existing assistant instructions and does not receive this profile. This adds prompt context, not retraining or changes to Runpod's model weights. Direct Runpod tests will need the same system context to compare outputs.

Deploy `andrew-context.md` alongside `conversation.py` on the droplet. Qwen reads it when first initialized and caches its prompt, so restart `voice-ai` after editing it; **New chat** gives a clean comparison. If the file is missing or empty, existing behavior is preserved. The context stays outside the web assets, but its contents are sent to the Qwen inference endpoint and can be used in answers.

Useful optional additions: core values, a few personal stories, current projects and goals with an "as of" date, preferred answers to common personal questions, and explicit topics the clone should keep private. Unknown facts should stay unknown rather than being filled in by the model.

### Test through MCP

Qwen uses `temperature=0`, `max_tokens=200` by default, and `enable_thinking=false`, with no generic assistant system prompt. Its first turn includes the visible greeting as an assistant message, matching the Runpod test. Subsequent turns retain that greeting and the conversation history without adding it again. Set `QWEN_MAX_NEW_TOKENS=200` in an existing `.env` to match the test limit. Andrew's displayed reply is not subject to the OpenAI assistant's 99-character shortening; voice synthesis still has a 1200-character input limit. OpenAI retains the assistant instructions and moderation. Browser requests include conversation history: use **New chat** when comparing with a single-turn Runpod test, and match the served model, messages, thinking setting, and generation parameters. Greedy decoding reduces sampling variation but does not guarantee identical output across different serving configurations.

Call `generate_reply` with:

```json
{"message":"Introduce yourself in one sentence.","provider":"qwen"}
```

Each MCP reply is independent; pass its returned text to `text_to_audio_player` for speech. `/api/chat` accepts the optional `provider` along with `message` and `conversation_id`; browser histories remain separate for each provider. Missing hosted credentials do not prevent the other provider or speech tools from starting. Install the app with `uv sync` and start with `uv run python server.py`; no local Qwen dependency extra is required.
