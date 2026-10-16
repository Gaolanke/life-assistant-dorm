/* 管理员登录（管理端口） */
App.page('login', {
  async render(box) {
    const info = App.state.loginInfo || {};
    box.innerHTML = `
      <div class="login-wrap">
        <div class="login-card">
          <div class="login-head">
            <div class="logo">🛏️</div>
            <h2>生活助手 · 管理端</h2>
            <p>请用管理员账号登录</p>
          </div>
          <form id="loginForm" autocomplete="on">
            ${App.field('账号', `<input id="loginUser" name="username" autocomplete="username" placeholder="管理员账号，例如 admin">`)}
            ${App.field('密码', `<input id="loginPass" name="password" type="password" autocomplete="current-password" placeholder="密码">`)}
            <label class="login-remember"><input type="checkbox" id="loginRemember" checked> 记住我（30 天内免登录）</label>
            <div class="login-error hidden" id="loginError"></div>
            <button class="btn primary block" id="loginBtn" type="submit">登录</button>
          </form>
          <div class="login-foot">
            <span>填报端入口：<a id="loginMainLink" href="#" target="_blank">—</a></span>
          </div>
        </div>
      </div>`;

    const mainLink = $(`#loginMainLink`);
      mainLink.href = App.publicUrl('/');
    mainLink.textContent = App.publicBase ? App.publicBase.replace(/^https?:\/\//, '') : `${location.hostname}:${App.mainPortNumber}`;

    const showError = (message) => {
      const el = $('#loginError');
      el.textContent = message;
      el.classList.remove('hidden');
    };

    const doLogin = async () => {
      const username = $('#loginUser').value.trim();
      const password = $('#loginPass').value;
      const btn = $('#loginBtn');
      if (!username || !password) {
        showError('请填写账号和密码');
        return;
      }
      btn.disabled = true;
      btn.textContent = '登录中…';
      try {
        const res = await App.login(username, password, $('#loginRemember').checked);
        App.toast(res.message || '登录成功', 'ok');
      } catch (e) {
        showError(e.message || '登录失败');
        btn.disabled = false;
        btn.textContent = '登录';
      }
    };

    $('#loginForm').onsubmit = (event) => {
      event.preventDefault();
      doLogin();
    };
    setTimeout(() => { const el = $('#loginUser'); if (el) el.focus(); }, 120);
  },
});
