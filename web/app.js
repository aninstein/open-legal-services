const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const state = { user: null, csrf: null, authMode: 'login', template: null, conversation: null, draftId: null, draftContent: '', mockSessionId: null, requestSearchSeq: 0, sourceSearchSeq: 0, lawyerSearchSeq: 0, examSearchSeq: 0 };
let toastTimer;

function errorText(error) { return error instanceof Error ? error.message : String(error); }
function showError(id, message) { const el = $(id); el.textContent = message; el.hidden = !message; }
function toast(message) { const el = $('#toast'); el.textContent = message; el.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 4000); }
function empty(title, detail = '') { return `<div class="empty-panel"><strong>${escapeHtml(title)}</strong>${escapeHtml(detail)}</div>`; }
function openDialog(id) { const dialog = $(id); dialog.showModal(); const target = [...dialog.querySelectorAll('input,textarea,select')].find(el => el.getClientRects().length && !el.disabled) || $('button', dialog); if (target) target.focus(); }
function closeDialog(id) { $(id).close(); }

async function api(path, { method = 'GET', body, signal } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (!['GET', 'HEAD'].includes(method) && state.csrf) headers['X-CSRF-Token'] = state.csrf;
  const response = await fetch(`/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin', signal });
  let data = {};
  try { data = await response.json(); } catch { /* no JSON error body */ }
  if (!response.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail) ? detail.map(item => item.msg).join('；') : (typeof detail === 'string' ? detail : `请求失败（${response.status}）`);
    const error = new Error(message); error.status = response.status; throw error;
  }
  return data;
}

function requireLogin() { if (state.user) return true; setAuthMode('login'); openDialog('#authDialog'); toast('请先登录后继续'); return false; }
function clearDocumentChat() {
  state.conversation = null; state.template = null;
  $('#documentChatTitle').textContent = '选一个场景开始';
  $('#documentChatPurpose').textContent = '不需要填表。选定文书后，直接说事实；Agent 会根据这份文书的提示逐步询问。';
  $('#documentChatMessages').innerHTML = '';
  $('#documentChatResult').hidden = true; $('#documentChatResult').innerHTML = '';
  $('#documentChatForm').hidden = true; $('#documentChatInput').value = '';
  showError('#documentChatError', '');
}

function updateAuthUi() {
  $('#authButton').textContent = state.user ? `${state.user.display_name.slice(0,1)}  ${state.user.display_name} ▾` : '登录 / 注册';
  $('#adminMenuButton').hidden = state.user?.role !== 'admin';
  if (!state.user) { $('#accountMenu').hidden = true; $('#authButton').setAttribute('aria-expanded','false'); }
}
async function refreshSession() { const data = await api('/auth/me'); state.user = data.user; state.csrf = data.csrf_token; updateAuthUi(); }

function routeTo(route) {
  const known = ['home','exchange','documents','exam','lawyers','library','inbox','profile','admin'];
  if (!known.includes(route) || (route === 'admin' && state.user?.role !== 'admin') || (route === 'profile' && !state.user)) route = 'home';
  $('#accountMenu').hidden = true; $('#authButton').setAttribute('aria-expanded','false');
  $$('.page').forEach(page => page.classList.toggle('active', page.id === `page-${route}`));
  $$('[data-route]').forEach(link => { const active = link.dataset.route === route; link.classList.toggle('active', active); if (active) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current'); });
  window.scrollTo({ top: 0, behavior: 'auto' });
  if (route === 'exchange') { loadRequests(); if (!$('#minePanel').hidden) loadMyRequests(); }
  if (route === 'documents') { if (!state.user) clearDocumentChat(); loadScenarios(); loadDocumentConversations(); loadDrafts(); loadOfficeTemplates(); loadOfficeFiles(); }
  if (route === 'exam') { loadExam(); loadMockSessions(); loadOfficialUpdates('exam', '#examUpdates'); }
  if (route === 'lawyers') loadLawyers();
  if (route === 'library') { loadSources(); loadOfficialUpdates('', '#libraryUpdates'); }
  if (route === 'inbox') loadConversations();
  if (route === 'admin') loadAdmin();
  if (route === 'profile') loadProfile();
}

function setAuthMode(mode) {
  state.authMode = mode;
  $('#authTitle').textContent = mode === 'login' ? '登录法寻' : '注册法寻';
  $('#authSubmit').textContent = mode === 'login' ? '登录' : '创建账户';
  $('#nameField').hidden = mode === 'login';
  $('#authPassword').autocomplete = mode === 'login' ? 'current-password' : 'new-password';
  $('#showLogin').classList.toggle('active', mode === 'login');
  $('#showRegister').classList.toggle('active', mode === 'register');
  showError('#authError','');
}

$('#authButton').addEventListener('click', async () => {
  if (!state.user) { setAuthMode('login'); openDialog('#authDialog'); return; }
  $('#accountMenu').hidden = !$('#accountMenu').hidden;
  $('#authButton').setAttribute('aria-expanded', String(!$('#accountMenu').hidden));
});
$('#profileMenuButton').addEventListener('click', () => { location.hash = 'profile'; routeTo('profile'); });
$('#adminMenuButton').addEventListener('click', () => { location.hash = 'admin'; routeTo('admin'); });
$('#logoutButton').addEventListener('click', async () => {
  try { await api('/auth/logout', { method: 'POST' }); state.user = null; state.csrf = null; state.mockSessionId = null; state.draftId = null; state.draftContent = ''; clearDocumentChat(); $('#conversationHistory').innerHTML = ''; $('#draftPreview').hidden = true; $('#draftContent').value = ''; $('#draftList').innerHTML = ''; $('#officeFileList').innerHTML = ''; $('#mockSession').innerHTML = ''; $('#mockHistory').innerHTML = ''; updateAuthUi(); location.hash = 'home'; routeTo('home'); toast('已退出登录'); }
  catch (error) { toast(errorText(error)); }
});
document.addEventListener('click', event => { if (!event.target.closest('.account-wrap')) { $('#accountMenu').hidden = true; $('#authButton').setAttribute('aria-expanded','false'); } });
async function loadProfile() {
  if (!state.user) return;
  try { const item = await api('/profile'); $('#profileName').value = item.display_name; $('#profileEmail').value = item.email; $('#profilePhone').value = item.phone || ''; }
  catch(error) { toast(errorText(error)); }
}
$('#profileForm').addEventListener('submit', async event => {
  event.preventDefault(); showError('#profileError','');
  try { const result = await api('/profile',{method:'PUT',body:{display_name:$('#profileName').value.trim(),email:$('#profileEmail').value.trim(),phone:$('#profilePhone').value.trim()}}); state.user = {...state.user,...result}; updateAuthUi(); toast('个人信息已保存'); }
  catch(error) { showError('#profileError',errorText(error)); }
});
$('#passwordForm').addEventListener('submit', async event => {
  event.preventDefault(); showError('#passwordError','');
  try { await api('/profile/password',{method:'PUT',body:{current_password:$('#currentPassword').value,new_password:$('#newPassword').value}}); $('#passwordForm').reset(); toast('密码已更新，其他设备需要重新登录'); }
  catch(error) { showError('#passwordError',errorText(error)); }
});
$('#showLogin').addEventListener('click', () => setAuthMode('login'));
$('#showRegister').addEventListener('click', () => setAuthMode('register'));
$('#authForm').addEventListener('submit', async event => {
  event.preventDefault(); showError('#authError','');
  const email = $('#authEmail').value.trim(); const password = $('#authPassword').value;
  if (!email.includes('@') || password.length < (state.authMode === 'register' ? 12 : 1)) { showError('#authError','请检查邮箱和密码；注册密码至少 12 个字符。'); return; }
  const body = state.authMode === 'register' ? { email, password, display_name: $('#authName').value.trim() } : { email, password };
  const button = $('#authSubmit'); button.disabled = true;
  try {
    const result = await api(`/auth/${state.authMode}`, { method: 'POST', body });
    state.user = result.user; state.csrf = result.csrf_token; updateAuthUi(); closeDialog('#authDialog');
    $('#authPassword').value = ''; toast(state.authMode === 'register' ? '账户已创建' : '已登录');
    routeTo(location.hash.slice(1) || 'home');
  } catch (error) { showError('#authError',errorText(error)); }
  finally { button.disabled = false; }
});
$$('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
$$('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); }));
$('#privacyButton').addEventListener('click', () => openDialog('#privacyDialog'));
window.addEventListener('hashchange', () => routeTo(location.hash.slice(1)));

$('#agentForm').addEventListener('submit', async event => {
  event.preventDefault(); const question = $('#agentInput').value.trim();
  if (question.length < 6) { toast('请至少用 6 个字描述问题'); $('#agentInput').focus(); return; }
  if (!requireLogin()) return;
  const button = $('#agentForm button[type="submit"]'); button.disabled = true; button.textContent = '正在梳理…';
  const answer = $('#agentAnswer'); answer.hidden = false; answer.textContent = '正在查找可核验的来源…';
  try {
    const data = await api('/agent/ask', { method: 'POST', body: { question } });
    answer.innerHTML = `<h3>${data.mode === 'agent' ? 'Agent 梳理' : '来源导航'}</h3><p>${escapeHtml(data.answer)}</p><div class="tagline">${data.sources.map(source => `<a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer" class="soft-tag">${escapeHtml(source.title)} ↗</a>`).join('')}</div><small>目录仅提供来源入口，具体条文与时点请到原站核对。</small>`;
  } catch (error) { answer.innerHTML = `<p class="form-error">${escapeHtml(errorText(error))}</p><small>请稍后重试，或直接使用法律资料页的官方入口。</small>`; }
  finally { button.disabled = false; button.textContent = '开始梳理 ↗'; }
});

function setExchangeTab(which) {
  const mine = which === 'mine'; $('#publicPanel').hidden = mine; $('#minePanel').hidden = !mine;
  $('#publicTab').classList.toggle('active', !mine); $('#mineTab').classList.toggle('active', mine);
  $('#publicTab').setAttribute('aria-selected', String(!mine)); $('#mineTab').setAttribute('aria-selected', String(mine));
  if (mine) loadMyRequests(); else loadRequests();
}
$('#publicTab').addEventListener('click', () => setExchangeTab('public'));
$('#mineTab').addEventListener('click', () => setExchangeTab('mine'));
$$('.tab').forEach(button => button.addEventListener('keydown', event => { if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return; event.preventDefault(); const mine = event.key === 'ArrowRight' || event.key === 'End'; setExchangeTab(mine ? 'mine' : 'public'); $(mine ? '#mineTab' : '#publicTab').focus(); }));

async function loadRequests() {
  const seq = ++state.requestSearchSeq;
  $('#requestList').innerHTML = empty('正在加载求取…');
  const q = $('#requestSearch').value.trim(); const category = $('#requestCategoryFilter').value;
  try {
    const data = await api(`/info-requests?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}`);
    if (seq !== state.requestSearchSeq) return;
    $('#requestList').innerHTML = data.items.length ? data.items.map(item => `<article class="request-card"><div><button class="request-title" data-request="${item.id}">${escapeHtml(item.title)}</button><p>${escapeHtml(item.description)}</p><div class="request-tags"><span class="soft-tag">${escapeHtml(item.category)}</span><span class="soft-tag">${escapeHtml(item.region)}</span>${item.platform_verified ? '<span class="verified-tag">✓ 平台核验</span>' : ''}</div></div><div class="request-side"><div class="reward ${item.reward_cents ? '' : 'free'}">${item.reward_cents ? `¥ ${item.reward_cents/100}<small>报酬意向</small>` : '免费互助'}</div><button class="secondary-button" data-request="${item.id}">查看详情 →</button></div></article>`).join('') : empty('暂无公开求取', q || category ? '调整搜索条件后重试。' : '新的求取经审核后会显示在这里。');
    $$('[data-request]', $('#requestList')).forEach(button => button.addEventListener('click', () => showRequest(button.dataset.request)));
  } catch (error) { if (seq === state.requestSearchSeq) $('#requestList').innerHTML = empty('加载失败',errorText(error)); }
}
async function loadMyRequests() {
  if (!state.user) { $('#myRequestList').innerHTML = empty('登录后查看我的求取'); return; }
  try { const data = await api('/info-requests/mine'); $('#myRequestList').innerHTML = data.items.length ? data.items.map(item => `<article class="request-card"><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.description)}</p><div class="request-tags"><span class="soft-tag">${escapeHtml(item.category)}</span><span class="soft-tag">${escapeHtml(item.region)}</span><span class="soft-tag">${statusLabel(item.status)}</span></div></div><div class="reward ${item.reward_cents ? '' : 'free'}">${item.reward_cents ? `¥ ${item.reward_cents/100}` : '免费互助'}</div></article>`).join('') : empty('还没有发布求取','提交后会进入审核队列。'); }
  catch (error) { $('#myRequestList').innerHTML = empty('加载失败',errorText(error)); }
}
function statusLabel(value) { return ({pending:'待审核',approved:'已公开',rejected:'未通过',closed:'已关闭'})[value] || value; }
async function showRequest(id) {
  try {
    const item = await api(`/info-requests/${id}`); $('#detailTitle').textContent = item.title;
    $('#detailBody').innerHTML = `<p class="detail-summary">${escapeHtml(item.description)}</p><div class="detail-grid"><div>类别<strong>${escapeHtml(item.category)}</strong></div><div>地区<strong>${escapeHtml(item.region)}</strong></div><div>报酬意向<strong>${item.reward_cents ? `¥ ${item.reward_cents/100} · 未托管` : '免费互助'}</strong></div><div>期望日期<strong>${escapeHtml(item.deadline || '未指定')}</strong></div></div><p class="detail-note">请仅提供合法取得、确有权分享的信息。联系和交付会保留在站内。</p><div class="dialog-actions"><button class="primary-button" id="contactRequest">站内联系</button></div>`;
    $('#contactRequest').addEventListener('click', async () => { if (!requireLogin()) return; try { const result = await api(`/info-requests/${id}/conversations`, { method:'POST' }); closeDialog('#detailDialog'); location.hash = 'inbox'; routeTo('inbox'); await openConversation(result.id); } catch (error) { toast(errorText(error)); } });
    openDialog('#detailDialog');
  } catch (error) { toast(errorText(error)); }
}
$('#openRequestForm').addEventListener('click', () => { if (requireLogin()) openDialog('#requestDialog'); });
$('#requestForm').addEventListener('submit', async event => {
  event.preventDefault();
  const body = { title:$('#reqTitle').value.trim(),category:$('#reqCategory').value,region:$('#reqRegion').value.trim(),description:$('#reqDescription').value.trim(),purpose:$('#reqPurpose').value.trim(),reward_yuan:Number($('#reqReward').value),deadline:$('#reqDeadline').value || null };
  if (body.title.length < 5 || body.region.length < 2 || body.description.length < 20 || body.purpose.length < 10 || !Number.isInteger(body.reward_yuan) || body.reward_yuan < 0) { showError('#requestError','请完善标题、地区、至少 20 字的信息说明、至少 10 字的用途，并填写非负整数报酬。'); return; }
  const button = $('#requestForm button[type="submit"]'); button.disabled = true;
  try { await api('/info-requests',{method:'POST',body}); $('#requestForm').reset(); showError('#requestError',''); closeDialog('#requestDialog'); setExchangeTab('mine'); toast('求取已提交审核'); }
  catch (error) { showError('#requestError',errorText(error)); }
  finally { button.disabled = false; }
});

let scenarioCatalog = [];
let selectedScenarioCategory = '';
let scenarioSearchTimer;

async function loadScenarios() {
  try {
    const data = await api('/documents/scenarios'); scenarioCatalog = data.items;
    renderScenarioCategories(); renderScenarios();
  } catch (error) { $('#scenarioList').innerHTML = empty('文书场景加载失败',errorText(error)); }
}
function renderScenarioCategories() {
  const categories = [...new Set(scenarioCatalog.map(item => item.category))];
  $('#scenarioCategories').innerHTML = ['全部',...categories].map(category => `<button type="button" class="scenario-chip ${selectedScenarioCategory === (category === '全部' ? '' : category) ? 'active' : ''}" data-scenario-category="${escapeHtml(category)}">${escapeHtml(category)}</button>`).join('');
  $$('[data-scenario-category]', $('#scenarioCategories')).forEach(button => button.addEventListener('click', () => { selectedScenarioCategory = button.dataset.scenarioCategory === '全部' ? '' : button.dataset.scenarioCategory; renderScenarioCategories(); renderScenarios(); }));
}
function renderScenarios() {
  const q = $('#scenarioSearch').value.trim().toLowerCase();
  const items = scenarioCatalog.filter(item => (!selectedScenarioCategory || item.category === selectedScenarioCategory) && (!q || `${item.title} ${item.purpose} ${item.category} ${item.fields.map(field => field.label).join(' ')}`.toLowerCase().includes(q)));
  $('#scenarioCount').textContent = `${items.length} 个场景`;
  $('#scenarioList').innerHTML = items.length ? items.map(item => `<button type="button" class="scenario-card ${state.template?.id === item.id ? 'active' : ''}" data-scenario="${escapeHtml(item.id)}"><span class="scenario-card-category">${escapeHtml(item.category)}</span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.purpose)}</small><span class="scenario-card-arrow" aria-hidden="true">→</span></button>`).join('') : empty('没有找到对应文书','换个关键词，或告诉 Agent 你的需求。');
  $$('[data-scenario]', $('#scenarioList')).forEach(button => button.addEventListener('click', () => startScenario(button.dataset.scenario)));
}
$('#scenarioSearch').addEventListener('input', () => { clearTimeout(scenarioSearchTimer); scenarioSearchTimer = setTimeout(renderScenarios, 120); });

async function startScenario(id) {
  if (!requireLogin()) return;
  const item = scenarioCatalog.find(entry => entry.id === id); if (!item) return;
  state.template = item; renderScenarios();
  $('#documentChatTitle').textContent = item.title;
  $('#documentChatPurpose').textContent = item.purpose + ' · Agent 将按这份文书的提问提示了解必要信息。';
  $('#documentChatMessages').innerHTML = empty('正在准备对话…');
  try { const conversation = await api('/documents/conversations',{method:'POST',body:{scenario_id:id}}); if (!state.user) return; showDocumentConversation(conversation); loadDocumentConversations(); $('#documentChatInput').focus(); }
  catch(error) { $('#documentChatMessages').innerHTML = empty('对话创建失败',errorText(error)); }
}
function showDocumentConversation(conversation) {
  state.conversation = conversation;
  state.template = scenarioCatalog.find(item => item.id === conversation.scenario_id) || null;
  $('#documentChatTitle').textContent = conversation.title;
  $('#documentChatPurpose').textContent = state.template?.purpose || '请直接说说你的情况。';
  $('#documentChatMessages').innerHTML = conversation.messages.map(message => `<div class="document-chat-message ${message.role === 'user' ? 'from-user' : 'from-agent'}"><span>${message.role === 'user' ? '你' : 'Agent'}</span><p>${escapeHtml(message.content)}</p></div>`).join('');
  $('#documentChatForm').hidden = false;
  const result = $('#documentChatResult'); const fileId = conversation.draft_id || conversation.artifact_id; result.hidden = !fileId;
  const isWord = conversation.kind === 'word';
  const filePath = isWord ? `/api/v1/documents/drafts/${encodeURIComponent(fileId)}` : `/api/v1/office/files/${encodeURIComponent(fileId)}`;
  const format = {word:'Word',excel:'Excel',ppt:'PPT'}[conversation.kind] || '文件';
  result.innerHTML = fileId ? `<strong>${escapeHtml(format)} 文件已生成</strong><a href="${filePath}/download" download>下载 ${escapeHtml(format)} ↓</a><a href="${filePath}/print" target="_blank" rel="noopener noreferrer">打印预览 ↗</a>${isWord ? '<button type="button" id="openConversationDraft">查看并编辑草稿</button>' : ''}` : '';
  $('#openConversationDraft')?.addEventListener('click', () => readDraft(conversation.draft_id));
  $('#documentChatMessages').scrollTop = $('#documentChatMessages').scrollHeight;
  renderScenarios();
}
async function loadDocumentConversations() {
  const ownerId = state.user?.id;
  if (!state.user) { $('#conversationHistory').innerHTML = empty('登录后查看对话'); return; }
  try { const data = await api('/documents/conversations'); if (!state.user || state.user.id !== ownerId) return; $('#conversationHistory').innerHTML = data.items.length ? data.items.map(item => `<div class="compact-row"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.updated_at.slice(0,10))}${item.draft_id || item.artifact_id ? ' · 已生成' : ' · 待补充'}</small><button type="button" data-conversation="${escapeHtml(item.id)}">继续对话 →</button></div>`).join('') : empty('还没有文书对话'); $$('[data-conversation]', $('#conversationHistory')).forEach(button => button.addEventListener('click', () => openDocumentConversation(button.dataset.conversation))); }
  catch(error) { $('#conversationHistory').innerHTML = empty('对话记录加载失败',errorText(error)); }
}
async function openDocumentConversation(id) { try { showDocumentConversation(await api(`/documents/conversations/${encodeURIComponent(id)}`)); $('.document-chat').scrollIntoView({behavior:'smooth',block:'start'}); } catch(error) { toast(errorText(error)); } }
$('#documentChatForm').addEventListener('submit', async event => {
  event.preventDefault(); if (!requireLogin() || !state.conversation) return;
  const body = $('#documentChatInput').value.trim(); if (!body) { showError('#documentChatError','请直接说说你的情况。'); return; }
  const button = $('#documentChatSubmit'); button.disabled = true; button.textContent = 'Agent 正在整理…'; showError('#documentChatError','');
  try { const priorFile = state.conversation.draft_id || state.conversation.artifact_id; const conversation = await api(`/documents/conversations/${encodeURIComponent(state.conversation.id)}/messages`,{method:'POST',body:{body}}); if (!state.user) return; $('#documentChatInput').value = ''; showDocumentConversation(conversation); loadDocumentConversations(); const fileId = conversation.draft_id || conversation.artifact_id; if (fileId) { loadDrafts(); loadOfficeFiles(); if (!priorFile) { const path = conversation.draft_id ? 'documents/drafts' : 'office/files'; window.location.assign(`/api/v1/${path}/${encodeURIComponent(fileId)}/download`); toast('文件已生成并开始下载'); } else toast('文件已按补充信息更新，可重新下载'); } }
  catch(error) { showError('#documentChatError',errorText(error)); }
  finally { button.disabled = false; button.textContent = '发送给 Agent →'; }
});
async function loadDrafts() {
  const ownerId = state.user?.id;
  if (!state.user) { $('#draftList').innerHTML = empty('登录后保存和查看草稿'); return; }
  try { const data = await api('/documents/drafts'); if (!state.user || state.user.id !== ownerId) return; $('#draftList').innerHTML = data.items.length ? data.items.map(item => `<div class="compact-row"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.updated_at.slice(0,10))}</small><button data-draft="${item.id}">查看草稿 →</button></div>`).join('') : empty('还没有草稿'); $$('[data-draft]', $('#draftList')).forEach(button => button.addEventListener('click', () => readDraft(button.dataset.draft))); }
  catch (error) { $('#draftList').innerHTML = empty('加载失败',errorText(error)); }
}
async function readDraft(id) { try { const draft = await api(`/documents/drafts/${id}`); showDraft(draft.id,draft.content); } catch (error) { toast(errorText(error)); } }
function showDraft(id,content) { state.draftId = id; state.draftContent = content; $('#draftContent').value = content; $('#draftPreview').hidden = false; $('#draftPreview').scrollIntoView({behavior:'smooth',block:'start'}); }
async function persistDraft() {
  if (!state.draftId) throw new Error('请先生成草稿');
  const content = $('#draftContent').value;
  if (content === state.draftContent) return;
  const draft = await api(`/documents/drafts/${state.draftId}`,{method:'PUT',body:{content}});
  state.draftContent = draft.content; loadDrafts();
}
$('#saveDraft').addEventListener('click', async () => { const button = $('#saveDraft'); button.disabled = true; try { await persistDraft(); toast('修改已保存'); } catch(error) { toast(errorText(error)); } finally { button.disabled = false; } });
$('#copyDraft').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('#draftContent').value); toast('正文已复制'); } catch { toast('复制失败，请手动选择正文'); } });
$('#downloadDraft').addEventListener('click', async () => { const button = $('#downloadDraft'); button.disabled = true; try { await persistDraft(); window.location.assign(`/api/v1/documents/drafts/${encodeURIComponent(state.draftId)}/download`); toast('Word 文件开始下载'); } catch(error) { toast(errorText(error)); } finally { button.disabled = false; } });
$('#printDraft').addEventListener('click', async () => { const preview = window.open('about:blank','_blank'); const button = $('#printDraft'); button.disabled = true; try { await persistDraft(); if (preview) preview.location.href = `/api/v1/documents/drafts/${encodeURIComponent(state.draftId)}/print`; else toast('浏览器阻止了打印窗口，请允许弹出窗口后重试'); } catch(error) { preview?.close(); toast(errorText(error)); } finally { button.disabled = false; } });

async function loadOfficeTemplates() {
  try {
    const data = await api('/office/templates');
    const label = {word:'Word · DOCX',excel:'Excel · XLSX',ppt:'PPT · PPTX'};
    $('#officeTemplateList').innerHTML = data.items.map(item => `<article class="office-template-card"><span class="office-format ${escapeHtml(item.kind)}">${escapeHtml(label[item.kind])}</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.description)}</p><div class="office-card-actions"><a href="/api/v1/office/templates/${encodeURIComponent(item.id)}/download" download>下载空白模板 ↓</a><a href="/api/v1/office/templates/${encodeURIComponent(item.id)}/print" target="_blank" rel="noopener noreferrer">打印预览 ↗</a>${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">核对官方示范文本 ↗</a>` : ''}</div></article>`).join('');
  } catch (error) { $('#officeTemplateList').innerHTML = empty('模板加载失败',errorText(error)); }
}
async function loadOfficeFiles() {
  const ownerId = state.user?.id;
  if (!state.user) { $('#officeFileList').innerHTML = empty('登录后查看 Office 文件','生成的文件只对你的账户可见。'); return; }
  try {
    const data = await api('/office/files'); if (!state.user || state.user.id !== ownerId) return;
    const label = {word:'Word',excel:'Excel',ppt:'PPT'};
    $('#officeFileList').innerHTML = data.items.length ? data.items.map(item => `<div class="office-file-row"><span class="office-format ${escapeHtml(item.kind)}">${escapeHtml(label[item.kind])}</span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.created_at.slice(0,16).replace('T',' '))}</small><div><a href="/api/v1/office/files/${encodeURIComponent(item.id)}/download" download>下载文件 ↓</a><a href="/api/v1/office/files/${encodeURIComponent(item.id)}/print" target="_blank" rel="noopener noreferrer">打印预览 ↗</a></div></div>`).join('') : empty('还没有 Office 文件','从场景库选择 Excel 或 PPT 文书开始。');
  } catch (error) { $('#officeFileList').innerHTML = empty('文件记录加载失败',errorText(error)); }
}
async function loadExam() {
  const seq = ++state.examSearchSeq; const q = $('#examSearch').value.trim(); const year = $('#examYear').value;
  $('#paperList').innerHTML = empty('正在检索公开试卷…'); $('#questionList').innerHTML = empty('正在检索授权题库…');
  try {
    const [papers, questions] = await Promise.all([api(`/exam/papers?q=${encodeURIComponent(q)}${year ? `&year=${encodeURIComponent(year)}` : ''}`), api(`/exam/questions?q=${encodeURIComponent(q)}${year ? `&year=${encodeURIComponent(year)}` : ''}`)]);
    if (seq !== state.examSearchSeq) return;
    $('#paperList').innerHTML = papers.items.length ? papers.items.map(item => `<article class="library-card exam-paper"><span class="service-icon lilac">✎</span><p class="overline">${item.year} · ${escapeHtml(item.paper_type)}</p><h2>${escapeHtml(item.title)}</h2><p class="source-meta">${escapeHtml(item.authority)} · ${item.rights_status === 'link-only' ? '官方目录元数据 · 仅链接' : '授权题库来源'}</p><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">${item.rights_status === 'link-only' ? '打开官方目录' : '核对题库来源'} ↗</a></article>`).join('') : empty('没有找到公开试卷','试试年份或“国家司法考试”。');
    $('#questionList').innerHTML = questions.items.length ? questions.items.map(item => `<article class="question-card"><p class="overline">${item.year} · ${escapeHtml(item.subject)} · 第 ${escapeHtml(item.question_no)} 题</p><h3>${escapeHtml(item.stem)}</h3>${item.options.length ? `<ul>${item.options.map(option => `<li>${escapeHtml(option)}</li>`).join('')}</ul>` : ''}<p>${item.answer ? `答案：${escapeHtml(item.answer)}` : '未附答案'}${item.explanation ? ` · 解析：${escapeHtml(item.explanation)}` : ''}</p><small>${escapeHtml(item.paper_title)} · 来源与使用权已登记</small><br><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">核对来源 ↗</a></article>`).join('') : empty('暂无可展示的逐题题目','当前只有官方公开试卷入口。导入有明确使用权的题库后，可以按题干、科目和年份搜索。');
  } catch (error) { if (seq === state.examSearchSeq) { $('#paperList').innerHTML = empty('检索失败',errorText(error)); $('#questionList').innerHTML = ''; } }
}

