# Voice AI MCP Server

This project provides a browser app for chatting with a voice assistant and a separate Model Context Protocol (MCP) endpoint for text-to-speech tools. Both use the same speech-generation backend; conversational chat is provided by the browser app.

## Browser app

**Public deployment:** [https://138.197.152.248/](https://138.197.152.248/)

Open this URL in a browser to use the chat interface. Sign in through Keycloak, enter a message, and the assistant returns a concise text reply and synthesized audio. If self-registration is enabled in the `voice-ai` Keycloak realm, new users can choose **Register** on the sign-in page.

The browser app uses OAuth Authorization Code + PKCE. Its backend routes are `/api/chat` for assistant replies and `/api/voice` for speech generation. The OpenAI API key stays on the server. Remote requests require an access token from the configured issuer with the expected audience and `voice:generate` scope.

For local development, keep `MCP_HOST=127.0.0.1`, run `uv sync` and `uv run python server.py`, then open [http://127.0.0.1:10000/](http://127.0.0.1:10000/). Assistant replies require `OPENAI_API_KEY` in the server's `.env` file.

## MCP endpoint

**Public deployment:** [https://138.197.152.248/mcp](https://138.197.152.248/mcp)

This is the MCP Streamable HTTP endpoint for MCP-compatible clients. It is a protocol endpoint, not a web page; opening it directly in a browser is not expected to show the chat app. Configure the MCP client to connect to this URL and complete OAuth sign-in when prompted. Remote MCP requests require the `voice:generate` scope and the configured API audience. The server exposes `text_to_audio` for normalized float audio samples and `text_to_audio_player` for playable WAV audio.

The browser app and MCP endpoint share the same running server process and model, so audio-generation requests through either interface use the server's inference resources.

For local development, the MCP endpoint is [http://127.0.0.1:10000/mcp](http://127.0.0.1:10000/mcp).

## Deployment and configuration

The public IP deployment uses HTTPS through Caddy. Caddy accepts public traffic on ports 80 and 443 and reverse proxies to the app on `127.0.0.1:10001`; Keycloak is served under `/auth` and listens privately on `127.0.0.1:8081`. Keep the app bound to loopback behind this proxy and set `MCP_SERVER_URL=https://138.197.152.248/mcp`, `MCP_ALLOWED_HOSTS=138.197.152.248`, and `MCP_ALLOWED_ORIGINS=https://138.197.152.248`. Set `OAUTH_FORCE_LOOPBACK=true` so OAuth remains enforced when the proxy connects to the app locally.

For deployment steps, production Keycloak/PostgreSQL setup, and OAuth client settings, see the [Keycloak OAuth setup](docs/keycloak-setup.md). For Ubuntu installation and starting the server, see the [Ubuntu startup guide](docs/ubuntu-startup-guide.md); model downloads, checkpoint paths, and inference details are in the [model setup guide](docs/model-setup.md).

Conversation history is stored in process memory and resets when the server restarts. OpenAI moderation checks input and output; the OpenAI API key remains server-side and must never be added to browser code.
