const authButton = document.querySelector("#auth-button");
const newChatButton = document.querySelector("#new-chat-button");
const form = document.querySelector("#composer-form");
const sendButton = document.querySelector("#speak-button");
const textarea = document.querySelector("#text-input");
const counter = document.querySelector("#count");
const statusLine = document.querySelector("#status");
const messages = document.querySelector("#messages");
const accountLabel = document.querySelector("#account-label");
let config;
let accessToken = null;
let authRequired = true;
let sending = false;
let conversationId = sessionStorage.getItem("voice_conversation_id");
const audioUrls = [];

function setStatus(message, kind = "") {
  statusLine.textContent = message;
  statusLine.dataset.kind = kind;
}

function updateControls() {
  sendButton.disabled = sending || !textarea.value.trim() || textarea.value.length > 2000 || (authRequired && !accessToken);
  newChatButton.disabled = sending;
}

function base64Url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function randomVerifier() {
  return base64Url(crypto.getRandomValues(new Uint8Array(32)));
}

async function discover() {
  const url = `${config.issuer.replace(/\/$/, "")}/.well-known/openid-configuration`;
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("Could not load OAuth provider discovery metadata.");
  const metadata = await response.json();
  if (metadata.issuer !== config.issuer) throw new Error("OAuth issuer metadata did not match the configured issuer.");
  return metadata;
}

async function signIn() {
  try {
    setStatus("Preparing secure sign-in...");
    const metadata = await discover();
    const verifier = randomVerifier();
    const challenge = base64Url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
    const state = randomVerifier();
    sessionStorage.setItem("oauth_pkce_verifier", verifier);
    sessionStorage.setItem("oauth_state", state);
    const url = new URL(metadata.authorization_endpoint);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("client_id", config.clientId);
    url.searchParams.set("redirect_uri", config.redirectUri);
    url.searchParams.set("scope", `openid ${config.scope}`);
    url.searchParams.set("state", state);
    url.searchParams.set("code_challenge", challenge);
    url.searchParams.set("code_challenge_method", "S256");
    url.searchParams.set("resource", config.resource);
    url.searchParams.set("audience", config.audience);
    window.location.assign(url);
  } catch (error) {
    setStatus(error.message || "Sign-in could not be started.", "error");
  }
}

async function finishSignIn() {
  const query = new URLSearchParams(window.location.search);
  const code = query.get("code");
  if (!code) return;
  const returnedState = query.get("state");
  const expectedState = sessionStorage.getItem("oauth_state");
  const verifier = sessionStorage.getItem("oauth_pkce_verifier");
  sessionStorage.removeItem("oauth_state");
  sessionStorage.removeItem("oauth_pkce_verifier");
  window.history.replaceState({}, document.title, window.location.pathname);
  if (!expectedState || returnedState !== expectedState || !verifier) {
    throw new Error("OAuth state validation failed. Please sign in again.");
  }
  const metadata = await discover();
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: config.clientId,
    code,
    redirect_uri: config.redirectUri,
    code_verifier: verifier,
    resource: config.resource,
  });
  const response = await fetch(metadata.token_endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const tokenResponse = await response.json();
  if (!response.ok || !tokenResponse.access_token) {
    throw new Error(tokenResponse.error_description || "Token exchange failed.");
  }
  accessToken = tokenResponse.access_token;
  authButton.textContent = "Sign out";
  accountLabel.textContent = "Signed in";
  setStatus("Signed in. You can start chatting.");
  updateControls();
}

function appendMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message message-${role}`;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "You" : "V";
  const content = document.createElement("div");
  content.className = "message-content";
  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "user" ? "You" : "Andrew's voice assistant";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  content.append(label, paragraph);
  article.append(avatar, content);
  messages.append(article);
  article.scrollIntoView({ behavior: "smooth", block: "end" });
  return { article, content };
}

function authHeaders(json = false) {
  const headers = {};
  if (json) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return headers;
}

async function readError(response) {
  if (response.status === 401) {
    accessToken = null;
    authButton.textContent = "Sign in";
    accountLabel.textContent = "";
    updateControls();
    return "Your sign-in expired. Sign in again to continue.";
  }
  const error = await response.json().catch(() => ({}));
  return error.error || "The request could not be completed.";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = textarea.value.trim();
  if (!message || sending || (authRequired && !accessToken)) return;
  sending = true;
  updateControls();
  appendMessage("user", message);
  textarea.value = "";
  counter.textContent = "0 / 2000";
  const pending = appendMessage("assistant", "Thinking...");
  let assistantReplyReceived = false;
  setStatus("Thinking...");

  try {
    const chatResponse = await fetch("/api/chat", {
      method: "POST",
      headers: authHeaders(true),
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });
    if (!chatResponse.ok) throw new Error(await readError(chatResponse));
    const result = await chatResponse.json();
    conversationId = result.conversation_id;
    sessionStorage.setItem("voice_conversation_id", conversationId);
    pending.content.querySelector("p").textContent = result.reply;
    assistantReplyReceived = true;
    setStatus("Preparing the spoken response...");

    const audioResponse = await fetch("/api/voice", {
      method: "POST",
      headers: authHeaders(true),
      body: JSON.stringify({ text: result.reply }),
    });
    if (!audioResponse.ok) throw new Error(await readError(audioResponse));
    const audioUrl = URL.createObjectURL(await audioResponse.blob());
    audioUrls.push(audioUrl);
    const player = document.createElement("audio");
    player.controls = true;
    player.preload = "metadata";
    player.src = audioUrl;
    player.setAttribute("aria-label", "Listen to the assistant response");
    pending.content.append(player);
    try {
      await player.play();
      setStatus("Response ready.");
    } catch {
      setStatus("Response ready. Press play to listen.");
    }
  } catch (error) {
    if (assistantReplyReceived) {
      const warning = document.createElement("small");
      warning.className = "speech-error";
      warning.textContent = `The reply was received, but its audio could not be generated: ${error.message}`;
      pending.content.append(warning);
    } else {
      pending.content.querySelector("p").textContent = error.message || "Something went wrong. Please try again.";
      pending.article.classList.add("message-error");
    }
    setStatus(error.message || "Something went wrong.", "error");
  } finally {
    sending = false;
    updateControls();
    textarea.focus();
  }
});

textarea.addEventListener("input", () => {
  counter.textContent = `${textarea.value.length} / 2000`;
  updateControls();
});

authButton.addEventListener("click", () => {
  if (!accessToken) return signIn();
  accessToken = null;
  authButton.textContent = "Sign in";
  accountLabel.textContent = "";
  setStatus("Signed out.");
  updateControls();
});

newChatButton.addEventListener("click", () => {
  conversationId = null;
  sessionStorage.removeItem("voice_conversation_id");
  for (const url of audioUrls) URL.revokeObjectURL(url);
  audioUrls.length = 0;
  messages.replaceChildren();
  appendMessage("assistant", "Hi, I'm here. What would you like to talk about?");
  setStatus(authRequired && !accessToken ? "Sign in to start chatting." : "New conversation ready.");
});

(async function initialize() {
  try {
    const response = await fetch("/auth/config", { cache: "no-store" });
    if (!response.ok) throw new Error("The app could not load its OAuth configuration.");
    config = await response.json();
    authRequired = config.authRequired;
    if (authRequired) {
      authButton.hidden = false;
      if (window.location.search.includes("error=")) {
        const query = new URLSearchParams(window.location.search);
        throw new Error(query.get("error_description") || query.get("error"));
      }
      await finishSignIn();
      if (!accessToken) setStatus("Sign in to start chatting.");
    } else {
      authButton.hidden = true;
      setStatus("Ready. Start a conversation.");
    }
    updateControls();
  } catch (error) {
    setStatus(error.message || "The app could not initialize.", "error");
  }
})();
