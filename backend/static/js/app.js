/* 路由与全局生命周期 */
const Pages = App.PAGES;

App.PAGE_META = {
  login: ['管理员登录', '用管理员账号登录管理端'],
  overview: ['总览', '今晚填报、班费、系统状态一屏看完'],
  home: ['选择寝室', '点一下自己的寝室，直接进入填写'],
  report: ['每日填报', '勾选每人是否在寝，提交即可'],
  dashboard: ['数据看板', '今晚的填报情况一目了然'],
  stats: ['统计图表', '按天 / 周 / 月查看填报与缺勤趋势'],
  records: ['填报记录', '按日期查看和导出历史填报'],
  logs: ['填写日志', '谁在什么时间、用什么设备、从哪个 IP 提交的'],
  accounts: ['账号管理', '添加管理员账号、管理寝室长账号'],
  fund: ['班费管理', '统计、明细编辑、导入导出、发班级群'],
  console: ['管理控制台', '寝室长密码、数据总览'],
  dorms: ['宿舍与人员', '导入、添加、编辑、删除人员信息'],
  classes: ['班级管理', '多班级管理：每个班级独立的数据、群绑定、提醒'],
  push: ['提醒推送', 'QQ 官方机器人汇报与定时提醒'],
  config: ['系统配置', '全部参数图形化修改'],
};

App.currentPage = 'home';

App.navigate = async function navigate(name) {
  // 允许 #/config/qqbot 这种二级路径：只取第一段当页面名，其余留给页面自己读
  name = String(name || '').split('/')[0] || App.defaultPage();
  const allowed = App.allowedPages().filter((page) => {
    if (!App.state.isAdminPort && App.HIDDEN_ON_PUBLIC.includes(page)) return false;
    if (App.ADMIN_ONLY_PAGES.includes(page) && !App.state.isAdmin) return false;
    return true;
  });
  if (!allowed.includes(name)) {
    if (!App.PAGE_META[name]) name = App.defaultPage();
    else {
      App.toast(
        App.state.isAdminPort
          ? '这是管理员端口，只提供管理界面'
          : `同学和寝室长请用 ${App.publicUrl('/')} 访问`,
        'err',
      );
      name = App.defaultPage();
    }
  }
  if (App.ADMIN_ONLY_PAGES.includes(name) && !App.state.isAdmin) {
    App.toast('请先登录管理员账号', 'err');
    name = 'login';
  }
  App.currentPage = name;
  $$('.nav-item').forEach((el) => el.classList.toggle('active', el.dataset.page === name));
  const meta = App.PAGE_META[name];
  $('#pageTitle').textContent = meta[0];
  $('#pageSub').textContent = meta[1];
  $('#sidebar').classList.remove('open');
  $('#sidebarMask').classList.remove('show');
  const container = $('#page');
  container.innerHTML = '<div class="card"><div class="empty">加载中…</div></div>';
  const pageConfig = Pages[name];
  if (!pageConfig) { container.innerHTML = '<div class="card"><div class="empty">页面不存在</div></div>'; return; }
  try {
    await pageConfig.render(container);
  } catch (e) {
    container.innerHTML = `<div class="card"><div class="empty">加载失败：${App.esc(e.message || e)}</div></div>`;
  }
  App.applyPermission();
  App.renderChrome();
  App.heartbeat(name);
};

App.reloadCurrent = async function reloadCurrent() {
  const pageConfig = Pages[App.currentPage];
  if (!pageConfig) return;
  const container = $('#page');
  try {
    await pageConfig.render(container);
    App.applyPermission();
  } catch (e) {
    App.toast(e.message || '刷新失败', 'err');
  }
};

