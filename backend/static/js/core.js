/* 核心工具：请求、状态、提示 */
window.App = {
  state: {
    // 三种身份：public 普通填报 / leader 寝室长 / admin 已授权管理设备
    mode: 'public',
    isAdmin: false,
    adminEnabled: true,
    adminFirstSetup: false,
    roomId: Number(localStorage.getItem('dorm_room_id') || 0),
    roomNo: localStorage.getItem('dorm_room_no') || '',
    leader: null,
    leaderToken: localStorage.getItem('dorm_leader_token') || '',
    sessionToken: localStorage.getItem('dorm_session_token') || '',
    account: null,
    isAdmin: false,
    submitter: localStorage.getItem('dorm_submitter') || '',
    dorms: [],
    classId: Number(localStorage.getItem('dorm_class_id') || 0),
    classes: [],
    settings: {},
    jobs: [],
    heartbeatTimer: null,
    lastStatus: null,
  },
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
App.$ = $;
App.$$ = $$;

/* ---------------- 寝室选择 ---------------- */
App.setRoom = function setRoom(dormId, roomNo) {
  App.state.roomId = Number(dormId) || 0;
  App.state.roomNo = roomNo || '';
  if (App.state.roomId) localStorage.setItem('dorm_room_id', String(App.state.roomId));
  else localStorage.removeItem('dorm_room_id');
  if (App.state.roomNo) localStorage.setItem('dorm_room_no', App.state.roomNo);
  else localStorage.removeItem('dorm_room_no');
};

App.roomLabel = function roomLabel() {
  if (App.state.leader) return App.state.leader.room_no;
  return App.state.roomNo || '';
};

/* ---------------- 班级切换（多班级管理） ---------------- */
App.setClass = function setClass(id) {
  App.state.classId = Number(id) || 0;
  if (App.state.classId) localStorage.setItem('dorm_class_id', String(App.state.classId));
  else localStorage.removeItem('dorm_class_id');
};

App.classQuery = function classQuery() { return `class_id=${App.state.classId || 0}`; };

App.loadClasses = async function loadClasses() {
  if (!App.state.isAdminPort) { App.state.classes = []; return; }
  try {
    const data = await App.api('/api/classes');
    App.state.classes = data.items || [];
    // 当前选的班级被删了就回第一个
    if (App.state.classes.length && !App.state.classes.some((c) => c.id === App.state.classId)) {
      App.setClass(App.state.classes[0].id);
    }
  } catch (e) { App.state.classes = []; }
};

/* ---------------- 页面注册表 ---------------- */
App.PAGES = {};
App.page = function page(name, config) { App.PAGES[name] = config; };
window.Pages = App.PAGES; // 兼容旧写法

/* ---------------- 时间同步 ---------------- */
App.heartbeat = async function heartbeat(page) {
  try {
    const res = await App.api('/api/auth/ping', 'POST', { page: page || (location.hash || '#/dashboard').replace('#/', '') });
    if (res && res.server_time) App.setServerTime(res.server_time);
  } catch (e) {
    /* 心跳失败静默处理 */
  }
};

/* ---------------- 请求 ---------------- */
App.api = async function api(url, method = 'GET', body = null) {
  const options = { method, headers: App.authHeaders(), credentials: 'same-origin' };
  if (body !== null && body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const res = await fetch(url, options);
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = { message: text }; }
  if (!res.ok) {
    const msg = (data && (data.message || data.detail)) || `请求失败（HTTP ${res.status}）`;
    const error = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    error.status = res.status;
    throw error;
  }
  return data;
};

App.authHeaders = function authHeaders(extra) {
  const headers = Object.assign({}, extra || {});
  if (App.state.submitter) headers['X-Client-Name'] = encodeURIComponent(App.state.submitter);
  if (App.state.leaderToken) headers['X-Leader-Token'] = App.state.leaderToken;
  if (App.state.sessionToken) headers['X-Session-Token'] = App.state.sessionToken;
  return headers;
};

App.saveSession = function saveSession(token) {
  App.state.sessionToken = token || '';
  if (token) localStorage.setItem('dorm_session_token', token);
  else localStorage.removeItem('dorm_session_token');
};

App.login = async function login(username, password, remember) {
  const data = await App.api('/api/auth/login', 'POST', { username, password, remember: remember !== false });
  App.state.account = data.account || null;
  App.state.isAdmin = !!(data.account && data.account.role === 'admin');
  App.saveSession(data.token || '');
  await App.loadClasses(); // 登录后刷新班级列表，供顶部切换器使用
  App.renderChrome();
  location.hash = `#/${App.defaultPage()}`;
  await App.navigate(App.defaultPage());
  return data;
};

App.logout = async function logout() {
  try {
    await App.api('/api/auth/logout', 'POST', {});
  } catch (e) { /* 忽略 */ }
  App.saveSession('');
  App.state.account = null;
  App.state.isAdmin = false;
  App.renderChrome();
  location.hash = '#/login';
  await App.navigate('login');
};

/* 支持用网址带上会话令牌，便于自动截图与联调： /?token=xxx#/console
   注意：只用于本地调试；正式使用请走登录页。 */
App.readTokenFromUrl = function readTokenFromUrl() {
  try {
    const params = new URLSearchParams(location.search);
    const token = params.get('token');
    if (token) {
      App.saveSession(token);
      params.delete('token');
      const query = params.toString();
      const clean = `${location.pathname}${query ? '?' + query : ''}${location.hash}`;
      history.replaceState(null, '', clean);
    }
  } catch (e) { /* 忽略 */ }
};

App.loadSession = async function loadSession() {
  try {
    const data = await App.api('/api/auth/me');
    App.state.account = data.account || null;
    App.state.isAdmin = !!(data.account && data.account.role === 'admin');
    if (!data.logged_in) App.saveSession('');
    return data;
  } catch (e) {
    App.state.account = null;
    App.state.isAdmin = false;
    return { logged_in: false };
  }
};

App.upload = async function upload(url, file, extra = {}) {
  const form = new FormData();
  form.append('file', file);
  Object.keys(extra).forEach((k) => form.append(k, extra[k]));
  const res = await fetch(url, { method: 'POST', body: form, credentials: 'same-origin', headers: App.authHeaders() });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || data.detail || '上传失败');
  return data;
};

