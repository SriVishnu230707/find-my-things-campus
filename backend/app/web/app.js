'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const state = { token: null, user: null, view: 'browse', page: 0, generation: 0 };
const pageSize = 12;
state.staffPanel = 'summary';
state.accountConfig = { verification_required: true, campus_domains: [], email_delivery: 'local' };
let notificationPolling = false;
const modal = $('#modal');
let modalGeneration = 0;
const symbols = { electronics: '⌁', clothing: '♧', documents: '▤', accessories: '◇', other: '✳' };

function initTheme() {
  const toggleBtn = $('#theme-toggle');
  const themeLabel = $('#theme-text');

  function applyTheme(theme) {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else if (theme === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }

    if (themeLabel) {
      themeLabel.textContent = theme ? (theme === 'dark' ? 'Dark' : 'Light') : 'Auto';
    }
    if (toggleBtn) {
      toggleBtn.title = `Theme: ${theme ? (theme === 'dark' ? 'Dark' : 'Light') : 'Auto (System)'}`;
    }
  }

  // Restore saved preference
  const savedTheme = localStorage.getItem('campus_theme');
  applyTheme(savedTheme);

  // Auto inherit OS preference changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (!localStorage.getItem('campus_theme')) {
      applyTheme(null);
    }
  });

  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const current = localStorage.getItem('campus_theme');
      let next;
      if (!current) {
        const isSystemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        next = isSystemDark ? 'light' : 'dark';
      } else if (current === 'dark') {
        next = 'light';
      } else {
        next = null;
      }

      if (next) {
        localStorage.setItem('campus_theme', next);
      } else {
        localStorage.removeItem('campus_theme');
      }
      applyTheme(next);
    });
  }
}