App.loadBase = async function loadBase() {
  try {
    const info = await App.api('/api/system/info');
    App.state.system = info;
    const brand = $('#brandSub');
    if (brand && info.settings) brand.textContent = `汇报 ${info.settings.qq_report_time}`;
    document.title = `${info.app} v${info.version}`;
    if (info.server_time) App.setServerTime(info.server_time);
  } catch (e) { /* 忽略 */ }
  try {
    // class_id=-1：拿全部班级的宿舍，公开端选寝室页按班级分组展示
    const dorms = await App.api('/api/dorms?with_members=false&active_only=false&class_id=-1');
    App.state.dorms = dorms.items || [];
  } catch (e) { App.state.dorms = []; }
  try {
    const settings = await App.api('/api/settings');
    App.state.settings = settings.values || {};
    App.state.jobs = settings.jobs || [];
    App.state.templateVars = settings.template_vars || {};
  } catch (e) { /* 忽略 */ }
  await App.loadClasses();
};

/* 按端口/身份调整左侧菜单和底部按钮 */
App.renderChrome = function renderChrome() {
  const adminMode = !!App.state.isAdminPort;
  const leader = App.state.leader;
  $$('.nav-item').forEach((el) => {
    const page = el.dataset.page;
    let show = adminMode ? App.ADMIN_PAGES.includes(page) : App.PUBLIC_PAGES.includes(page);
    if (!adminMode && App.HIDDEN_ON_PUBLIC.includes(page)) show = false;
    if (adminMode && App.ADMIN_ONLY_PAGES.includes(page) && !App.state.isAdmin) show = false;
    if (!adminMode && leader && ['dashboard', 'stats', 'records'].includes(page)) show = false;
    if (!adminMode && page === 'home' && leader) show = false;
    el.classList.toggle('hidden', !show);
  });
  $('#portBadge').textContent = adminMode
    ? (App.publicBase ? '管理端（域名访问）' : `管理员端口 ${App.adminPortNumber}`)
    : (App.adminBase ? '公开端（域名访问）' : `公开端口 ${App.mainPortNumber}`);
  $('#portBadge').className = `chip ${adminMode ? 'gray' : 'ok'}`;
  // 班级切换器：只在管理端且已登录时显示
  const classSwitcher = $('#classSwitcher');
  if (classSwitcher) {
    const showSwitcher = adminMode && App.state.isAdmin;
    classSwitcher.classList.toggle('hidden', !showSwitcher);
    if (showSwitcher) {
      const items = App.state.classes || [];
      const options = items.length
        ? items.map((c) => `<option value="${c.id}">${App.esc(c.name)}</option>`).join('')
        : '<option value="0">默认班级</option>';
      // renderChrome 会被反复调用：内容没变就不重填，保证幂等
      if (classSwitcher.dataset.options !== options) {
        classSwitcher.innerHTML = options;
        classSwitcher.dataset.options = options;
      }
      classSwitcher.value = String(App.state.classId || 0);
    }
  }
  const box = $('#whoBox');
  if (box) {
    const avatar = box.querySelector('.avatar');
    const roleEl = $('#whoRole');
    if (adminMode && App.state.isAdmin) {
      if (avatar) avatar.textContent = '🔐';
      roleEl.textContent = `管理员 · ${(App.state.account && App.state.account.display_name) || 'admin'}`;
    } else if (adminMode) {
      if (avatar) avatar.textContent = '🔒';
      roleEl.textContent = '未登录';
    } else if (leader) {
      if (avatar) avatar.textContent = '🧑‍🎓';
      roleEl.textContent = `寝室长 · ${leader.room_no}`;
    } else {
      if (avatar) avatar.textContent = '🏠';
      roleEl.textContent = '普通填报';
    }
  }
  // 底部按钮：按端口和身份显示
  const show = (sel, visible) => { const el = $(sel); if (el) el.classList.toggle('hidden', !visible); };
  // 公开端口不出现任何管理入口（管理员一律走管理端口）
  show('#btnSwitchRoom', !adminMode && !leader);
  show('#btnLeaderVerify', !adminMode && !leader);
  show('#btnLeaderExit', !adminMode && !!leader);
  show('#btnAdminEnter', false);
  show('#btnAdminExit', adminMode && App.state.isAdmin);
  show('#btnChangePwd', adminMode && App.state.isAdmin);
  show('#adminPortLink', !adminMode);
  show('#mainPortLink', adminMode);
  const adminLink = $('#adminPortLink');
  if (adminLink) adminLink.textContent = App.publicBase ? '管理端（域名）' : `管理端 :${App.adminPortNumber}`;
  if (adminLink && App.adminBase) adminLink.title = App.adminBase;
  const mainLink = $('#mainPortLink');
  if (mainLink) mainLink.textContent = App.adminBase ? '填报端（域名）' : `填报端 :${App.mainPortNumber}`;
};