App.download = async function download(url, fallbackName = 'download.xlsx') {
  const res = await fetch(url, { credentials: 'same-origin', headers: App.authHeaders() });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.message || `下载失败（HTTP ${res.status}）`);
  }
  const blob = await res.blob();
  let name = fallbackName;
  const disposition = res.headers.get('Content-Disposition') || '';
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  if (utf8) name = decodeURIComponent(utf8[1]);
  else if (plain) name = plain[1];
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.appendChild(link);
  link.click();
  setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 800);
  return name;
};

/* ---------------- 提示 / 弹窗 ---------------- */
App.toast = function toast(message, type = '') {
  const wrap = $('#toastWrap');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  wrap.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(6px)'; }, 2600);
  setTimeout(() => el.remove(), 3100);
};

App.modal = function modal({ title, html, okText = '保存', cancelText = '取消', onOk, wide = false, hideOk = false, showCancel = true, footerExtra = '', onMount }) {
  const mask = $('#modalMask');
  const box = $('#modalBox');
  box.style.maxWidth = wide ? '860px' : '620px';
  box.innerHTML = `
    <h3>${App.esc(title)}</h3>
    <div class="modal-body">${html}</div>
    <div class="modal-foot">
      ${footerExtra}
      ${showCancel ? `<button class="btn" data-act="cancel">${App.esc(cancelText)}</button>` : ''}
      ${hideOk ? '' : `<button class="btn primary" data-act="ok">${App.esc(okText)}</button>`}
    </div>`;
  mask.classList.remove('hidden');
  const close = () => { mask.classList.add('hidden'); box.innerHTML = ''; };
  const cancelBtn = box.querySelector('[data-act="cancel"]');
  if (cancelBtn) cancelBtn.onclick = close;
  const okBtn = box.querySelector('[data-act="ok"]');
  if (okBtn) {
    okBtn.onclick = async () => {
      if (!onOk) return close();
      okBtn.disabled = true;
      try {
        const result = await onOk(box);
        if (result !== false) close();
      } catch (e) {
        App.toast(e.message || '操作失败', 'err');
      } finally {
        okBtn.disabled = false;
      }
    };
  }
  mask.onclick = (event) => { if (event.target === mask) close(); };
  if (typeof onMount === 'function') onMount(box, close);
  return { close, box };
};

