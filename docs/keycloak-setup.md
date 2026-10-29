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

## Public deployment on the provided IP

The repository also includes a production-mode Keycloak + PostgreSQL stack and a Caddy reverse-proxy config. This uses a Let's Encrypt IP-address certificate from the short-lived profile (about six days), which Caddy renews automatically. It requires ports 80 and 443 to reach this machine and a recent Caddy version with ACME profile support. See the [Let's Encrypt IP certificate notes](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability) and [Caddy TLS issuer settings](https://caddyserver.com/docs/caddyfile/directives/tls).

Before switching, copy the updated `server.py`, `conversation.py`, `auth.py`, `config/voice_agent_instructions.md`, `keycloak/voice-ai-realm.json`, `docker-compose.public.yml`, and `Caddyfile.public` to the server. Keep the existing dev Keycloak container running until the public setup is verified. The public stack uses a new PostgreSQL database and imports the realm afresh, so create a user again in that new realm (or export/import existing users separately).

On the Ubuntu server, create `.env.public` from `.env.public.example`, set unique passwords, and lock down the file:

```bash
cp .env.public.example .env.public
chmod 600 .env.public
```

Start the production Keycloak and database:

```bash
docker compose --env-file .env.public -f docker-compose.public.yml up -d
docker compose --env-file .env.public -f docker-compose.public.yml logs --tail 100 keycloak
```

Install Caddy using its [official Ubuntu package instructions](https://caddyserver.com/docs/install), copy `Caddyfile.public` to `/etc/caddy/Caddyfile`, then validate and reload it:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

Allow inbound TCP ports 80 and 443 in the cloud firewall and Ubuntu firewall. Configure the Voice AI server's `.env` like this, then restart it. The app binds only to localhost; Caddy is the public entry point. Set `OAUTH_FORCE_LOOPBACK=true` because the local reverse proxy makes the app see proxied requests as loopback:

Below confix assumes a public IPv4 address of `138.197.152.248` as used by the respective application. 

```env
MCP_HOST=127.0.0.1
MCP_PORT=10001
MCP_SERVER_URL=https://138.197.152.248/mcp
MCP_ALLOWED_HOSTS=138.197.152.248
MCP_ALLOWED_ORIGINS=https://138.197.152.248
OAUTH_ISSUER=https://138.197.152.248/auth/realms/voice-ai
OAUTH_CLIENT_ID=voice-ai-web
OAUTH_AUDIENCE=voice-ai-api
OAUTH_SCOPE=voice:generate
OAUTH_REDIRECT_URI=https://138.197.152.248/
OAUTH_JWT_ALGORITHMS=RS256
OAUTH_FORCE_LOOPBACK=true
```

The public Keycloak client is imported with the HTTPS callback and origin above, the `basic` default scope, PKCE S256, and the custom `voice-ai-api` audience mapper. Create a regular user in `https://138.197.152.248/auth/admin/` under the `voice-ai` realm. The existing development realm and its H2 database remain separate; do not expose the dev port 8080 publicly.

### Keep the public deployment running

The repository includes `deploy/voice-ai.service` for running the Voice AI app under systemd and `scripts/restart-deployment.sh` for a cron health check. The service file assumes the project is at `/root/voice-mcp-server` and `uv` is at `/root/.local/bin/uv`; adjust those paths if your server differs. Stop any manually running `uv run python server.py` process with Ctrl+C before enabling the service.

After copying both files to the server, install and start the app service:

```bash
sudo cp deploy/voice-ai.service /etc/systemd/system/voice-ai.service
sudo systemctl daemon-reload
sudo systemctl enable --now voice-ai.service
sudo systemctl status voice-ai.service --no-pager
```

Run the health-check script every five minutes from root's crontab (`sudo crontab -e`):

```cron
*/5 * * * * /bin/bash /root/voice-mcp-server/scripts/restart-deployment.sh
```

The script appends its activity to `logs/log.txt`, ensures the public Keycloak/PostgreSQL Compose stack is started, starts Caddy if its service is down, and restarts Keycloak or the app only when their health checks fail. The app is checked through `http://127.0.0.1:10001/auth/config`; Keycloak is checked through its local discovery endpoint. systemd and Docker restart policies also recover processes that exit unexpectedly. Inspect the log with `tail -n 100 /root/voice-mcp-server/logs/log.txt`.