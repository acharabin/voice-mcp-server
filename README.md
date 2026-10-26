

## Conversational voice app and authentication

The browser app lets an authenticated user chat with an OpenAI-backed assistant and hear each answer in Andrew's synthesized voice. It serves the public page at `/`, the conversation API at `/api/chat`, the audio endpoint at `/api/voice`, and the MCP Streamable HTTP endpoint at `/mcp`. Remote browser and MCP requests require OAuth; same-machine loopback requests remain exempt. OAuth uses authorization code with PKCE for the browser, and the server validates access-token signature, issuer, audience, expiry, and `voice:generate` scope.

The app follows the marathon assistant's model setup pattern: `AGENT_MODEL` selects the model (default `openai:gpt-4.1-mini`), LangGraph `InMemorySaver` stores per-user conversation history while the process runs, and OpenAI moderation checks inputs and outputs. History is memory-only and resets when the server restarts. The OpenAI API key remains server-side in `.env` and is never returned to the browser.

For local use, keep `MCP_HOST=127.0.0.1`. The browser app and voice API then use the loopback exception; `OPENAI_API_KEY` is still required for assistant replies. Start with `uv sync`, then `uv run python server.py`, and open `http://127.0.0.1:10000/`.

For remote deployment, configure `OAUTH_ISSUER`, `OAUTH_CLIENT_ID`, `OAUTH_AUDIENCE`, and `OAUTH_REDIRECT_URI`, and use HTTPS. Create a public SPA client and API/resource with `voice:generate`, allow authorization code + PKCE S256, register the exact callback and web origin, and configure RS256 access tokens whose audience matches `OAUTH_AUDIENCE`. Never put a client secret or the OpenAI API key in browser code. For Auth0, the authorization request also sends the `audience` parameter. Use `MCP_HOST=0.0.0.0`, the public HTTPS URL in `MCP_SERVER_URL`, and matching allowed host/origin settings. The server refuses non-loopback binding unless all OAuth settings are present.

For a local open-source Keycloak setup with a preconfigured public PKCE client, see the [Keycloak OAuth setup](docs/keycloak-setup.md).
## Ubuntu setup

See the [Ubuntu startup guide](docs/ubuntu-startup-guide.md) for installation, sparse checkout, model setup, and starting the MCP server and browser client.