App.closeModal = function closeModal() {
  const mask = $('#modalMask');
  if (mask) mask.classList.add('hidden');
  const box = $('#modalBox');
  if (box) box.innerHTML = '';
};

App.confirmBox = function confirmBox(message, onOk, okText = '确定') {  App.modal({
    title: '确认操作',
    html: `<div class="hint-text" style="font-size:13.5px">${App.esc(message)}</div>`,
    okText,
    onOk: async () => { await onOk(); },
  });
};

/* ---------------- 小工具 ---------------- */
App.esc = function esc(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
};

App.attr = (value) => App.esc(value).replace(/\n/g, ' ');

App.today = () => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

App.shiftDate = function shiftDate(days, from) {
  const base = from ? new Date(`${from}T00:00:00`) : new Date();
  base.setDate(base.getDate() + days);
  const pad = (n) => String(n).padStart(2, '0');
  return `${base.getFullYear()}-${pad(base.getMonth() + 1)}-${pad(base.getDate())}`;
};

App.weekday = function weekday(iso) {
  if (!iso) return '';
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return '';
  return '星期' + '日一二三四五六'[d.getDay()];
};

App.bytes = function bytes(size) {
  if (!size) return '0B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = size;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return index === 0 ? `${value}B` : `${value.toFixed(1)}${units[index]}`;
};

App.rateClass = (rate) => (rate >= 95 ? 'ok' : rate >= 80 ? 'warn' : 'bad');

App.progress = function progress(rate, warn = 80) {
  const cls = rate >= warn ? '' : rate >= 60 ? 'warn' : 'bad';
  return `<div class="bar ${cls}"><i style="width:${Math.max(0, Math.min(100, rate))}%"></i></div>`;
};

App.statusChip = function statusChip(text) {
  const map = {
    '齐全': 'ok', '在寝': 'ok', '成功': 'ok', 'success': 'ok', '在线': 'ok',
    '缺人': 'bad', '未填报': 'bad', '失败': 'bad', 'failed': 'bad', '离线': 'gray',
    '未知': 'gray',
  };
  return `<span class="chip ${map[text] || 'gray'}">${App.esc(text)}</span>`;
};

App.field = function field(label, inner, hint, required) {
  return `<label class="field"><span>${App.esc(label)}${required ? ' <b>*</b>' : ''}</span>${inner}${hint ? `<div class="hint-text">${hint}</div>` : ''}</label>`;
};

App.openLink = (url) => window.open(url, '_blank');

App.copy = async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    App.toast('已复制到剪贴板', 'ok');
  } catch (e) {
    App.toast('复制失败，请手动选择文本', 'err');
  }
};

/* ---------------- 端口与界面模式 ---------------- */
// 公开端口（默认 8090）：选寝室 + 填报 + 寝室长界面
// 管理端口（默认 8091）：管理员界面（需要设备授权）
// 公开端口：同学与寝室长用的页面
App.PUBLIC_PAGES = ['home', 'report', 'dashboard', 'stats', 'records'];
// 管理端口：登录后能打开的全部页面
App.ADMIN_PAGES = [
  'overview', 'accounts', 'classes', 'fund', 'console', 'dorms', 'push', 'config',
  'dashboard', 'stats', 'records', 'logs',
];
// 需要登录管理员账号才能打开的页面
App.ADMIN_ONLY_PAGES = ['accounts', 'classes', 'fund', 'console', 'dorms', 'push', 'config', 'logs'];
// 公开端口上不出现的页面（这些只在管理端）
App.HIDDEN_ON_PUBLIC = ['logs', 'accounts', 'fund'];
// 不用登录也能看的页面（登录页）
App.FREE_PAGES = ['login'];
App.publicBase = '';
App.adminBase = '';

/** 公开端地址：用域名访问时返回 https://xiaoaiyun.top，用 IP 时返回 http://IP:8090 */
App.publicUrl = function publicUrl(path) {
  const base = App.publicBase || `${location.protocol}//${location.hostname}:${App.mainPortNumber}`;
  return base.replace(/\/$/, '') + (path || '');
};

