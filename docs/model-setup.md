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
QWEN_MAX_NEW_TOKENS=256
QWEN_TIMEOUT_SECONDS=300
```

`QWEN_MODEL` defaults to `persona` when omitted or blank. Override it if your endpoint uses a different served model or LoRA adapter name. This is not the endpoint ID. It can be checked with the endpoint's authenticated `/models` API. The client requests non-thinking responses using vLLM's `chat_template_kwargs`.

Restart once after configuring credentials or deploying code. Models/clients are initialized lazily and cached; subsequent provider switches require no restart. A first request after the worker scales to zero can be slow. Automatic client retries are disabled to avoid repeating inference after a timeout. Set the minimum worker count to zero for scale-to-zero and cap maximum workers to control concurrency/cost; keeping a worker warm trades idle charges for lower latency.

The browser and MCP client never receive the Runpod key. They authenticate to this application; only the backend calls Runpod over HTTPS using Bearer authentication. Keep the key in the server `.env`, protect that file, and rotate/revoke the key in Runpod if needed. A private model repository's `HF_TOKEN` belongs on the Runpod worker, not in browser code.

See the [Runpod vLLM worker setup](https://github.com/runpod-workers/worker-vllm) and [Runpod credential permissions](https://docs.runpod.io/get-started/credentials).

### Test through MCP

Call `generate_reply` with:

```json
{"message":"Introduce yourself in one sentence.","provider":"qwen"}
```

Each MCP reply is independent; pass its returned text to `text_to_audio_player` for speech. `/api/chat` accepts the optional `provider` along with `message` and `conversation_id`; browser histories remain separate for each provider. Missing hosted credentials do not prevent the other provider or speech tools from starting. Install the app with `uv sync` and start with `uv run python server.py`; no local Qwen dependency extra is required.