async function loadMockSessions() {
  if (!state.user) { $('#mockHistory').innerHTML = empty('登录后开始模拟练习','练习进度与成绩会保存在你的账户中。'); return; }
  try {
    const data = await api('/exam/mock-sessions');
    $('#mockHistory').innerHTML = data.items.length ? data.items.map(item => `<button class="mock-history-item" type="button" data-mock-id="${escapeHtml(item.id)}"><span><strong>${escapeHtml(item.subject === '随机' ? '随机混合' : item.subject)} · ${item.total_questions} 题</strong><small>${escapeHtml(item.created_at.slice(0,10))} · ${item.status === 'completed' ? '已完成' : `已作答 ${item.answered_count} 题`}</small></span><span>${item.correct_count}/${item.answered_count} 正确 <span aria-hidden="true">→</span></span></button>`).join('') : empty('还没有模拟练习');
    $$('[data-mock-id]', $('#mockHistory')).forEach(button => button.addEventListener('click', () => openMockSession(button.dataset.mockId)));
  } catch (error) { $('#mockHistory').innerHTML = empty('练习记录加载失败',errorText(error)); }
}

function renderMockSession(session) {
  state.mockSessionId = session.id;
  const panel = $('#mockSession'); const question = session.question;
  if (!question) { panel.innerHTML = empty('题目正在生成','请稍后刷新练习记录。'); return; }
  const typeLabel = question.kind === 'single' ? '单选题 · 1 分' : '多选题 · 2 分';
  const inputType = question.kind === 'single' ? 'radio' : 'checkbox';
  const options = Object.entries(question.options).map(([key, value]) => `<label class="mock-option ${question.answered && question.answer_keys.includes(key) ? 'correct' : ''} ${question.answered && question.selected_keys.includes(key) && !question.answer_keys.includes(key) ? 'incorrect' : ''}"><input type="${inputType}" name="mockAnswer" value="${escapeHtml(key)}" ${question.answered ? (question.selected_keys.includes(key) ? 'checked disabled' : 'disabled') : ''}><span class="mock-option-key">${escapeHtml(key)}</span><span>${escapeHtml(value)}</span></label>`).join('');
  const feedback = question.answered ? `<div class="mock-feedback ${question.is_correct ? 'success' : 'needs-review'}"><strong>${question.is_correct ? '回答正确' : '回答错误'} · 正确答案 ${escapeHtml(question.answer_keys.join('、'))}</strong><p>${escapeHtml(question.explanation)}</p><a href="https://flk.npc.gov.cn/search" target="_blank" rel="noopener noreferrer">到国家法律法规数据库核对现行规定 ↗</a></div>` : '';
  const complete = session.status === 'completed' ? `<div class="mock-result"><strong>本组练习完成</strong><span>${session.correct_count} / ${session.total_questions} 题正确 · 已得 ${session.points} / ${session.graded_max_points} 分</span><small>成绩只针对本组 AI 原创练习。</small></div>` : '';
  panel.innerHTML = `<div class="mock-progress"><span>第 ${session.current_position} / ${session.total_questions} 题</span><span>已答对 ${session.correct_count} 题</span></div><div class="mock-question-head"><span class="mock-kind">${typeLabel}</span><span>${escapeHtml(question.subject)} · ${escapeHtml(question.knowledge_point)}</span></div><form id="mockAnswerForm"><fieldset ${question.answered ? 'disabled' : ''}><legend>${escapeHtml(question.stem)}</legend><div class="mock-options">${options}</div></fieldset>${question.answered ? '' : `<div class="mock-actions"><button type="submit" class="primary-button">提交答案并判题</button><small>${question.kind === 'multiple' ? '多选题需选择所有正确选项；漏选或多选均算错。' : '选择一个答案后提交。'}</small></div>`}</form>${feedback}${question.answered && session.status !== 'completed' ? `<button type="button" class="secondary-button mock-next" id="mockNextButton">生成下一题 →</button>` : ''}${complete}`;
  $('#mockAnswerForm')?.addEventListener('submit', submitMockAnswer);
  $('#mockNextButton')?.addEventListener('click', nextMockQuestion);
}

