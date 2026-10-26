"""OIDC access-token verification for the MCP and voice HTTP endpoints."""

import asyncio
import json
import logging
import secrets
import threading
import time
import urllib.request
from typing import Any

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)


class OIDCTokenVerifier:
    """Verify signed OIDC access tokens against issuer, audience, expiry and scope."""

    def __init__(self, issuer: str, audience: str, required_scope: str, resource_url: str,
                 algorithms: list[str] | None = None, local_access_token: str | None = None):
        self.issuer = issuer
        self.audience = audience
        self.required_scope = required_scope
        self.resource_url = resource_url
        self.algorithms = algorithms or ["RS256"]
        self.local_access_token = local_access_token
        self._jwks: PyJWKClient | None = None
        self._jwks_lock = threading.Lock()

    def _get_jwks(self) -> PyJWKClient:
        if self._jwks is not None:
            return self._jwks
        with self._jwks_lock:
            if self._jwks is not None:
                return self._jwks
            discovery_url = f"{self.issuer.rstrip('/')}/.well-known/openid-configuration"
            request = urllib.request.Request(discovery_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=8) as response:
                metadata = json.load(response)
            if metadata.get("issuer") != self.issuer:
                raise ValueError("OIDC discovery issuer does not match OAUTH_ISSUER")
            jwks_uri = metadata.get("jwks_uri")
            if not jwks_uri:
                raise ValueError("OIDC discovery document has no jwks_uri")
            self._jwks = PyJWKClient(jwks_uri, cache_keys=True)
            return self._jwks

    def _verify_sync(self, token: str) -> AccessToken | None:
        try:
            signing_key = self._get_jwks().get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
            raw_scopes = claims.get("scope", claims.get("scp", []))
            scopes = raw_scopes.split() if isinstance(raw_scopes, str) else list(raw_scopes)
            if self.required_scope not in scopes:
                return None
            return AccessToken(
                token=token,
                client_id=str(claims.get("azp", claims.get("client_id", "oidc-client"))),
                scopes=scopes,
                expires_at=int(claims["exp"]),
                resource=self.resource_url,
                subject=str(claims["sub"]),
                claims=claims,
            )
        except (jwt.PyJWTError, OSError, ValueError, KeyError, TypeError) as exc:
            logger.info("Rejected OAuth access token: %s", type(exc).__name__)
            return None

    async def verify_token(self, token: str) -> AccessToken | None:
        if self.local_access_token and secrets.compare_digest(token, self.local_access_token):
            return AccessToken(
                token=token,
                client_id="loopback-client",
                scopes=[self.required_scope],
                expires_at=int(time.time()) + 3600,
                resource=self.resource_url,
                subject="loopback-user",
                claims={"sub": "loopback-user"},
            )
        return await asyncio.to_thread(self._verify_sync, token)
