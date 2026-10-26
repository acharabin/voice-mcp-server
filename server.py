import asyncio
import io
import ipaddress
import logging
import os
import secrets
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"


def load_project_env(path: Path) -> None:
    """Load simple KEY=VALUE settings, preserving variables set by the shell."""
    if not path.is_file():
        return
    values = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key.replace("_", "").isalnum() or key[0].isdigit():
            raise ValueError(f"Invalid setting in {path} on line {line_number}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    for key, value in values.items():
        os.environ.setdefault(key, value)


load_project_env(ROOT / ".env")
for import_path in reversed(os.getenv("PYTHONPATH", "").split(os.pathsep)):
    if import_path.strip():
        path = Path(import_path.strip())
        if not path.is_absolute():
            path = ROOT / path
        sys.path.insert(0, str(path.resolve()))

import numpy as np
import uvicorn
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Audio as MCPAudio, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel
from scipy.io.wavfile import write as write_wav
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from auth import OIDCTokenVerifier
from DeepLearningExamples.PyTorch.SpeechSynthesis.Tacotron2 import inference
from config.config import args, parser
from conversation import create_speech_rewriter, create_voice_agent, improve_spoken_text

logger = logging.getLogger(__name__)


MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1").strip()
MCP_PORT = int(os.getenv("MCP_PORT", "10000"))
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://127.0.0.1:{MCP_PORT}/mcp").strip().rstrip("/")
OAUTH_SCOPE = os.getenv("OAUTH_SCOPE", "voice:generate").strip()
OAUTH_FORCE_LOOPBACK = os.getenv("OAUTH_FORCE_LOOPBACK", "false").strip().lower() in {"1", "true", "yes"}
JWT_ALGORITHMS = [item.strip() for item in os.getenv("OAUTH_JWT_ALGORITHMS", "RS256").split(",") if item.strip()]

_oauth_names = ("OAUTH_ISSUER", "OAUTH_CLIENT_ID", "OAUTH_AUDIENCE", "OAUTH_REDIRECT_URI")
_oauth_values = {name: os.getenv(name, "").strip() for name in _oauth_names}
OAUTH_REQUIRED = all(_oauth_values.values())
_is_loopback = MCP_HOST.lower() in {"127.0.0.1", "localhost", "::1"}
if not OAUTH_REQUIRED and not _is_loopback:
    missing = ", ".join(name for name, value in _oauth_values.items() if not value)
    raise RuntimeError(f"OAuth settings are required when binding outside loopback; configure: {missing}")

OAUTH_ISSUER = _oauth_values["OAUTH_ISSUER"]
OAUTH_CLIENT_ID = _oauth_values["OAUTH_CLIENT_ID"]
OAUTH_AUDIENCE = _oauth_values["OAUTH_AUDIENCE"]
OAUTH_REDIRECT_URI = _oauth_values["OAUTH_REDIRECT_URI"]
LOCAL_ACCESS_TOKEN = secrets.token_urlsafe(32) if OAUTH_REQUIRED else None
verifier = None
mcp_auth = None
if OAUTH_REQUIRED:
    verifier = OIDCTokenVerifier(
        issuer=OAUTH_ISSUER,
        audience=OAUTH_AUDIENCE,
        required_scope=OAUTH_SCOPE,
        resource_url=MCP_SERVER_URL,
        algorithms=JWT_ALGORITHMS,
        local_access_token=LOCAL_ACCESS_TOKEN,
    )
    mcp_auth = AuthSettings(
        issuer_url=OAUTH_ISSUER,
        resource_server_url=MCP_SERVER_URL,
        required_scopes=[OAUTH_SCOPE],
        validate_token_resource=False,
    )

class AudioSamples(BaseModel):
    sample_rate: int
    samples: list[float]


mcp = MCPServer("Public Voice MCP", **({"token_verifier": verifier, "auth": mcp_auth} if OAUTH_REQUIRED else {}))
voice_agent = create_voice_agent()
speech_rewriter = create_speech_rewriter()
_inference_lock = threading.Lock()


def synthesize_samples(text: str, maxcharacters: int = 200, peak_level: float = 1.0,
                       voice: str = "Andrew Charabin") -> AudioSamples:
    if voice != "Andrew Charabin":
        raise ValueError("Only Andrew Charabin's voice is currently enabled")
    if not text.strip():
        raise ValueError("Enter some text to synthesize")
    if len(text) > maxcharacters:
        raise ValueError(f"Input text exceeds the maximum length of {maxcharacters} characters")
    if not 0.0 < peak_level <= 1.0:
        raise ValueError("Peak level must be greater than 0 and at most 1")

    with _inference_lock:
        args.input_text = text
        unscaled_audio = np.asarray(inference.main(args, parser))
    if unscaled_audio.size == 0:
        raise RuntimeError("No audio samples returned")

    peak = np.max(np.abs(unscaled_audio))
    if peak == 0:
        samples = np.zeros_like(unscaled_audio, dtype=np.float32)
    else:
        samples = np.asarray(unscaled_audio / peak * peak_level, dtype=np.float32)
    return AudioSamples(sample_rate=args.sampling_rate, samples=samples.tolist())


@mcp.tool()
def text_to_audio(text: str, maxcharacters: int = 200, peak_level: float = 1.0,
                  voice: str = "Andrew Charabin") -> AudioSamples:
    """Convert text to normalized 32-bit floating-point audio samples."""
    return synthesize_samples(text, maxcharacters, peak_level, voice)


@mcp.tool()
def text_to_audio_player(text: str, maxcharacters: int = 200, peak_level: float = 1.0,
                         voice: str = "Andrew Charabin") -> MCPAudio:
    """Convert text to playable 32-bit floating-point WAV audio content."""
    audio = synthesize_samples(text, maxcharacters, peak_level, voice)
    samples = np.clip(np.asarray(audio.samples, dtype=np.float32), -1.0, 1.0)
    wav_buffer = io.BytesIO()
    write_wav(wav_buffer, audio.sample_rate, samples)
    return MCPAudio(data=wav_buffer.getvalue(), format="wav")


def is_loopback_address(host: str | None) -> bool:
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or (
        isinstance(address, ipaddress.IPv6Address)
        and address.ipv4_mapped is not None
        and address.ipv4_mapped.is_loopback
    )


class MCPAccessMiddleware:
    """Inject a private loopback credential before MCP OAuth middleware."""

    def __init__(self, app, local_token: str | None, oauth_enabled: bool):
        self.app = app
        self.local_token = local_token
        self.oauth_enabled = oauth_enabled

    async def __call__(self, scope, receive, send):
        if (self.oauth_enabled and scope["type"] == "http"
                and scope.get("path", "").rstrip("/") == "/mcp"
                and not OAUTH_FORCE_LOOPBACK
                and is_loopback_address((scope.get("client") or (None,))[0])):
            scope = dict(scope)
            headers = [(key, value) for key, value in scope.get("headers", [])
                       if key.lower() != b"authorization"]
            headers.append((b"authorization", f"Bearer {self.local_token}".encode("ascii")))
            scope["headers"] = headers
        await self.app(scope, receive, send)

async def auth_config(request: Request) -> JSONResponse:
    return JSONResponse({
        "authRequired": OAUTH_REQUIRED and (
            OAUTH_FORCE_LOOPBACK
            or not is_loopback_address(request.client.host if request.client else None)
        ),
        "issuer": OAUTH_ISSUER,
        "clientId": OAUTH_CLIENT_ID,
        "audience": OAUTH_AUDIENCE,
        "scope": OAUTH_SCOPE,
        "resource": MCP_SERVER_URL,
        "redirectUri": OAUTH_REDIRECT_URI,
    }, headers={"Cache-Control": "no-store"})


async def authenticate_request(request: Request) -> tuple[str | None, Response | None]:
    local_request = is_loopback_address(request.client.host if request.client else None)
    if (local_request and not OAUTH_FORCE_LOOPBACK) or not OAUTH_REQUIRED:
        return "loopback", None
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    access = await verifier.verify_token(token) if scheme.lower() == "bearer" and token else None
    if access is None:
        return None, JSONResponse({"error": "Authentication required"}, status_code=401,
                                  headers={"WWW-Authenticate": "Bearer"})
    if OAUTH_SCOPE not in access.scopes:
        return None, JSONResponse({"error": f"Missing {OAUTH_SCOPE} permission"}, status_code=403)
    return f"{OAUTH_ISSUER}:{access.subject}", None


async def voice_api(request: Request) -> Response:
    _, auth_error = await authenticate_request(request)
    if auth_error:
        return auth_error
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        text = payload.get("text", "")
        if not isinstance(text, str):
            raise ValueError("Text must be a string")
        audio = await asyncio.to_thread(synthesize_samples, text, 1200)
        samples = np.clip(np.asarray(audio.samples, dtype=np.float32), -1.0, 1.0)
        wav_buffer = io.BytesIO()
        write_wav(wav_buffer, audio.sample_rate, samples)
        return Response(wav_buffer.getvalue(), media_type="audio/wav",
                        headers={"Cache-Control": "no-store"})
    except (ValueError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def chat_api(request: Request) -> Response:
    principal, auth_error = await authenticate_request(request)
    if auth_error:
        return auth_error
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        message = payload.get("message", "")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Enter a message")
        message = message.strip()
        if len(message) > 2000:
            raise ValueError("Message exceeds the 2000 character limit")
        conversation_id = payload.get("conversation_id")
        if conversation_id is None:
            conversation_id = secrets.token_urlsafe(24)
        if not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 128:
            raise ValueError("Invalid conversation id")

        result = await voice_agent.ainvoke(
            {"messages": [{"role": "user", "content": message}]},
            config={"configurable": {"thread_id": f"{principal}:{conversation_id}"}},
        )
        content = result["messages"][-1].content
        if isinstance(content, list):
            raw_parts = [
                item.get("text", "") for item in content
                if isinstance(item, dict) and item.get("type") == "text"
                and isinstance(item.get("text"), str) and item["text"].strip()
            ]
        else:
            raw_parts = [str(content).strip()]
        processed_parts = await improve_spoken_text(raw_parts, speech_rewriter)
        reply = " ".join(part for part in processed_parts if part).strip()
        if not reply:
            raise RuntimeError("The assistant returned an empty response")
        if len(reply) > 1200:
            reply = reply[:1197].rsplit(" ", 1)[0] + "..."
        return JSONResponse({"reply": reply, "conversation_id": conversation_id})
    except (ValueError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.error("Conversational agent failed (%s)", type(exc).__name__)
        return JSONResponse({"error": "The assistant could not respond. Please try again."}, status_code=502)

async def home(_: Request) -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


def create_app():
    raw_hosts = os.getenv("MCP_ALLOWED_HOSTS", "")
    raw_origins = os.getenv("MCP_ALLOWED_ORIGINS", "")
    transport_security = None
    if raw_hosts or raw_origins:
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[value.strip() for value in raw_hosts.split(",") if value.strip()],
            allowed_origins=[value.strip() for value in raw_origins.split(",") if value.strip()],
        )
    app = mcp.streamable_http_app(host=MCP_HOST, transport_security=transport_security)
    app.routes[0:0] = [
        Route("/", home, methods=["GET"]),
        Route("/auth/config", auth_config, methods=["GET"]),
        Route("/api/chat", chat_api, methods=["POST"]),
        Route("/api/voice", voice_api, methods=["POST"]),
        Mount("/assets", app=StaticFiles(directory=WEB_DIR), name="assets"),
    ]
    return MCPAccessMiddleware(app, LOCAL_ACCESS_TOKEN, OAUTH_REQUIRED)


if __name__ == "__main__":
    uvicorn.run(create_app(), host=MCP_HOST, port=MCP_PORT)