async function openMockSession(id) {
  if (!requireLogin()) return;
  $('#mockSession').innerHTML = empty('正在打开练习…');
  try { const session = await api(`/exam/mock-sessions/${encodeURIComponent(id)}`); renderMockSession(session); $('#mockSession').scrollIntoView({behavior:'smooth',block:'start'}); }
  catch (error) { $('#mockSession').innerHTML = empty('打开练习失败',errorText(error)); }
}

$('#mockStartForm').addEventListener('submit', async event => {
  event.preventDefault(); if (!requireLogin()) return;
  const button = $('#mockStartButton'); button.disabled = true; button.textContent = 'AI 正在出题…';
  $('#mockSession').innerHTML = empty('正在生成原创练习题','通常需要十几秒；首次启动本地模型可能更久。');
  try {
    const session = await api('/exam/mock-sessions', {method:'POST',body:{subject:$('#mockSubject').value,count:Number($('#mockCount').value)}});
    renderMockSession(session); loadMockSessions(); $('#mockSession').scrollIntoView({behavior:'smooth',block:'start'});
  } catch (error) { $('#mockSession').innerHTML = empty('出题失败',errorText(error)); }
  finally { button.disabled = false; button.textContent = '开始模拟练习 →'; }
});

async function submitMockAnswer(event) {
  event.preventDefault();
  const keys = $$('[name="mockAnswer"]:checked', $('#mockAnswerForm')).map(input => input.value);
  if (!keys.length) { toast('请先选择答案'); return; }
  const button = $('#mockAnswerForm button[type="submit"]'); button.disabled = true; button.textContent = '正在判题…';
  try { const session = await api(`/exam/mock-sessions/${encodeURIComponent(state.mockSessionId)}/answer`, {method:'POST',body:{selected_keys:keys}}); renderMockSession(session); loadMockSessions(); }
  catch (error) { toast(errorText(error)); button.disabled = false; button.textContent = '提交答案并判题'; }
}

