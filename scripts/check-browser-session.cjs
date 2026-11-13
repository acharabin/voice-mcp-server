const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function storage() {
  const data = new Map();
  return { getItem: k => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)), removeItem: k => data.delete(k) };
}

const localStorage = storage(), sessionStorage = storage();
const context = vm.createContext({ localStorage, sessionStorage, TextDecoder, Uint8Array, atob, Date });
vm.runInContext(fs.readFileSync('web/session.js', 'utf8') + '\nglobalThis.session = ChatSession;', context);
const session = context.session;
const config = { authRequired: true, issuer: 'https://issuer.test', clientId: 'chat' };
const token = sub => `header.${Buffer.from(JSON.stringify({ sub })).toString('base64url')}.signature`;
const ownerA = session.owner(config, token('a'));
const ownerB = session.owner(config, token('b'));
session.save(ownerA, { id: 'conversation-1', draft: 'Draft', turns: [{role:'assistant', text:'Hello', provider:'qwen'}] });
assert.equal(session.load(ownerA).id, 'conversation-1');
assert.equal(session.load(ownerA).draft, 'Draft');
assert.equal(session.load(ownerB), null, 'Other accounts must not see cached chats');
session.provider('openai');
assert.equal(session.provider(), 'openai');
session.auth(config, {token: token('a'), expiresAt: Date.now() + 60000});
assert.equal(session.auth(config), token('a'));
assert.equal(localStorage.getItem('andrew_auth'), null);
session.auth(config, {token:'expired', expiresAt: Date.now() - 1});
assert.equal(session.auth(config), null);
session.auth(config, {token:'invalid'});
assert.equal(session.auth(config), null);
session.auth(config, null);
assert.equal(session.load(ownerA).id, 'conversation-1', 'Re-sign-in must retain chat');
session.save(ownerA, {id:null, draft:'', turns:[]});
assert.equal(session.load(ownerA).turns.length, 0);
localStorage.setItem(`andrew_chat:${ownerA}`, '{broken');
assert.equal(session.load(ownerA), null);

// Exercise the app across a fresh page, a reload, and the New chat action.
class Element {
  constructor(tag = 'div') { this.tag = tag; this.children = []; this.dataset = {}; this.handlers = {}; this.value = ''; this.textContent = ''; this.className = ''; this.classList = {add(){}}; }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  setAttribute(name, value) { if(name === 'data-greeting') this.dataset.greeting = value; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  querySelector(selector) {
    const matches = e => selector === 'p' ? e.tag === 'p' : selector === '.message[data-greeting]' ? e.className.includes('message-assistant') && e.dataset.greeting : e.className.split(' ').includes(selector.slice(1));
    for(const child of this.children) { if(matches(child)) return child; const found = child.querySelector(selector); if(found) return found; }
    return null;
  }
  scrollIntoView() {}
  focus() {}
  async play() {}
}

async function page() {
  const nodes = {};
  for(const id of ['auth-button','new-chat-button','composer-form','speak-button','text-input','count','status','messages','account-label','model-provider','conversation-mode']) nodes[`#${id}`] = new Element();
  const requests = [];
  const sandbox = vm.createContext({
    localStorage, sessionStorage, TextDecoder, Uint8Array, atob, Date,
    document: {querySelector: s => nodes[s], createElement: tag => new Element(tag)},
    window: {location:{search:''}, addEventListener(){}},
    URL: {createObjectURL:()=> 'blob:test', revokeObjectURL(){}},
    setTimeout:()=>1, clearTimeout(){},
    fetch: async (url, options) => {
      requests.push({url, options});
      if(url === '/auth/config') return {ok:true, json:async()=>({authRequired:false})};
      if(url === '/api/chat') return {ok:true,json:async()=>({reply:'Hello again',conversation_id:'same-conversation'})};
      return {ok:true,blob:async()=>({})};
    },
  });
  vm.runInContext(fs.readFileSync('web/session.js','utf8'), sandbox);
  vm.runInContext(fs.readFileSync('web/app.js','utf8'), sandbox);
  await new Promise(resolve => setImmediate(resolve));
  return {nodes, requests};
}

(async () => {
  const first = await page();
  first.nodes['#text-input'].value = 'Hello';
  await first.nodes['#composer-form'].handlers.submit({preventDefault(){}});
  first.nodes['#text-input'].value = 'Unsent draft';
  first.nodes['#text-input'].handlers.input();
  const reloaded = await page();
  assert.equal(reloaded.nodes['#text-input'].value, 'Unsent draft');
  assert.equal(reloaded.nodes['#messages'].children.length, 3, 'Greeting and both saved turns restored');
  await reloaded.nodes['#composer-form'].handlers.submit({preventDefault(){}});
  const request = reloaded.requests.find(r=>r.url === '/api/chat');
  assert.equal(JSON.parse(request.options.body).conversation_id, 'same-conversation');
  reloaded.nodes['#new-chat-button'].handlers.click();
  const reset = await page();
  assert.equal(reset.nodes['#messages'].children.length, 1);
  assert.equal(reset.nodes['#text-input'].value, '');
  console.log('PASS: account scoping, auth expiry, reload, transcript, draft, continued conversation, and explicit reset');
})().catch(error => {console.error(error); process.exitCode = 1;});
