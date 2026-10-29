# Ubuntu startup guide

This guide starts the Tacotron2 voice service and its browser client on one Ubuntu machine. The conversational browser client is served by the same process as the MCP server; it calls the local chat and audio routes, so there is no separate frontend process.

The latest deployment instance uses **2 vCPUs and 4 GB of RAM**. Use this as the replication target; it describes the current instance, not a minimum sizing guarantee.

## 1. Install system tools

Use Ubuntu 22.04 or newer with Python 3.12, Git, and `curl`:

```bash
sudo apt update
sudo apt install -y git curl build-essential python3.12 python3.12-venv
```

Install `uv` for your user:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

If `uv` is not found, open a new shell or add `~/.local/bin` to `PATH`.

## 2. Get this project

Clone this repository and enter its root (the directory containing `server.py` and `pyproject.toml`):

```bash
git clone <VOICE_AI_MCP_SERVER_REPOSITORY_URL> voice-ai-mcp-server
cd voice-ai-mcp-server
```

Replace the placeholder URL with the URL of your project repository.

## 3. Get only the Tacotron2 source directory

The project imports the forked Tacotron2 code from `DeepLearningExamples/PyTorch/SpeechSynthesis/Tacotron2`. Fetch that directory at the commit used by this project, with sparse checkout:

```bash
git clone --filter=blob:none --no-checkout \
  https://github.com/acharabin/DeepLearningExamples.git DeepLearningExamples
cd DeepLearningExamples
git sparse-checkout init --no-cone
git sparse-checkout set /PyTorch/SpeechSynthesis/Tacotron2/
git fetch --depth 1 origin caf6bf7a501e6df2449aea1f6d78d5afba7f947a
git checkout FETCH_HEAD
cd ..
```

Create the import alias expected by the fork. Run this from the project root:

```bash
cd DeepLearningExamples/PyTorch/SpeechSynthesis/Tacotron2
rm -f __Tacotron2
ln -s . __Tacotron2
cd ../../../../
```

The resulting link should point to the Tacotron2 directory itself. Confirm it with:

```bash
readlink DeepLearningExamples/PyTorch/SpeechSynthesis/Tacotron2/__Tacotron2
```

It should print `.`. Do not use this command if `__Tacotron2` is a real directory containing data; it is intended to replace the small placeholder file in this fork.

## 4. Configure the environment

Download and place the Tacotron2 and UnivNet checkpoints as described in the [model setup guide](model-setup.md). Copy the environment template and review it:

```bash
cp .env.example .env
```

For a private local run, keep these settings (and set `AGENT_MODEL=openai:gpt-4.1-mini`; keep `OPENAI_API_KEY` in `.env`):

```dotenv
MCP_HOST=127.0.0.1
MCP_PORT=10000
MCP_SERVER_URL=http://127.0.0.1:10000/mcp
PYTHONPATH=src:DeepLearningExamples/PyTorch/SpeechSynthesis/Tacotron2
TACOTRON2_CHECKPOINT=models/checkpoint_Tacotron2_1000.pt
UNIVNET_CHECKPOINT=models/univ_c32_AC_2141.pt
```

Leave the OAuth values blank for loopback use. The server intentionally refuses to bind to a non-loopback address without OAuth settings. When configured, OAuth is required for remote clients, while requests from the same machine over loopback stay exempt. For remote access, configure OAuth and HTTPS before changing `MCP_HOST` to `0.0.0.0`; see the authentication section in the [README](../README.md).

## 5. Install Python dependencies

Create/sync the project environment, then install the Tacotron2 inference requirements into that environment:

```bash
uv sync
uv pip install --python .venv/bin/python \
  -r DeepLearningExamples/PyTorch/SpeechSynthesis/Tacotron2/requirements.txt
```

`uv sync` creates `.venv` from `uv.lock`; the second command installs the additional libraries listed by the fork's inference code. It may need internet access to install `dllogger` from GitHub. The project currently configures CPU inference (`args.cpu=True`), so a CUDA setup is not required.

## 6. Start the MCP server and browser client

From the project root:

```bash
uv run python server.py
```

The first startup can take a while while PyTorch and the model checkpoints load. Leave this terminal open. Open the browser UI on the same machine at:

```text
http://127.0.0.1:10000/
```

Enter a message, choose **Send**, and listen to the assistant response. The assistant uses the server-side `OPENAI_API_KEY`; the key is never sent to the browser. Local loopback mode does not ask for OAuth credentials. Conversation history is held in memory and resets when the server restarts.

The MCP Streamable HTTP endpoint is:

```text
http://127.0.0.1:10000/mcp
```

Configure an MCP client that supports Streamable HTTP to use that URL. Keep the server terminal running while using either the browser UI or an MCP client.

## 7. Stop and restart

Stop the server with `Ctrl+C`. Start it again using the command in section 6. If port `10000` is already in use, stop the other process or update `MCP_PORT`, `MCP_SERVER_URL`, and the allowed host/origin values together in `.env`.

## Common problems

- **Missing checkpoint:** verify both model files exist at the paths in `.env`; relative paths are resolved from the project root.
- **`No module named __Tacotron2`:** recreate the `__Tacotron2 -> .` symlink from section 3 and run the server from the project root.
- **`No module named ...` from inference:** install the fork's `requirements.txt` into `.venv` using section 5.
- **Permission denied binding the port:** choose a port above 1024, such as the default `10000`.
- **Cannot open the UI from another machine:** loopback binding is intentionally private. For remote access, configure OAuth and HTTPS rather than binding unauthenticated service to a public interface.