async function nextMockQuestion() {
  const button = $('#mockNextButton'); button.disabled = true; button.textContent = 'AI 正在出下一题…';
  try { const session = await api(`/exam/mock-sessions/${encodeURIComponent(state.mockSessionId)}/next`, {method:'POST'}); renderMockSession(session); loadMockSessions(); }
  catch (error) { toast(errorText(error)); button.disabled = false; button.textContent = '生成下一题 →'; }
}

async function loadLawyers() {
  const seq = ++state.lawyerSearchSeq; $('#lawyerList').innerHTML = empty('正在加载律师…');
  try { const data = await api(`/lawyers?q=${encodeURIComponent($('#lawyerSearch').value.trim())}`); if (seq !== state.lawyerSearchSeq) return; $('#lawyerList').innerHTML = data.items.length ? data.items.map(item => `<article class="lawyer-card"><div class="lawyer-avatar"><img src="/api/v1/lawyers/${encodeURIComponent(item.user_id)}/portrait" alt="${escapeHtml(item.display_name)}的职业头像" loading="lazy"></div><div class="lawyer-main"><h2>${escapeHtml(item.display_name)} <span class="verified-tag small">✓ 执业信息已核验</span></h2><p>${escapeHtml(item.years)} 年执业 · ${escapeHtml(item.firm)} · ${escapeHtml(item.region)}</p><div class="tagline">${item.specialties.map(area => `<span class="soft-tag">${escapeHtml(area)}</span>`).join('')}</div><p>${escapeHtml(item.bio)}</p>${item.case_summary ? `<p>公开案例：${escapeHtml(item.case_summary)}</p>` : ''}${item.honors ? `<p>荣誉资质：${escapeHtml(item.honors)}</p>` : ''}<small class="source-meta">平台核验时间：${escapeHtml(item.verified_at?.slice(0,10) || '')}</small>${item.verification_source ? `<br><a href="${escapeHtml(item.verification_source)}" target="_blank" rel="noopener noreferrer">查看核验来源 ↗</a>` : ''}${item.social_url ? `<br><a href="${escapeHtml(item.social_url)}" target="_blank" rel="noopener noreferrer">公开社交账号 ↗</a>` : ''}</div></article>`).join('') : empty('暂无已核验律师','新入驻资料经核验后会显示在这里。'); }
  catch (error) { if (seq === state.lawyerSearchSeq) $('#lawyerList').innerHTML = empty('加载失败',errorText(error)); }
}
$('#openLawyerForm').addEventListener('click', async () => {
  if (!requireLogin()) return;
  try { const data = await api('/lawyers/profile/mine'); const profile = data.profile;
    $('#lawyerReviewStatus').hidden = !profile;
    if (profile) $('#lawyerReviewStatus').textContent = `当前认证状态：${{pending:'待审核',verified:'已认证',rejected:'已驳回'}[profile.status] || profile.status}${profile.review_note ? ' · 审核备注：'+profile.review_note : ''}`;
  } catch { $('#lawyerReviewStatus').hidden = true; }
  openDialog('#lawyerDialog');
});
$('#lawyerForm').addEventListener('submit', async event => {
  event.preventDefault(); const body = {license_no:$('#lawyerLicense').value.trim(),firm:$('#lawyerFirm').value.trim(),years:Number($('#lawyerYears').value),region:$('#lawyerRegion').value.trim(),specialties:$('#lawyerAreas').value.split(/[,，]/).map(x=>x.trim()).filter(Boolean),social_url:$('#lawyerSocial').value.trim()||null,bio:$('#lawyerBio').value.trim(),case_summary:$('#lawyerCases').value.trim(),legal_name:$('#lawyerLegalName').value.trim(),gender:$('#lawyerGender').value,id_number:$('#lawyerIdNumber').value.trim(),practice_start:$('#lawyerStart').value,honors:$('#lawyerHonors').value.trim(),contact_phone:$('#lawyerContactPhone').value.trim()};
  if (!body.license_no || !body.firm || !body.region || !$('#lawyerYears').value || !body.specialties.length || body.specialties.length > 5 || body.bio.length < 10 || !body.legal_name || !body.id_number || !body.practice_start || !body.contact_phone) { showError('#lawyerError','请完整填写身份与执业信息，主营业务最多 5 项。'); return; }
  const files = [['portrait','#lawyerPortrait'],['id_front','#lawyerIdFront'],['id_back','#lawyerIdBack'],['license_front','#lawyerLicenseFront'],['license_record','#lawyerLicenseRecord']];
  if (files.some(([,selector]) => !$(selector).files[0])) { showError('#lawyerError','请上传头像、身份证两面和律师执业证两页。'); return; }
  const button = $('#lawyerForm button[type="submit"]'); button.disabled = true;
  try {
    await api('/lawyers/profile/mine',{method:'PUT',body});
    for (const [kind,selector] of files) {
      const data = new FormData(); data.append('file',$(selector).files[0]);
      const response = await fetch(`/api/v1/lawyers/evidence/${kind}`,{method:'POST',headers:{'X-CSRF-Token':state.csrf},body:data,credentials:'same-origin'});
      if (!response.ok) { const detail = await response.json().catch(()=>({})); throw new Error(detail.detail || `上传 ${kind} 失败`); }
    }
    closeDialog('#lawyerDialog'); $('#lawyerForm').reset(); showError('#lawyerError',''); toast('律师资料已提交核验');
  }
  catch (error) { showError('#lawyerError',errorText(error)); } finally { button.disabled = false; }
});