App.exitAdmin = async function exitAdmin() {
  App.confirmBox('退出登录？下次进管理端需要重新输入账号密码。', async () => {
    await App.logout();
  }, '退出登录');
};

App.init = async function init() {
  App.readTokenFromUrl();
  await App.loadMode();
  App.readSubmitterFromUrl();
  await App.loadBase();
  await App.loadSession();
  await App.refreshAccess();
  App.readSubmitterFromUrl();

  const hash = (location.hash || '').replace('#/', '').split('/')[0];
  const allowed = App.allowedPages().filter((page) => {
    if (!App.state.isAdminPort && App.HIDDEN_ON_PUBLIC.includes(page)) return false;
    if (App.ADMIN_ONLY_PAGES.includes(page) && !App.state.isAdmin) return false;
    return true;
  });
  let first;
  if (App.state.isAdminPort && !App.state.isAdmin) {
    // 管理端口没登录 → 一律先去登录页
    first = 'login';
  } else if (hash && allowed.includes(hash)) {
    first = hash;
  } else {
    first = App.defaultPage();
  }
  await App.navigate(first);
  App.renderChrome();

  // 首次登录给的密码是随机生成的，提示去改
  if (App.state.isAdmin && App.state.account && App.state.account.must_change) {
    setTimeout(() => App.toast('这是系统生成的初始密码，建议到「账号管理 → 修改密码」改一个自己好记的', 'warn'), 800);
  }

  window.addEventListener('hashchange', () => {
    const name = (location.hash || '').replace('#/', '').split('/')[0];
    if (name !== App.currentPage) App.navigate(name);
  });

  $('#btnMenu').onclick = () => {
    $('#sidebar').classList.toggle('open');
    $('#sidebarMask').classList.toggle('show');
  };
  $('#sidebarMask').onclick = () => {
    $('#sidebar').classList.remove('open');
    $('#sidebarMask').classList.remove('show');
  };
  $('#btnRefresh').onclick = () => App.reloadCurrent();
  $('#btnSwitchRoom').onclick = async () => { location.hash = '#/home'; await App.navigate('home'); };
  $('#btnLeaderVerify').onclick = () => App.showLeaderVerify(async () => {
    App.renderChrome();
    location.hash = '#/report';
    await App.navigate('report');
  });
  $('#btnLeaderExit').onclick = async () => {
    await App.leaderLogout();
    App.renderChrome();
    location.hash = '#/home';
    await App.navigate('home');
  };
  $('#btnAdminEnter').onclick = () => {
    const url = App.adminUrl('/');
    window.open(url, '_blank');
  };
  $('#btnAdminExit').onclick = () => App.logout();
  $('#btnChangePwd').onclick = () => App.showChangePassword();
  $('#classSwitcher').onchange = async () => {
    App.setClass($('#classSwitcher').value);
    App.renderChrome();
    await App.reloadCurrent();
  };
  $('#adminPortLink').onclick = () => {
    const url = App.adminUrl('/');
    App.copy(url);
    window.open(url, '_blank');
  };
  $('#mainPortLink').onclick = () => {
    const url = App.publicUrl('/');
    App.copy(url);
    window.open(url, '_blank');
  };
  $('#whoBox').onclick = () => { if (!App.state.isAdmin && !App.state.leader) App.askSubmitter(); };

  App.applyPermission();
  App.heartbeat(App.currentPage);
  if (App.state.heartbeatTimer) clearInterval(App.state.heartbeatTimer);
  App.state.heartbeatTimer = setInterval(() => App.heartbeat(App.currentPage), 60000);
};

document.addEventListener('DOMContentLoaded', App.init);
