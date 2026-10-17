'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Load the real functions; exclude page event registration and startup requests.
const source = fs.readFileSync(path.join(__dirname, '../app/web/app.js'), 'utf8').split("$('#close-modal').addEventListener")[0];
function context(storage = {}) {
  const elements = new Map();
  function element(selector) {
    if (!elements.has(selector)) elements.set(selector, {
      textContent: '', hidden: false, open: true, listeners: {},
      addEventListener(name, callback) { this.listeners[name] = callback; },
      setAttribute() {}, replaceChildren() {}, close() { this.open = false; },
    });
    return elements.get(selector);
  }
  const attributes = {};
  const media = { matches: false, addEventListener() {} };
  const sandbox = vm.createContext({
    document: { querySelector: element, documentElement: {
      setAttribute(name, value) { attributes[name] = value; },
      removeAttribute(name) { delete attributes[name]; },
    } },
    window: { matchMedia() { return media; } },
    localStorage: { getItem() { return null; }, setItem() {}, removeItem() {}, ...storage },
    FormData, URLSearchParams,
  });
  vm.runInContext(source, sandbox);
  return { sandbox, element, attributes };
}

test('blocked theme storage still initializes and cycles the theme', () => {
  const denied = () => { throw new Error('Storage is blocked'); };
  const { sandbox, element, attributes } = context({ getItem: denied, setItem: denied, removeItem: denied });
  vm.runInContext('initTheme()', sandbox);
  const click = element('#theme-toggle').listeners.click;
  assert.equal(element('#theme-text').textContent, 'Auto');
  click(); assert.equal(attributes['data-theme'], 'dark');
  click(); assert.equal(attributes['data-theme'], 'light');
  click(); assert.equal(attributes['data-theme'], undefined);
});

test('invalid stored theme falls back to system preference', () => {
  const { sandbox, element } = context({ getItem() { return 'invalid-theme'; } });
  vm.runInContext('initTheme()', sandbox);
  assert.equal(element('#theme-text').textContent, 'Auto');
});

test('non-JSON 401 still clears an expired session', async () => {
  const { sandbox } = context();
  sandbox.fetch = async () => ({ status: 401, ok: false, json: async () => { throw new SyntaxError('HTML'); } });
  vm.runInContext("state.token = 'expired'; state.user = {id: 1}; setAccount = () => {};", sandbox);
  await assert.rejects(vm.runInContext("api('/auth/me')", sandbox), /Request failed \(401\)/);
  assert.equal(vm.runInContext('state.token', sandbox), null);
  assert.equal(vm.runInContext('state.user', sandbox), null);
});

test('non-JSON successful response produces a useful retry error', async () => {
  const { sandbox } = context();
  sandbox.fetch = async () => ({ status: 200, ok: true, json: async () => { throw new SyntaxError('HTML'); } });
  await assert.rejects(vm.runInContext("api('/items')", sandbox), /unreadable response/);
});

test('late unauthorized response cannot clear a newer login', async () => {
  const { sandbox } = context();
  let respond;
  sandbox.fetch = () => new Promise(resolve => { respond = resolve; });
  vm.runInContext("state.token = 'old'; state.user = {id: 1}", sandbox);
  const pending = vm.runInContext("api('/auth/me')", sandbox);
  vm.runInContext("state.token = 'new'; state.user = {id: 2}", sandbox);
  respond({ status: 401, ok: false, json: async () => ({ detail: 'Expired' }) });
  await assert.rejects(pending, /Expired/);
  assert.equal(vm.runInContext('state.token', sandbox), 'new');
  assert.equal(vm.runInContext('state.user.id', sandbox), 2);
});

test('a failed form request cannot write errors into a replacement dialog', async () => {
  const { sandbox } = context();
  const notices = [];
  let rejectRequest, submitHandler;
  sandbox.FormData = class { *[Symbol.iterator]() {} };
  sandbox.form = {
    isConnected: true, append() {},
    addEventListener(name, callback) { submitHandler = callback; },
  };
  sandbox.captureNotice = message => notices.push(message);
  sandbox.handler = () => new Promise((resolve, reject) => { rejectRequest = reject; });
  vm.runInContext('node = () => ({}); notice = captureNotice; wireForm(form, handler, "Save")', sandbox);
  const pending = submitHandler({ preventDefault() {} });
  sandbox.form.isConnected = false;
  rejectRequest(new Error('Error from previous dialog'));
  await pending;
  assert.deepEqual(notices, ['']);
});

test('a late report error cannot overwrite the current dialog', async () => {
  const { sandbox } = context();
  const notices = [];
  let rejectRequest;
  sandbox.captureNotice = message => notices.push(message);
  sandbox.pendingRequest = () => new Promise((resolve, reject) => { rejectRequest = reject; });
  vm.runInContext('openModal = () => ({append() {}}); node = () => ({}); notice = captureNotice; api = pendingRequest', sandbox);
  const pending = vm.runInContext('reportDetail(123)', sandbox);
  vm.runInContext('++modalGeneration', sandbox);
  rejectRequest(new Error('Old report no longer exists'));
  await pending;
  assert.deepEqual(notices, []);
});