async function loadSources() {
  const seq = ++state.sourceSearchSeq; $('#sourceList').innerHTML = empty('正在加载来源…');
  try { const q = $('#sourceSearch').value.trim(); const kind = $('#sourceKind').value; const data = await api(`/sources?q=${encodeURIComponent(q)}&kind=${encodeURIComponent(kind)}`); if (seq !== state.sourceSearchSeq) return; $('#sourceList').innerHTML = data.items.length ? data.items.map(item => `<article class="library-card"><p class="overline">${escapeHtml(({law:'法律',case:'案例',service:'政务服务',company:'企业公示',lawyer:'律师核验'})[item.kind] || item.kind)}</p><h2>${escapeHtml(item.title)}</h2><p>${escapeHtml(item.summary)}</p><div class="source-meta">${escapeHtml(item.authority)} · 目录核验 ${escapeHtml(item.verified_at.slice(0,10))}</div><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">打开官方来源 ↗</a></article>`).join('') : empty('没有匹配的来源','换个关键词或类型试试。'); }
  catch (error) { if (seq === state.sourceSearchSeq) $('#sourceList').innerHTML = empty('加载失败',errorText(error)); }
}

async function loadOfficialUpdates(kind, selector) {
  $(selector).innerHTML = empty('正在检查官方发布目录…');
  try {
    const data = await api(`/official-updates?kind=${encodeURIComponent(kind)}`);
    const items = kind ? data.items.slice(0,12) : [...data.items.filter(item=>item.kind==='law').slice(0,6),...data.items.filter(item=>item.kind==='case').slice(0,6)];
    $(selector).innerHTML = items.length ? items.map(item => `<article class="library-card"><p class="overline">${item.kind === 'law' ? '法规政策' : item.kind === 'case' ? '公开典型案例' : '法考公告'}</p><h3>${escapeHtml(item.title)}</h3><p class="source-meta">${escapeHtml(item.authority)} · ${item.published_at ? '来源月份 '+escapeHtml(item.published_at) : '收录 '+escapeHtml(item.discovered_at.slice(0,10))}</p><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer">查看官方发布 ↗</a></article>`).join('') : empty('尚未收录最新条目','后台任务将每天检查一次，管理员也可手动同步。');
  } catch(error) { $(selector).innerHTML = empty('更新读取失败',errorText(error)); }
}
$('#companySearchForm').addEventListener('submit', async event => {
  event.preventDefault();
  try { const data = await api(`/companies/search?q=${encodeURIComponent($('#companySearchInput').value.trim())}`); $('#companySearchResult').innerHTML = `<p>${escapeHtml(data.message)}</p><p>检索词：${escapeHtml(data.query)}</p><a href="${escapeHtml(data.source_url)}" target="_blank" rel="noopener noreferrer">打开国家企业信用信息公示系统 ↗</a>`; }
  catch(error) { $('#companySearchResult').textContent = errorText(error); }
});