/** 管理端地址：用域名访问时返回 https://admin.xiaoaiyun.top，用 IP 时返回 http://IP:8091 */
App.adminUrl = function adminUrl(path) {
  const base = App.adminBase || `${location.protocol}//${location.hostname}:${App.adminPortNumber}`;
  return base.replace(/\/$/, '') + (path || '');
};

App.adminPortNumber = 8091;
App.mainPortNumber = 8090;

/** 系统信息异步加载完后，把页面上显示旧端口的文案刷新成域名 */
App.refreshLinks = function refreshLinks() {
  const chip = document.querySelector('#modeChip');
  if (chip) {
    chip.textContent = App.state.isAdminPort
      ? (App.publicBase ? '管理端（域名）' : 管理员端口 )
      : (App.adminBase ? '公开端（域名）' : 公开端口 );
  }
  const adminLink = document.querySelector('#adminPortLink');
  if (adminLink && App.adminBase) {
    adminLink.textContent = '管理端（域名）';
    adminLink.title = App.adminBase;
  }
  const mainLink = document.querySelector('#mainLink');
  if (mainLink && App.publicBase) {
    const pretty = App.publicBase.replace(/^https?:\/\//, '');
    mainLink.textContent = pretty;
    mainLink.href = App.publicBase + '/';
  }
};

App.loadMode = async function loadMode() {
  try {
    const data = await App.api('/api/system/mode');
    App.state.portMode = data.mode;
    App.state.isAdminPort = !!data.is_admin_port;
    App.state.port = data.port;
    App.mainPortNumber = data.main_port || App.mainPortNumber;
    App.adminPortNumber = data.admin_port || App.adminPortNumber;
    App.publicBase = data.public_base || App.publicBase;
    App.adminBase = data.admin_base || App.adminBase;
    // 系统信息加载完后再刷新一遍页面上的地址文案（登录页比它先渲染）
    App.refreshLinks();
    return data;
  } catch (e) {
    App.state.portMode = 'public';
    App.state.isAdminPort = false;
    return null;
  }
};

App.allowedPages = function allowedPages() {
  return App.state.isAdminPort ? App.ADMIN_PAGES.slice() : App.PUBLIC_PAGES.slice();
};

App.defaultPage = function defaultPage() {
  return App.state.isAdminPort ? 'console' : 'home';
};

/* ---------------- 身份与权限 ---------------- */
App.refreshAccess = async function refreshAccess() {
  try {
    const data = await App.api('/api/access/status');
    App.state.isAdmin = !!data.is_admin;
    App.state.account = data.account || null;
    App.state.leader = data.leader || null;
    App.state.mode = App.state.leader ? 'leader' : (App.state.isAdmin ? 'admin' : 'public');
    if (App.state.leader) App.setRoom(App.state.leader.dorm_id, App.state.leader.room_no);
    App.applyPermission();
    return data;
  } catch (e) {
    App.state.mode = 'public';
    return null;
  }
};

App.updateClient = function updateClient() { /* 兼容旧调用：权限统一由 refreshAccess 处理 */ };

/* 支持用网址直接带上寝室与填表人，例如 /?room=6-213&as=杨朝辉 */
App.readSubmitterFromUrl = function readSubmitterFromUrl() {
  const params = new URLSearchParams(location.search);
  const value = params.get('as') || params.get('name');
  if (value) App.setSubmitter(value);
  const room = params.get('room');
  if (room) {
    const dorm = (App.state.dorms || []).find((item) => item.room_no === room);
    if (dorm) App.setRoom(dorm.id, dorm.room_no);
  }
  return !!value;
};

App.setSubmitter = function setSubmitter(name) {
  const value = String(name || '').trim().slice(0, 40);
  App.state.submitter = value;
  if (value) localStorage.setItem('dorm_submitter', value);
  else localStorage.removeItem('dorm_submitter');
  App.renderSubmitter();
};

App.renderSubmitter = function renderSubmitter() {
  const leader = App.state.leader;
  const chip = $('#submitterChip');
  if (chip) {
    let text = App.state.submitter ? `填表人：${App.state.submitter}` : '填表人：未填写';
    let cls = App.state.submitter ? 'ok' : 'warn';
    if (App.state.isAdmin) {
      const who = (App.state.account && (App.state.account.display_name || App.state.account.username)) || '管理员';
      text = `管理员：${who}`;
      cls = 'ok';
    }
    else if (leader) { text = `寝室长：${leader.room_no}`; cls = 'ok'; }
    chip.textContent = text;
    chip.className = `chip ${cls}`;
    chip.title = (App.state.isAdmin || leader) ? '当前身份' : '点这里填写你是谁（提交时一起记录）';
    chip.style.cursor = 'pointer';
    chip.onclick = () => { if (!App.state.isAdmin && !leader) App.askSubmitter(); };
  }
  const roomEl = $('#whoRoom');
  if (roomEl) roomEl.textContent = App.roomLabel() || '未选择';
  const side = $('#whoSubmitter');
  if (side) side.textContent = App.state.submitter || '未填写';
  // 左侧身份文字统一由 App.renderChrome 负责
};

App.askSubmitter = function askSubmitter(after) {
  App.modal({
    title: '填表人',
    okText: '保存',
    html: `
      <div class="hint-text">不需要账号，填一下你的名字（或宿舍号）就行，提交时会记进填报记录和操作日志，方便老师知道是谁报的。</div>
      ${App.field('我的名字 / 宿舍号', `<input id="submitterInput" value="${App.attr(App.state.submitter)}" placeholder="例如：6-213 杨朝辉">`)}
      <div class="hint-text">留空也能提交，会记为“匿名填报”。</div>`,
    onMount: (box) => {
      setTimeout(() => { const el = box.querySelector('#submitterInput'); if (el) el.focus(); }, 50);
    },
    onOk: async (box) => {
      App.setSubmitter(box.querySelector('#submitterInput').value);
      App.toast(App.state.submitter ? `已记录填表人：${App.state.submitter}` : '已清空填表人，将记为匿名填报', 'ok');
      if (typeof after === 'function') await after();
      return true;
    },
  });
};

/* 寝室长验证 */
App.showLeaderVerify = function showLeaderVerify(after) {
  App.modal({
    title: '寝室长验证',
    okText: '验证',
    html: `
      <div class="hint-text">寝室长输入宿舍号和密码。密码由生活委员在「管理控制台」生成或重置；不知道密码就直接用普通填报，一样能提交。</div>
      ${App.field('宿舍号', `<input id="leaderRoom" value="${App.attr(App.state.roomNo)}" placeholder="例如 6-213">`, '', true)}
      ${App.field('密码', `<input id="leaderPass" type="password" placeholder="例如 428315">`, '', true)}
      <div id="leaderErr" class="hint-text" style="color:#dc2626"></div>`,
    onMount: (box) => {
      setTimeout(() => { const el = box.querySelector('#leaderRoom'); if (el) el.focus(); }, 60);
    },
    onOk: async (box) => {
      const roomNo = box.querySelector('#leaderRoom').value.trim();
      const password = box.querySelector('#leaderPass').value;
      if (!roomNo || !password) { box.querySelector('#leaderErr').textContent = '请填写宿舍号和密码'; return false; }
      try {
        const res = await App.api('/api/access/leader/login', 'POST', { room_no: roomNo, password });
        App.state.leaderToken = res.token;
        App.state.leader = res.dorm;
        localStorage.setItem('dorm_leader_token', res.token);
        App.setRoom(res.dorm.id, res.dorm.room_no);
        App.setSubmitter(res.dorm.leader_name || res.dorm.room_no);
        await App.refreshAccess();
        App.toast(res.message || '验证成功', 'ok');
        if (typeof after === 'function') await after();
        return true;
      } catch (e) {
        box.querySelector('#leaderErr').textContent = e.message;
        return false;
      }
    },
  });
};

App.leaderLogout = async function leaderLogout() {
  App.state.leaderToken = '';
  App.state.leader = null;
  localStorage.removeItem('dorm_leader_token');
  await App.refreshAccess();
  App.toast('已退出寝室长身份，回到普通填报', 'ok');
};

/* 管理员登录（弹窗形式；管理端口有独立登录页） */
App.showAdminEntry = function showAdminEntry(after) {
  App.modal({
    title: '管理员登录',
    okText: '登录',
    html: `
      <div class="hint-text">用管理员账号登录。没有账号就找生活委员在「账号管理」里给你建一个。</div>
      ${App.field('账号', '<input id="adminUser" placeholder="例如 admin">', '', true)}
      ${App.field('密码', '<input id="adminPass" type="password">', '', true)}
      <div id="adminErr" class="hint-text" style="color:#dc2626"></div>`,
    onMount: (box) => {
      setTimeout(() => { const el = box.querySelector('#adminUser'); if (el) el.focus(); }, 60);
    },
    onOk: async (box) => {
      const username = box.querySelector('#adminUser').value.trim();
      const password = box.querySelector('#adminPass').value;
      if (!username || !password) { box.querySelector('#adminErr').textContent = '请填写账号和密码'; return false; }
      try {
        const res = await App.login(username, password);
        App.toast(res.message || '登录成功', 'ok');
        if (typeof after === 'function') await after();
        return true;
      } catch (e) {
        box.querySelector('#adminErr').textContent = e.message;
        return false;
      }
    },
  });
};

/* 改自己的密码 */
App.showChangePassword = function showChangePassword() {
  const account = App.state.account || {};
  App.modal({
    title: '修改密码',
    okText: '保存新密码',
    html: `
      <div class="hint-text">正在修改账号 <b>${App.esc(account.username || '')}</b> 的登录密码。</div>
      ${App.field('原密码', '<input id="pwdOld" type="password">', '', true)}
      ${App.field('新密码（至少 6 位）', '<input id="pwdNew" type="password">', '', true)}
      ${App.field('再输一次新密码', '<input id="pwdNew2" type="password">', '', true)}
      <div id="pwdErr" class="hint-text" style="color:#dc2626"></div>`,
    onMount: (box) => setTimeout(() => { const el = box.querySelector('#pwdOld'); if (el) el.focus(); }, 60),
    onOk: async (box) => {
      const oldPassword = box.querySelector('#pwdOld').value;
      const newPassword = box.querySelector('#pwdNew').value;
      const again = box.querySelector('#pwdNew2').value;
      const err = box.querySelector('#pwdErr');
      if (newPassword.length < 6) { err.textContent = '新密码至少 6 位'; return false; }
      if (newPassword !== again) { err.textContent = '两次输入的新密码不一致'; return false; }
      try {
        const res = await App.api('/api/auth/password', 'POST', { old_password: oldPassword, new_password: newPassword });
        App.toast(res.message || '密码已修改', 'ok');
        return true;
      } catch (e) {
        err.textContent = e.message;
        return false;
      }
    },
  });
};

/* 管理员给别的账号直接指定密码 */
App.showSetAccountPassword = function showSetAccountPassword(username, accountId, after) {
  App.modal({
    title: `给 ${username} 设置密码`,
    okText: '保存密码',
    html: `
      <div class="hint-text">直接给这个账号定一个新密码，保存后他就能用新密码登录。</div>
      ${App.field('新密码（至少 6 位）', '<input id="setPwd1" type="password">', '', true)}
      ${App.field('再输一次', '<input id="setPwd2" type="password">', '', true)}
      <div class="hint-text">不确定的话也可以点「随机重置」生成一个 6 位数字，然后复制发给他。</div>
      <div id="setPwdErr" class="hint-text" style="color:#dc2626"></div>`,
    onMount: (box) => setTimeout(() => { const el = box.querySelector('#setPwd1'); if (el) el.focus(); }, 60),
    onOk: async (box) => {
      const first = box.querySelector('#setPwd1').value;
      const second = box.querySelector('#setPwd2').value;
      const err = box.querySelector('#setPwdErr');
      if (first.length < 6) { err.textContent = '密码至少 6 位'; return false; }
      if (first !== second) { err.textContent = '两次输入的密码不一致'; return false; }
      try {
        const res = await App.api(`/api/accounts/${accountId}/password`, 'POST', { new_password: first });
        App.toast(`已设置 ${username} 的新密码：${res.password}`, 'ok');
        if (typeof after === 'function') await after();
        return true;
      } catch (e) {
        err.textContent = e.message;
        return false;
      }
    },
  });
};

/* 显示生成好的密码/凭据，方便复制发出去 */
App.showResetCredential = function showResetCredential(res, kind, title) {
  if (kind === 'batch') {
    const items = res.items || [];
    const text = items.map((i) => `${i.room_no}\t${i.username}\t${i.password}`).join('\n');
    App.modal({
      title: `已创建 ${items.length} 个寝室长账号`,
      hideOk: true,
      cancelText: '关闭',
      html: `<div class="hint-text">复制下面的清单发到各宿舍群（宿舍号 / 账号 / 密码）：</div>
        <div class="logbox" style="white-space:pre-wrap">${App.esc(text || '（没有新建）')}</div>
        <div style="margin-top:10px"><button class="btn tiny primary" id="btnCopyBatch">复制全部</button></div>`,
      onMount: (box) => {
        box.querySelector('#btnCopyBatch').onclick = () => App.copy(text);
      },
    });
    return;
  }
  const password = res.password || '';
  const username = res.username || res.room_no || '';
  if (!password) {
    App.toast(res.message || '操作完成', 'ok');
    return;
  }
  const text = `填报网址：${location.origin}
账号：${username}
密码：${password}`;
  App.modal({
    title: title || '账号密码',
    hideOk: true,
    cancelText: '关闭',
    html: `<div class="hint-text">把下面这几行发给他（打开网址 →「我是寝室长（登录）」→ 输入账号和密码）：</div>
      <div class="logbox" style="white-space:pre-wrap">${App.esc(text)}</div>
      <div style="margin-top:10px"><button class="btn tiny primary" id="btnCopyCred">复制</button></div>`,
    onMount: (box) => {
      box.querySelector('#btnCopyCred').onclick = () => App.copy(text);
    },
  });
};

App.applyPermission = function applyPermission() {
  const admin = !!App.state.isAdmin;
  $$('[data-admin-only]').forEach((el) => el.classList.toggle('hidden', !admin));
  App.renderSubmitter();
};

// 兼容旧调用
App.canEdit = () => !!App.state.isAdmin;
App.canReport = () => true;

App.setServerTime = function setServerTime(text) {
  const el = $('#serverTime');
  if (el) el.textContent = `服务器时间 ${text}`;
};

/* ---------------- 图表辅助 ---------------- */
App.chartColors = ['#1f6feb', '#16a34a', '#d97706', '#dc2626', '#7c3aed', '#0891b2'];

App.lineChart = function lineChart(canvas, labels, series, options = {}) {
  if (!canvas || !window.Chart) return null;
  if (canvas._chart) canvas._chart.destroy();
  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: options.type || 'line',
    data: {
      labels,
      datasets: series.map((item, index) => ({
        label: item.label,
        data: item.data,
        borderColor: item.color || App.chartColors[index % App.chartColors.length],
        backgroundColor: item.fill === false ? 'transparent' : `${(item.color || App.chartColors[index % App.chartColors.length])}22`,
        borderWidth: 2,
        tension: 0.32,
        fill: item.fill !== false,
        pointRadius: 3,
        pointHoverRadius: 5,
        yAxisID: item.yAxisID || 'y',
        type: item.type,
        borderRadius: 6,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: series.length > 1, position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } },
        tooltip: { padding: 10, cornerRadius: 8 },
      },
      scales: {
        y: {
          beginAtZero: true,
          suggestedMax: options.maxY,
          grid: { color: '#eef2f8' },
          ticks: { precision: 0, font: { size: 11 } },
        },
        y1: {
          beginAtZero: true,
          position: 'right',
          grid: { display: false },
          ticks: { precision: 0, font: { size: 11 } },
          display: !!options.hasY1,
        },
        x: { grid: { display: false }, ticks: { font: { size: 11 } } },
      },
    },
  });
  return canvas._chart;
};

App.barChart = function barChart(canvas, labels, values, options = {}) {
  return App.lineChart(canvas, labels, [{
    label: options.label || '数量',
    data: values,
    color: options.color || '#1f6feb',
    type: 'bar',
    fill: false,
  }], { type: 'bar' });
};

App.donutChart = function donutChart(canvas, labels, values, colors) {
  if (!canvas || !window.Chart) return null;
  if (canvas._chart) canvas._chart.destroy();
  canvas._chart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors || ['#16a34a', '#dc2626', '#cbd5e1'],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } } },
    },
  });
  return canvas._chart;
};
