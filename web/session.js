/* Browser persistence. Credentials stay in tab storage, never in cookies. */
const ChatSession = (() => {
  function read(storage, key) {
    try { return JSON.parse(storage.getItem(key)); } catch { return null; }
  }
  function write(storage, key, value) {
    try {
      if (value === null) storage.removeItem(key);
      else storage.setItem(key, JSON.stringify(value));
    } catch { /* Chat still works when browser storage is unavailable/full. */ }
  }
  function owner(config, token) {
    if (!config.authRequired) return "local";
    const encoded = token.split(".")[1].replaceAll("-", "+").replaceAll("_", "/");
    const claims = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(encoded), c => c.charCodeAt(0))));
    if (typeof claims.sub !== "string" || !claims.sub) throw new Error("Sign-in token has no account identity.");
    // This only partitions the display cache; the server verifies authorization.
    return JSON.stringify([config.issuer, config.clientId, claims.sub]);
  }
  function key(owner) { return `andrew_chat:${owner}`; }
  function load(owner) {
    const value = read(localStorage, key(owner));
    if (!value || typeof value !== "object") return null;
    return {
      id: typeof value.id === "string" && value.id.length <= 128 ? value.id : null,
      draft: typeof value.draft === "string" ? value.draft.slice(0, 2000) : "",
      turns: Array.isArray(value.turns) ? value.turns.filter(turn =>
        turn && ["user", "assistant"].includes(turn.role) && typeof turn.text === "string"
        && ["qwen", "openai"].includes(turn.provider)
      ) : [],
    };
  }
  function save(owner, value) { write(localStorage, key(owner), value); }
  function provider(value) {
    if (value !== undefined) write(localStorage, "andrew_provider", value);
    return read(localStorage, "andrew_provider") === "openai" ? "openai" : "qwen";
  }
  function auth(config, value) {
    const key = `andrew_auth:${JSON.stringify([config.issuer, config.clientId])}`;
    if (value !== undefined) write(sessionStorage, key, value);
    const stored = read(sessionStorage, key);
    if (!stored || typeof stored.token !== "string" || !Number.isFinite(stored.expiresAt)
        || stored.expiresAt <= Date.now() + 10000) {
      write(sessionStorage, key, null);
      return null;
    }
    return stored.token;
  }
  return { owner, load, save, provider, auth };
})();