async function loadConversations() {
  if (!state.user) { $('#conversationList').innerHTML = empty('登录后查看站内消息'); $('#messageList').innerHTML = empty('选择一个会话'); $('#messageForm').hidden = true; return; }
  try { const data = await api('/conversations'); $('#conversationList').innerHTML = data.items.length ? data.items.map(item => `<div class="compact-row"><strong>${escapeHtml(item.request_title)}</strong><small>${escapeHtml(item.created_at.slice(0,10))}</small><button data-conversation="${item.id}">打开会话 →</button></div>`).join('') : empty('暂无站内会话','在公开求取详情中点击“站内联系”。'); $$('[data-conversation]', $('#conversationList')).forEach(button => button.addEventListener('click', () => openConversation(button.dataset.conversation))); if (state.conversation) openConversation(state.conversation); }
  catch (error) { $('#conversationList').innerHTML = empty('加载失败',errorText(error)); }
}
async function openConversation(id) {
  state.conversation = id; $('#messageForm').hidden = false; $('#messageList').innerHTML = empty('正在加载消息…');
  try { const data = await api(`/conversations/${id}/messages`); $('#messageList').innerHTML = data.items.length ? data.items.map(item => `<div class="message-bubble ${item.sender_id === state.user?.id ? 'mine' : ''}">${escapeHtml(item.body)}<small>${escapeHtml(item.created_at.slice(0,16).replace('T',' '))}</small></div>`).join('') : empty('会话已建立','请先说明可以提供的信息及来源。'); }
  catch (error) { $('#messageList').innerHTML = empty('加载失败',errorText(error)); }
}
$('#messageForm').addEventListener('submit', async event => {
  event.preventDefault(); const body = $('#messageText').value.trim(); if (body.length < 10) { toast('消息至少 10 个字'); return; }
  const button = $('#messageForm button[type="submit"]'); button.disabled = true;
  try { await api(`/conversations/${state.conversation}/messages`,{method:'POST',body:{body}}); $('#messageText').value=''; openConversation(state.conversation); toast('消息已发送'); }
  catch (error) { toast(errorText(error)); } finally { button.disabled = false; }
});

