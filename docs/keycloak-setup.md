# Keycloak OAuth setup

This repository includes a Keycloak realm import for the Voice AI app. It creates a public browser client using Authorization Code, requires PKCE with S256, and adds the `voice:generate` scope and `voice-ai-api` access-token audience. It does not create a client secret.

## Start Keycloak for local setup

Copy `.env.keycloak.example` to `.env.keycloak`, replace the bootstrap admin password with a long random value, then start Keycloak from the project root:

```powershell
Copy-Item .env.keycloak.example .env.keycloak
docker compose --env-file .env.keycloak -f docker-compose.keycloak.yml up -d
```

Keycloak is available at `http://localhost:8080`. Sign in to the admin console with the username and password in `.env.keycloak`; select the `voice-ai` realm. Create a user under **Users**, set a password under **Credentials**, and turn **Temporary** off if you want a non-expiring local password.

The included container uses Keycloak development mode and binds only to loopback. Keep it local; it is not a production deployment.

## Connect the app

Set the following in the app's `.env` (keep `.env` private):

```env
OAUTH_ISSUER=http://localhost:8080/realms/voice-ai
OAUTH_CLIENT_ID=voice-ai-web
OAUTH_AUDIENCE=voice-ai-api
OAUTH_SCOPE=voice:generate
OAUTH_REDIRECT_URI=http://localhost:10000/
OAUTH_JWT_ALGORITHMS=RS256
```

Keep `MCP_HOST=127.0.0.1` and `MCP_SERVER_URL=http://127.0.0.1:10000/mcp` for local use. Restart the app after editing `.env`. The browser UI skips sign-in for loopback requests by design, so OAuth is enforced when the app is accessed remotely.

For a browser-based OAuth test without publishing Keycloak, tunnel both services to local ports. Set `OAUTH_FORCE_LOOPBACK=true`, `OAUTH_REDIRECT_URI=http://localhost:10000/`, and add `localhost:10000` to `MCP_ALLOWED_HOSTS` and `http://localhost:10000` to `MCP_ALLOWED_ORIGINS`. Keep `http://localhost:10000/` in the Keycloak client's valid redirect URIs and `http://localhost:10000` in its web origins. Restart the app, then create both SSH forwards from your computer:

```powershell
ssh -N -L 10000:127.0.0.1:10001 -L 8080:127.0.0.1:8080 root@138.197.152.248
```

Open `http://localhost:10000/`. The loopback override makes the app require and validate OAuth tokens for this tunnel-based test. Turn `OAUTH_FORCE_LOOPBACK` back off for ordinary loopback use.

## Remote deployment

The bundled Keycloak container is not configured for public deployment. For remote use, provide a public HTTPS URL for Keycloak behind a TLS reverse proxy, use Keycloak production mode with a persistent production database, and set the realm's `VOICE_APP_URL` and `VOICE_APP_ORIGIN` to the app's exact HTTPS callback and origin before the realm is first imported. The OIDC issuer must be the public URL and must be reachable both by browsers and by the Voice AI server. Use those public issuer and app URLs in the app's `.env`; set `MCP_SERVER_URL`, `MCP_ALLOWED_HOSTS`, and `MCP_ALLOWED_ORIGINS` to the app's public HTTPS endpoint, and set `MCP_HOST=0.0.0.0` only after HTTPS and OAuth are working.

For production, set a unique Keycloak bootstrap admin password, restrict the admin console, back up the database, and do not expose Keycloak's development server directly. Realm import runs only when the realm does not already exist; update callback URLs and client settings in the Keycloak admin console for an existing realm.