function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function notice(message, error = false, inModal = false) {
  const target = $(inModal ? '#modal-error' : '#notice');
  target.textContent = message;
  target.className = 'notice' + (error ? ' error' : '');
  target.hidden = !message;
}
function setAccount() {
  $('#user-label').textContent = state.user ? `${state.user.display_name}${state.user.role === 'staff' ? ' · staff' : ''}` : '';
  $('#login-button').hidden = !!state.user;
  $('#logout-button').hidden = !state.user;
  $('#account-button').hidden = !state.user;
  $('#staff-tab').hidden = state.user?.role !== 'staff';
  $('#notification-count').hidden = true;
  $('#notification-count').textContent = '0';
  if (state.user) refreshNotificationCount();
}
async function refreshNotificationCount() {
  if (!state.token || notificationPolling) return;
  const token = state.token; notificationPolling = true;
  try {
    const data = await api('/notifications/unread-count');
    if (state.token !== token) return;
    const badge = $('#notification-count'); badge.textContent = String(data.unread_count); badge.hidden = data.unread_count === 0;
  } catch { /* Inbox errors remain retryable through the notifications view. */ }
  finally { notificationPolling = false; }
}
async function api(path, { method = 'GET', body, form = false } = {}) {
  const requestToken = state.token;
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const multipart = body instanceof FormData;
  if (body !== undefined && !multipart) headers['Content-Type'] = form ? 'application/x-www-form-urlencoded' : 'application/json';
  let response;
  try { response = await fetch(path, { method, headers, body: body === undefined ? undefined : multipart ? body : form ? new URLSearchParams(body) : JSON.stringify(body) }); }
  catch { throw new Error('Unable to connect. Check your connection and try again.'); }
  const result = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    if (response.status === 401 && state.token && state.token === requestToken) {
      ++state.generation;
      state.token = null; state.user = null; setAccount();
      modal.close();
      $('#results').replaceChildren();
      $('#results').setAttribute('aria-busy', 'false');
      $('#results-label').textContent = 'Sign in to continue';
      $('#inbox-tools').hidden = true;
      $('#previous').disabled = true; $('#next').disabled = true;
      notice('Your session expired. Sign in again to continue.', true);
    }
    const details = Array.isArray(result?.detail) ? result.detail.map(e => `${e.loc.filter(x => !['body', 'query'].includes(x)).join('.')}: ${e.msg}`).join(' · ') : result?.detail;
    throw new Error((details || `Request failed (${response.status})`) + (response.status === 429 ? ' Please wait a minute and try again.' : ''));
  }
  return result;
}
function button(label, action, className = 'button subtle') {
  const el = node('button', label, className); el.type = 'button'; el.addEventListener('click', action); return el;
}
function openModal(title) {
  ++modalGeneration;
  $('#modal-title').textContent = title; $('#modal-body').replaceChildren(); notice('', false, true);
  if (!modal.open) modal.showModal();
  return $('#modal-body');
}
function field(form, label, name, { type = 'text', value = '', options, min, max, required = true } = {}) {
  const wrapper = node('label', label);
  const input = node(options ? 'select' : type === 'textarea' ? 'textarea' : 'input');
  input.name = name; input.required = required;
  input.setAttribute('aria-label', label);
  if (!options && type !== 'textarea') input.type = type;
  if (options) for (const option of options) { const el = node('option', option); el.value = option; input.append(el); }
  if (min) input.minLength = min; if (max) input.maxLength = max;
  if (type === 'password') input.autocomplete = name === 'password' && form.dataset.register === 'true' ? 'new-password' : 'current-password';
  if (type === 'email') input.autocomplete = 'email';
  input.value = value; wrapper.append(input); form.append(wrapper); return input;
}
function wireForm(form, handler, label) {
  const submit = node('button', label, 'button dark'); submit.type = 'submit'; form.append(submit);
  form.addEventListener('submit', async event => {
    event.preventDefault(); notice('', false, true); submit.disabled = true;
    try { await handler(Object.fromEntries(new FormData(form))); }
    catch (error) { notice(error.message, true, true); }
    finally { submit.disabled = false; }
  });
}
function authForm(register = false) {
  const body = openModal(register ? 'Join your campus community' : 'Welcome back.');
  body.append(node('p', register ? `Create a student account, then verify your email from Account before posting or claiming.${state.accountConfig.campus_domains.length ? ' Allowed campus domains: ' + state.accountConfig.campus_domains.join(', ') : ''}` : 'Sign in to manage your reports and claims. Sessions last 15 minutes; refreshing this page signs you out.', 'hint'));
  const form = node('form', undefined, 'form-stack'); form.dataset.register = String(register); body.append(form);
  if (register) field(form, 'Display name', 'display_name', { min: 2, max: 100 });
  field(form, 'Email address', 'email', { type: 'email', max: 254 });
  field(form, 'Password', 'password', { type: 'password', min: register ? 12 : 1, max: 128 });
  wireForm(form, async data => {
    if (register) await api('/auth/register', { method: 'POST', body: data });
    const login = await api('/auth/login', { method: 'POST', form: true, body: { username: data.email, password: data.password } });
    state.token = login.access_token;
    try { state.user = await api('/auth/me'); } catch (error) { state.token = null; throw error; }
    setAccount(); modal.close(); state.page = 0; notice(register ? 'Account created. Welcome to the community!' : 'You’re signed in.'); await load();
  }, register ? 'Create account' : 'Sign in');
  body.append(button(register ? 'Already have an account? Sign in' : 'New here? Create an account', () => authForm(!register), 'text-button'));
  if (!register) body.append(button('Forgot password?', () => emailInstructionForm('reset', form.elements.email.value), 'text-button'));
}
function eligibleAccount() { return state.user && (state.user.role === 'staff' || !state.accountConfig.verification_required || (state.user.email_verified && (!state.accountConfig.campus_domains.length || state.user.campus_verified))); }
function requireAccount() { if (!state.user) { authForm(); return false; } if (!eligibleAccount()) { accountForm(); return false; } return true; }
function accountForm() {
  if (!state.user) { authForm(); return; }
  const body = openModal('Your account');
  body.append(node('p', state.user.display_name, 'detail-description'), node('p', `${state.user.email} · ${state.user.role}`, 'hint'), badge(state.user.campus_verified ? 'campus verified' : state.user.email_verified ? 'email verified' : 'verification needed'));
  if (!state.accountConfig.campus_domains.length) body.append(node('p', 'Campus domains have not been configured. Email verification confirms access to your inbox, not college membership.', 'hint'));
  else body.append(node('p', 'Approved campus domains: ' + state.accountConfig.campus_domains.join(', '), 'hint'));
  if (!state.user.email_verified) body.append(button('Send verification email', () => emailInstructionForm('verify', state.user.email), 'button dark'));
  body.append(button('Enter verification code', () => accountTokenForm('verify')));
  body.append(button('Reset password', () => emailInstructionForm('reset', state.user.email)));
}
function emailInstructionForm(purpose, email = '') {
  const body = openModal(purpose === 'verify' ? 'Verify your email' : 'Reset your password');
  const form = node('form', undefined, 'form-stack'); body.append(form);
  field(form, 'Email address', 'email', { type: 'email', value: email, max: 254 });
  wireForm(form, async data => {
    const response = await api(purpose === 'verify' ? '/auth/verification/request' : '/auth/password/request', { method: 'POST', body: data });
    const content = openModal('Check your email'); content.append(node('p', response.message, 'hint'));
    if (state.accountConfig.email_delivery === 'local') content.append(node('p', 'Development mode: emails are saved privately on the server. Ask the operator for your link or code; nothing was sent to a real inbox.', 'hint'));
    content.append(node('p', 'Repeated requests within one minute are ignored. Use the newest link; older links are replaced.', 'hint'), button('Enter code', () => accountTokenForm(purpose), 'button dark'));
  }, 'Send instructions');
}
function accountTokenForm(purpose, initialToken = '') {
  const body = openModal(purpose === 'verify' ? 'Confirm your email' : 'Choose a new password');
  const form = node('form', undefined, 'form-stack'); body.append(form);
  const tokenInput = field(form, purpose === 'verify' ? 'Verification code' : 'Reset code', 'token', { type: 'password', value: initialToken, min: 40, max: 128 }); tokenInput.autocomplete = 'off';
  if (purpose === 'reset') {
    field(form, 'New password', 'password', { type: 'password', min: 12, max: 128 }).autocomplete = 'new-password';
    field(form, 'Confirm new password', 'confirmation', { type: 'password', min: 12, max: 128 }).autocomplete = 'new-password';
  }
  wireForm(form, async data => {
    if (purpose === 'reset' && data.password !== data.confirmation) throw new Error('Passwords do not match.');
    delete data.confirmation;
    const result = await api(purpose === 'verify' ? '/auth/verification/confirm' : '/auth/password/reset', { method: 'POST', body: data });
    if (purpose === 'reset') { ++state.generation; state.token = null; state.user = null; }
    else if (state.token) state.user = await api('/auth/me');
    setAccount(); modal.close(); notice(result.message); state.page = 0; await load();
  }, purpose === 'verify' ? 'Confirm email' : 'Update password');
}
function reportForm(item = null) {
  if (!requireAccount()) return;
  const body = openModal(item ? 'Edit your report' : 'Report an item');
  const form = node('form', undefined, 'form-stack'); body.append(form);
  let savedItem = item;
  field(form, 'Title', 'title', { value: item?.title, min: 3, max: 120 });
  field(form, 'Description', 'description', { type: 'textarea', value: item?.description, min: 10, max: 2000 });
  field(form, 'Location', 'location', { value: item?.location, min: 2, max: 150 });
  field(form, 'Category', 'category', { value: item?.category || 'electronics', options: Object.keys(symbols) });
  field(form, 'Report type', 'type', { value: item?.type || 'lost', options: ['lost', 'found'] });
  const photoInput = field(form, 'Photo (optional · JPEG or PNG · up to 2 MiB)', 'photo', { type: 'file', required: false });
  photoInput.accept = 'image/jpeg,image/png';
  const preview = node('img', undefined, 'photo-preview'); preview.alt = 'Selected photo preview'; preview.hidden = true; form.append(preview);
  if (item?.photo_url) { preview.src = item.photo_url; preview.alt = 'Current report photo'; preview.hidden = false; }
  photoInput.addEventListener('change', () => {
    const file = photoInput.files[0]; notice('', false, true);
    if (!file) { preview.hidden = true; preview.removeAttribute('src'); return; }
    if (file.size > 2 * 1024 * 1024 || !['image/jpeg', 'image/png'].includes(file.type)) {
      photoInput.value = ''; preview.hidden = true; preview.removeAttribute('src'); notice('Choose a JPEG or PNG photo no larger than 2 MiB.', true, true); return;
    }
    const reader = new FileReader(); reader.onload = () => { if (!photoInput.isConnected || photoInput.files[0] !== file) return; preview.src = reader.result; preview.alt = 'Selected photo preview'; preview.hidden = false; }; reader.readAsDataURL(file);
  });
  body.append(node('p', 'Reports and photos are public. Describe the item clearly, and keep contact information, identity documents, and private identifying details out of photos and descriptions.', 'hint'));
  wireForm(form, async data => {
    const photo = photoInput.files[0]; delete data.photo;
    if (savedItem) for (const key of Object.keys(data)) if (data[key] === savedItem[key]) delete data[key];
    if (!savedItem || Object.keys(data).length) savedItem = await api(savedItem ? `/items/${savedItem.id}` : '/items', { method: savedItem ? 'PATCH' : 'POST', body: data });
    if (photo) {
      const upload = new FormData(); upload.append('photo', photo);
      try { savedItem = await api(`/items/${savedItem.id}/photo`, { method: 'PUT', body: upload }); }
      catch (error) { throw new Error(`Report #${savedItem.id} was saved, but the photo was not: ${error.message} You can retry here without creating another report.`); }
    }
    modal.close(); notice(item ? 'Report updated.' : 'Your report is on the noticeboard.'); state.page = 0; await load();
  }, item ? 'Save changes' : 'Post report');
}
function date(value) { return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(value)); }
function badge(value) { return node('span', value, 'badge ' + value); }
function empty(title, message, action) {
  const box = node('div', undefined, 'empty'); box.append(node('span', '↩'), node('h3', title), node('p', message));
  if (action) box.append(action); $('#results').append(box);
}
async function load() {
  const generation = ++state.generation;
  const results = $('#results'); results.replaceChildren(); results.setAttribute('aria-busy', 'true');
  $('#results-label').textContent = 'Loading…'; $('#previous').disabled = true; $('#next').disabled = true;
  $('#filters').hidden = !['browse', 'reports'].includes(state.view) && !(state.view === 'staff' && state.staffPanel === 'reports');
  $('#staff-tools').hidden = state.view !== 'staff' || state.user?.role !== 'staff';
  $('#staff-status-label').hidden = state.staffPanel !== 'claims';
  $('#inbox-tools').hidden = state.view !== 'notifications' || !state.user;
  document.querySelectorAll('.tab').forEach(tab => { tab.classList.toggle('active', tab.dataset.view === state.view); if (tab.dataset.view === state.view) tab.setAttribute('aria-current', 'page'); else tab.removeAttribute('aria-current'); });
  $('#page-label').textContent = `Page ${state.page + 1}`;
  if (state.view !== 'browse' && !state.user) {
    results.setAttribute('aria-busy', 'false'); $('#results-label').textContent = 'Your personal workspace';
    empty('A little space of your own.', 'Sign in to see your reports and private claims.', button('Sign in', () => authForm(), 'button dark')); return;
  }
  if (state.view === 'staff' && state.user?.role !== 'staff') { results.setAttribute('aria-busy', 'false'); $('#results-label').textContent = 'Staff workspace'; empty('Staff access required.', 'Sign in with an authorized staff account.'); return; }
  if (state.view === 'staff' && state.staffPanel === 'summary') {
    try {
      const data = await api('/staff/summary'); if (generation !== state.generation) return;
      $('#results-label').textContent = 'Campus overview';
      const names = { users: 'Accounts', verified_users: 'Email-verified accounts', active_users: 'Active accounts', reports: 'Total reports', open_reports: 'Open reports', resolved_reports: 'Resolved reports', archived_reports: 'Archived reports', pending_claims: 'Pending claims' };
      for (const [key, label] of Object.entries(names)) { const card = node('div', undefined, 'card staff-metric'); const content = node('div', undefined, 'card-content'); content.append(node('h3', label), node('strong', String(data[key]), 'metric-value')); card.append(content); results.append(card); }
    } catch (error) { if (generation === state.generation) empty('Could not load the dashboard.', error.message, button('Retry', load)); }
    finally { if (generation === state.generation) results.setAttribute('aria-busy', 'false'); }
    return;
  }
  const params = new URLSearchParams();
  if (!$('#filters').hidden) for (const [key, value] of new FormData($('#filters'))) {
    const trimmed = String(value).trim();
    if (trimmed && key !== 'archived') params.set(key, trimmed);
  }
  if (!$('#filters').hidden) params.set('archived', String($('#filters [name=archived]').checked));
  if (state.view === 'staff' && state.staffPanel === 'claims') params.set('status', $('#staff-claim-status').value);
  if (state.view === 'notifications') params.set('unread_only', String($('#unread-only').checked));
  params.set('limit', pageSize); params.set('offset', state.page * pageSize);
  const path = state.view === 'staff' ? `/staff/${state.staffPanel}` : state.view === 'notifications' ? '/notifications' : state.view === 'claims' ? '/claims/me' : state.view === 'reports' ? '/items/mine' : '/items';
  try {
    const items = await api(`${path}?${params}`); if (generation !== state.generation) return;
    const noun = state.view === 'staff' ? ({ reports: 'report', claims: 'claim', users: 'account', audit: 'event' }[state.staffPanel]) : state.view === 'notifications' ? 'notification' : state.view === 'claims' ? 'claim' : 'report';
    $('#results-label').textContent = `${items.length} ${noun}${items.length === 1 ? '' : 's'} on this page`;
    if (!items.length) empty(state.view === 'notifications' ? 'You’re all caught up.' : state.view === 'claims' ? 'No claims just yet.' : 'Nothing here just yet.', state.view === 'notifications' ? 'Claim updates will appear here. Refresh to check for new activity.' : state.view === 'claims' ? 'Recognize something on the noticeboard? Open a found report to submit a private claim.' : 'Try different filters, or be the first to share a lost or found item.');
    for (const item of items) state.view === 'staff' ? results.append(staffCard(item)) : state.view === 'notifications' ? results.append(notificationCard(item)) : state.view === 'claims' ? results.append(claimCard(item)) : results.append(reportCard(item));
    if (state.user) refreshNotificationCount();
    $('#previous').disabled = state.page === 0; $('#next').disabled = items.length < pageSize;
  } catch (error) { if (generation === state.generation) { $('#results-label').textContent = 'Could not load results'; empty('Let’s try that again.', error.message, button('Retry', load)); } }
  finally { if (generation === state.generation) results.setAttribute('aria-busy', 'false'); }
}
function staffCard(entry) {
  if (state.staffPanel === 'reports') return reportCard(entry);
  const card = node('div', undefined, 'card'); const content = node('div', undefined, 'card-content'); card.append(content);
  if (state.staffPanel === 'users') {
    content.append(badge(entry.is_active ? 'active' : 'disabled'), node('h3', entry.display_name), node('p', entry.email), node('p', `${entry.role} · ${entry.campus_verified ? 'campus verified' : entry.email_verified ? 'email verified' : 'unverified'} · Account #${entry.id}`, 'hint'));
    if (entry.role !== 'staff') content.append(button(entry.is_active ? 'Disable account' : 'Enable account', () => {
      const body = openModal(entry.is_active ? 'Disable this account?' : 'Enable this account?'); body.append(node('p', 'This revokes previous sessions. Reports and claim history are preserved. Do not put passwords or private claim evidence in the reason.', 'hint'));
      const form = node('form', undefined, 'form-stack'); body.append(form); field(form, 'Reason for moderation', 'reason', { type: 'textarea', min: 8, max: 500 });
      wireForm(form, async data => { await api(`/staff/users/${entry.id}/status`, { method: 'PATCH', body: { is_active: !entry.is_active, reason: data.reason } }); modal.close(); notice('Account status updated.'); await load(); }, 'Confirm account change');
    }));
  } else if (state.staffPanel === 'claims') {
    content.append(badge(entry.status), node('h3', `Claim #${entry.id} · Report #${entry.item_id}`), node('p', entry.evidence, 'staff-evidence'), button('Review report', () => reportDetail(entry.item_id)));
  } else {
    content.append(node('h3', entry.action.replaceAll('_', ' ')), node('p', `${entry.actor_role} #${entry.actor_id ?? 'local'} · ${date(entry.created_at)}`, 'hint'), node('p', [entry.item_id && `Report #${entry.item_id}`, entry.claim_id && `Claim #${entry.claim_id}`, entry.target_user_id && `Account #${entry.target_user_id}`].filter(Boolean).join(' · ')), node('p', entry.details, 'staff-evidence'));
  }
  return card;
}
function reportCard(item) {
  const card = node('button', undefined, 'card'); card.type = 'button'; card.addEventListener('click', () => reportDetail(item.id));
  const art = node('div', undefined, 'card-art ' + item.category); art.append(badge(item.type), node('span', symbols[item.category] || '✳', 'item-symbol')); art.lastChild.setAttribute('aria-hidden', 'true');
  if (item.photo_url) { const image = node('img', undefined, 'report-photo'); image.src = item.photo_url; image.alt = item.title; image.loading = 'lazy'; image.addEventListener('error', () => image.remove(), { once: true }); art.prepend(image); }
  const content = node('div', undefined, 'card-content'); const top = node('div', undefined, 'card-top'); top.append(node('span', item.category, 'category'), badge(item.archived ? 'archived' : item.status));
  const bottom = node('div', undefined, 'card-bottom'); bottom.append(node('span', item.reported_by), node('span', date(item.created_at)));
  content.append(top, node('h3', item.title), node('p', '↳ ' + item.location), bottom); card.append(art, content); return card;
}
function notificationCard(notification) {
  const card = node('div', undefined, 'card notification-card' + (notification.is_read ? '' : ' unread'));
  const content = node('div', undefined, 'card-content');
  content.append(badge(notification.is_read ? 'read' : 'unread'), node('h3', notification.kind.replaceAll('_', ' ')), node('p', notification.message, 'notification-message'), node('p', `${date(notification.created_at)} · Report #${notification.item_id}`, 'hint'));
  const actions = node('div', undefined, 'actions'); content.append(actions);
  actions.append(button('View report', () => reportDetail(notification.item_id)));
  if (!notification.is_read) actions.append(button('Mark as read', async event => {
    const control = event.currentTarget; control.disabled = true;
    try { await api(`/notifications/${notification.id}/read`, { method: 'PATCH' }); await load(); }
    catch (error) { notice(error.message, true); control.disabled = false; }
  }));
  card.append(content); return card;
}
function claimCard(claim) {
  const card = node('div', undefined, 'card'); const content = node('div', undefined, 'card-content');
  content.append(badge(claim.status), node('h3', `Claim #${claim.id} · Report #${claim.item_id}`), node('p', claim.evidence));
  content.append(button('View report', () => reportDetail(claim.item_id)));
  content.append(button('View claim details', () => {
    const body = openModal(`Your claim #${claim.id}`);
    body.append(badge(claim.status), node('p', claim.evidence, 'detail-description'), node('p', `Report #${claim.item_id} · Submitted ${date(claim.created_at)}`, 'hint'), button('View report', () => reportDetail(claim.item_id)));
  }));
  if (['pending', 'approved'].includes(claim.status)) content.append(button('Withdraw claim', () => confirmAction('Withdraw this claim?', 'You can submit a new claim while the item remains available.', async () => { await api(`/claims/${claim.id}/withdraw`, { method: 'POST' }); })));
  card.append(content); return card;
}
function confirmAction(title, message, action) {
  const body = openModal(title); body.append(node('p', message, 'hint'));
  const actions = node('div', undefined, 'actions'); body.append(actions);
  const confirm = button('Confirm', async () => {
    confirm.disabled = true;
    try { await action(); modal.close(); notice('Action completed.'); await load(); }
    catch (error) { notice(error.message, true, true); }
    finally { confirm.disabled = false; }
  }, 'button dark'); actions.append(confirm, button('Cancel', () => modal.close()));
}
async function reportDetail(id) {
  const body = openModal('Report details'); body.append(node('p', 'Loading…', 'hint'));
  const generation = modalGeneration;
  try {
    const item = await api(`/items/${id}`); if (!modal.open || generation !== modalGeneration) return;
    body.replaceChildren(); $('#modal-title').textContent = item.title;
    if (item.photo_url) { const image = node('img', undefined, 'detail-photo'); image.src = item.photo_url; image.alt = item.title; body.append(image); }
    body.append(badge(item.type), document.createTextNode(' '), badge(item.archived ? 'archived' : item.status), node('p', item.description, 'detail-description'), node('p', `${item.location} · ${item.category}\nReported by ${item.reported_by} · ${date(item.created_at)} · Report #${item.id}`, 'detail-meta'));
    const owner = state.user && (state.user.id === item.reporter_id || state.user.role === 'staff');
    const actions = node('div', undefined, 'actions'); body.append(actions);
    if (!item.archived && owner) {
      actions.append(button('Edit report', () => reportForm(item)));
      if (item.photo_url) actions.append(button('Remove photo', () => confirmAction('Remove this photo?', 'The report will remain on the noticeboard without its photo.', () => api(`/items/${id}/photo`, { method: 'DELETE' }))));
      actions.append(button('Mark resolved', () => confirmAction('Resolve this report?', 'Use this for reports without claim history. Found items with claims must be returned through handover.', () => api(`/items/${id}`, { method: 'PATCH', body: { status: 'resolved' } }))));
      actions.append(button('Archive', () => confirmAction('Archive this report?', 'It will leave the main noticeboard. Claim history is kept, and archived reports cannot be edited.', () => api(`/items/${id}/archive`, { method: 'POST' }))));
    }
    if (owner) actions.append(button('Delete report', () => confirmAction('Delete this report?', 'This permanently removes a report without claim history. Reports with claims must be archived instead.', () => api(`/items/${id}`, { method: 'DELETE' })), 'button danger'));
    if (!owner && !item.archived && item.type === 'found' && item.status === 'open' && (!state.user || state.user.role === 'student')) {
      actions.append(button('This might be mine', () => {
        if (!requireAccount()) return;
        const claimBody = openModal('Tell the finder why it’s yours');
        claimBody.append(node('p', 'Share identifying marks or other details only the owner would know. Evidence is visible to you, the finder, and campus staff—not the public.', 'hint'));
        const form = node('form', undefined, 'form-stack'); claimBody.append(form); field(form, 'Private ownership evidence', 'evidence', { type: 'textarea', min: 10, max: 2000 });
        wireForm(form, async data => { await api(`/items/${id}/claims`, { method: 'POST', body: data }); modal.close(); notice('Claim submitted. You can track it in My claims.'); }, 'Submit private claim');
      }, 'button dark'));
    }
    if (owner) {
      body.append(node('hr', undefined, 'divider'), node('h3', 'Private claims'));
      const claimArea = node('div'); body.append(claimArea); await loadReview(item, claimArea);
    }
  } catch (error) { notice(error.message, true, true); }
}
async function loadReview(item, area) {
  let offset = 0;
  const more = button('Load more claims', async () => { more.disabled = true; try { await fetchPage(); } catch (error) { notice(error.message, true, true); more.disabled = false; } });
  async function fetchPage() {
    const claims = await api(`/items/${item.id}/claims?limit=20&offset=${offset}`); more.remove();
    if (!claims.length && offset === 0) area.append(node('p', 'No claims on this report yet.', 'hint'));
    for (const claim of claims) {
      const box = node('div', undefined, 'claim-box'); box.append(badge(claim.status), node('p', `Claim #${claim.id} · Student #${claim.claimant_id} · ${date(claim.created_at)}`, 'hint'), node('p', claim.evidence));
      const actions = node('div', undefined, 'actions'); box.append(actions);
      if (claim.status === 'pending') for (const decision of ['approved', 'rejected']) actions.append(button(decision === 'approved' ? 'Approve claim' : 'Reject claim', () => confirmAction(decision === 'approved' ? 'Approve this claim?' : 'Reject this claim?', decision === 'approved' ? 'Approval reserves the item. Confirm handover only after the physical return.' : 'The claimant will see the rejected status in My claims.', () => api(`/claims/${claim.id}/decision`, { method: 'PATCH', body: { decision } }))));
      if (claim.status === 'approved') actions.append(button('Confirm handover', () => confirmAction('Has the item been returned?', 'Confirm only after returning the item. This completes the claim, resolves the report, and rejects other pending claims.', () => api(`/claims/${claim.id}/handover`, { method: 'POST' })), 'button dark'));
      area.append(box);
    }
    offset += claims.length; if (claims.length === 20) { more.disabled = false; area.append(more); }
  }
  await fetchPage();
}
$('#close-modal').addEventListener('click', () => modal.close());
modal.addEventListener('close', () => { ++modalGeneration; $('#modal-body').replaceChildren(); notice('', false, true); });
$('#login-button').addEventListener('click', () => authForm());
$('#account-button').addEventListener('click', accountForm);
$('#logout-button').addEventListener('click', () => { ++state.generation; state.token = null; state.user = null; setAccount(); modal.close(); notice('You’re signed out.'); state.page = 0; load(); });
$('#new-report').addEventListener('click', () => reportForm());
document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => { state.view = tab.dataset.view; state.page = 0; notice(''); load(); }));
$('#filters').addEventListener('submit', event => { event.preventDefault(); state.page = 0; notice(''); load(); });
$('#filters').addEventListener('reset', () => { state.page = 0; setTimeout(load, 0); });
$('#previous').addEventListener('click', () => { if (state.page > 0) { state.page--; load(); } });
$('#next').addEventListener('click', () => { state.page++; load(); });
$('#refresh-notifications').addEventListener('click', () => { state.page = 0; load(); });
$('#unread-only').addEventListener('change', () => { state.page = 0; load(); });
$('#read-all').addEventListener('click', async event => {
  const control = event.currentTarget; control.disabled = true;
  try { await api('/notifications/read-all', { method: 'POST' }); await load(); }
  catch (error) { notice(error.message, true); }
  finally { control.disabled = false; }
});
setInterval(() => { if (state.user && !document.hidden) refreshNotificationCount(); }, 30000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshNotificationCount(); });
$('#staff-section').addEventListener('change', () => { state.staffPanel = $('#staff-section').value; state.page = 0; load(); });
$('#staff-claim-status').addEventListener('change', () => { state.page = 0; load(); });

initTheme();
setAccount();
load();
api('/auth/config').then(config => { state.accountConfig = config; }).catch(() => notice('Account configuration is unavailable. Please try again later.', true));
function handleAccountLink() {
  const accountLink = new URLSearchParams(location.hash.slice(1));
  const linkPurpose = accountLink.has('verify') ? 'verify' : accountLink.has('reset') ? 'reset' : null;
  if (linkPurpose) { const raw = accountLink.get(linkPurpose); accountLink.delete(linkPurpose); history.replaceState(null, '', location.pathname); accountTokenForm(linkPurpose, raw); }
}
window.addEventListener('hashchange', handleAccountLink);
handleAccountLink();