async function loadAdmin() {
  if (state.user?.role !== 'admin') return;
  try {
    const [requests, lawyers] = await Promise.all([api('/admin/info-requests'),api('/admin/lawyers')]);
    $('#pendingRequests').innerHTML = requests.items.length ? requests.items.map(item => `<div class="admin-item"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.description)}<br>用途：${escapeHtml(item.purpose)}<br>地区：${escapeHtml(item.region)} · 报酬 ¥${item.reward_cents/100}</p><label class="field-label" for="basis-${item.id}">主体和用途核验依据（可选）</label><input id="basis-${item.id}" class="admin-input" data-basis="${item.id}" placeholder="核对资料及依据，至少 10 个字"><div class="admin-actions"><button class="secondary-button" data-review-request="${item.id}" data-status="approved">仅审核通过</button><button class="secondary-button" data-review-request="${item.id}" data-status="approved" data-verified="true">通过并标记平台核验</button><button class="danger-outline" data-review-request="${item.id}" data-status="rejected">驳回</button></div></div>`).join('') : empty('没有待审求取');
    $('#pendingLawyers').innerHTML = lawyers.items.length ? lawyers.items.map(item => `<div class="admin-item"><strong>${escapeHtml(item.legal_name || '')} · ${escapeHtml(item.firm)}</strong><p>执业证号：${escapeHtml(item.license_no)}<br>身份证号：${escapeHtml(item.id_number || '')} · 联系电话：${escapeHtml(item.contact_phone || '')}<br>地区：${escapeHtml(item.region)} · 开始执业：${escapeHtml(item.practice_start || '')}<br>擅长：${escapeHtml(item.specialties_json)}<br>${escapeHtml(item.bio)}</p><div class="evidence-links">${[['portrait','头像'],['id_front','身份证人像面'],['id_back','身份证国徽面'],['license_front','执业证首页'],['license_record','执业证备案页']].map(([kind,label]) => item.evidence.includes(kind) ? `<a href="/api/v1/lawyers/evidence/${encodeURIComponent(item.user_id)}/${kind}" target="_blank" rel="noopener noreferrer">查看${label}</a>` : `<span class="missing-evidence">缺少${label}</span>`).join('')}</div><label class="field-label" for="lawyer-source-${item.user_id}">执业核验来源</label><input id="lawyer-source-${item.user_id}" class="admin-input" data-lawyer-source="${item.user_id}" placeholder="https://credit.acla.org.cn/..."><input class="admin-input" data-lawyer-note="${item.user_id}" placeholder="审核备注或驳回原因"><div class="admin-actions"><button class="secondary-button" data-review-lawyer="${item.user_id}" data-status="verified">核验通过</button><button class="danger-outline" data-review-lawyer="${item.user_id}" data-status="rejected">驳回</button></div></div>`).join('') : empty('没有待审律师资料');
    $$('[data-review-request]', $('#pendingRequests')).forEach(button => button.addEventListener('click', async () => { const verified = button.dataset.verified === 'true'; const basis = $(`[data-basis="${button.dataset.reviewRequest}"]`).value.trim(); try { await api(`/admin/info-requests/${button.dataset.reviewRequest}`,{method:'PATCH',body:{status:button.dataset.status,platform_verified:verified,verification_basis:basis,note:''}}); toast('审核结果已保存'); loadAdmin(); } catch(error){toast(errorText(error));} }));
    $$('[data-review-lawyer]', $('#pendingLawyers')).forEach(button => button.addEventListener('click', async () => { try { await api(`/admin/lawyers/${button.dataset.reviewLawyer}`,{method:'PATCH',body:{status:button.dataset.status,verification_source:$(`[data-lawyer-source="${button.dataset.reviewLawyer}"]`).value.trim(),note:$(`[data-lawyer-note="${button.dataset.reviewLawyer}"]`).value.trim()}}); toast('核验结果已保存'); loadAdmin(); } catch(error){toast(errorText(error));} }));
  } catch (error) { $('#pendingRequests').innerHTML = empty('加载失败',errorText(error)); }
  loadAdminUsers(); loadAdminConversations(); loadAdminTemplates(); loadSyncStatus();
}

let adminUserOffset = 0;
async function loadAdminUsers(more = false) {
  if (state.user?.role !== 'admin') return;
  if (!more) { adminUserOffset = 0; $('#adminUsers').innerHTML = empty('正在加载用户…'); }
  try {
    const data = await api(`/admin/users?q=${encodeURIComponent($('#adminUserSearch').value.trim())}&offset=${adminUserOffset}&limit=30`);
    const html = data.items.map(item => `<div class="compact-row admin-user-row"><strong>${escapeHtml(item.display_name)}</strong><small>${escapeHtml(item.email)}${item.phone ? ' · '+escapeHtml(item.phone) : ''} · ${item.role === 'admin' ? '管理员' : '普通用户'}</small><button type="button" class="secondary-button" data-role-user="${item.id}" data-role="${item.role === 'admin' ? 'user' : 'admin'}" ${item.id === state.user.id ? 'disabled' : ''}>${item.role === 'admin' ? '撤销管理员' : '设为管理员'}</button></div>`).join('');
    if (more) $('#adminUsers').insertAdjacentHTML('beforeend',html); else $('#adminUsers').innerHTML = html || empty('没有匹配用户');
    adminUserOffset += data.items.length; $('#adminUserMore').hidden = adminUserOffset >= data.total;
    $$('[data-role-user]', $('#adminUsers')).forEach(button => { button.onclick = async () => { try { await api(`/admin/users/${button.dataset.roleUser}/role`,{method:'PATCH',body:{role:button.dataset.role}}); toast('用户角色已更新'); loadAdminUsers(); } catch(error) { toast(errorText(error)); } }; });
  } catch(error) { $('#adminUsers').innerHTML = empty('用户加载失败',errorText(error)); }
}
$('#adminUserMore').addEventListener('click', () => loadAdminUsers(true));
debouncedInput('#adminUserSearch', () => loadAdminUsers());

async function loadAdminConversations() {
  if (state.user?.role !== 'admin') return;
  try { const data = await api(`/admin/conversations?q=${encodeURIComponent($('#adminConversationSearch').value.trim())}`); $('#adminConversations').innerHTML = data.items.length ? data.items.map(item => `<div class="compact-row"><strong>${escapeHtml(item.request_title)}</strong><small>${escapeHtml(item.requester_name)} ↔ ${escapeHtml(item.provider_name)} · ${escapeHtml((item.last_message_at || item.created_at).slice(0,10))}</small><button type="button" data-admin-conversation="${item.id}">查看消息</button></div>`).join('') : empty('没有站内会话'); $$('[data-admin-conversation]', $('#adminConversations')).forEach(button => { button.onclick = async () => { try { const result = await api(`/admin/conversations/${button.dataset.adminConversation}/messages`); $('#adminMessageDetail').innerHTML = `<h3>会话消息</h3>` + (result.items.length ? result.items.map(message => `<div class="admin-message"><strong>${escapeHtml(message.sender_name)}</strong><small>${escapeHtml(message.created_at.slice(0,16))}</small><p>${escapeHtml(message.body)}</p></div>`).join('') : empty('会话尚无消息')); } catch(error) { toast(errorText(error)); } }; }); }
  catch(error) { $('#adminConversations').innerHTML = empty('会话加载失败',errorText(error)); }
}
debouncedInput('#adminConversationSearch',loadAdminConversations);

async function loadAdminTemplates() {
  if (state.user?.role !== 'admin') return;
  try { const data = await api('/admin/document-templates'); $('#adminTemplates').innerHTML = data.items.length ? data.items.map(item => `<div class="compact-row"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.category)} · ${item.active ? '已上架' : '已归档'}</small>${item.active ? `<button type="button" data-archive-template="${item.id}">归档</button>` : ''}</div>`).join('') : empty('还没有手动添加的模板'); $$('[data-archive-template]', $('#adminTemplates')).forEach(button => { button.onclick = async () => { try { await api(`/admin/document-templates/${button.dataset.archiveTemplate}/archive`,{method:'PATCH'}); toast('模板已归档'); loadAdminTemplates(); } catch(error) { toast(errorText(error)); } }; }); }
  catch(error) { $('#adminTemplates').innerHTML = empty('模板加载失败',errorText(error)); }
}
$('#adminTemplateForm').addEventListener('submit', async event => {
  event.preventDefault();
  const levelMap = {'必填':'required','推荐':'recommended','选填':'optional'};
  const lines = $('#templateFields').value.split('\n').map(line=>line.trim()).filter(Boolean);
  const fields = lines.map(line=>{const [key,label,level] = line.split('|').map(x=>x?.trim()); return {key,label,level:levelMap[level] || level};});
  if (fields.some(item=>!item.key||!item.label||!['required','recommended','optional'].includes(item.level))) { toast('字段格式应为：键|名称|必填/推荐/选填'); return; }
  const paragraphs = $('#templateBody').value.split(/\n\s*\n/).map(x=>x.trim()).filter(Boolean);
  try { await api('/admin/document-templates',{method:'POST',body:{category:$('#templateCategory').value.trim(),title:$('#templateTitle').value.trim(),purpose:$('#templatePurpose').value.trim(),fields,paragraphs,source_url:$('#templateSource').value.trim()||null}}); $('#adminTemplateForm').reset(); toast('模板已保存，用户可从文书起草中选择'); loadAdminTemplates(); }
  catch(error) { toast(errorText(error)); }
});

async function loadSyncStatus() {
  try { const data = await api('/official-updates/status'); $('#syncStatus').innerHTML = data.items.length ? data.items.map(item => `<div class="compact-row"><strong>${{law:'法规政策',exam:'法考公告',case:'典型案例'}[item.source_key]}</strong><small>${item.run_day} · ${item.status === 'success' ? `成功，扫描 ${item.item_count} 条` : item.status === 'failed' ? `失败：${escapeHtml(item.error)}` : '运行中'}</small></div>`).join('') : empty('尚未执行更新'); }
  catch(error) { $('#syncStatus').innerHTML = empty('状态读取失败',errorText(error)); }
}
$('#syncNowButton').addEventListener('click', async () => { const button=$('#syncNowButton'); button.disabled=true; button.textContent='检查中…'; try { const data=await api('/admin/official-updates/sync',{method:'POST'}); toast(data.items.some(item=>item.status==='failed')?'部分来源检查失败，请查看状态':'官方目录已更新'); loadSyncStatus(); loadOfficialUpdates('', '#libraryUpdates'); loadOfficialUpdates('exam', '#examUpdates'); } catch(error) { toast(errorText(error)); } finally { button.disabled=false; button.textContent='立即检查更新'; } });

function debouncedInput(inputId, handler, delay = 250) { let timer; let composing = false; const input = $(inputId); input.addEventListener('compositionstart', () => { composing = true; clearTimeout(timer); }); input.addEventListener('input', () => { const clear = $(`[data-clear="${input.id}"]`); if (clear) clear.hidden = !input.value; clearTimeout(timer); if (!composing) timer = setTimeout(handler, delay); }); input.addEventListener('compositionend', () => { composing = false; clearTimeout(timer); handler(); }); }
debouncedInput('#requestSearch',loadRequests); $('#requestCategoryFilter').addEventListener('change',loadRequests);
debouncedInput('#sourceSearch',loadSources); $('#sourceKind').addEventListener('change',loadSources);
debouncedInput('#lawyerSearch',loadLawyers);
debouncedInput('#examSearch',loadExam); $('#examYear').addEventListener('change',loadExam);
$$('[data-clear]').forEach(button => button.addEventListener('click', () => { const input = document.getElementById(button.dataset.clear); input.value = ''; button.hidden = true; input.focus(); input.dispatchEvent(new Event('input')); }));

refreshSession().then(() => routeTo(location.hash.slice(1) || 'home')).catch(error => { updateAuthUi(); routeTo('home'); toast(errorText(error)); });
