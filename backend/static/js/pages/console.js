/* 管理控制台：寝室长身份一览与快速操作 */
App.page('console', {
  async render(box) {
    const state = { rows: [], keyword: '' };

    box.innerHTML = `
      <div class="card">
        <div class="card-head">
          <h2>🔐 管理控制台</h2>
          <span class="sub">寝室长密码一览；账号管理请到「账号管理」页</span>
          <span class="spacer"></span>
          <button class="btn tiny" id="btnGenAll">给没有密码的寝室批量生成</button>
          <button class="btn tiny" id="btnConsoleRefresh">刷新</button>
        </div>
        <div id="consoleSummary" class="hint-text">加载中…</div>
      </div>

      <div class="card">
        <div class="card-head"><h3>寝室长登录密码</h3>
          <span class="sub">登录名 = 宿舍号；密码可以随时设置、重置或取消</span>
          <span class="spacer"></span>
          <input id="consoleSearch" placeholder="搜索宿舍号 / 寝室长" style="width:180px">
        </div>
        <div class="table-wrap" style="max-height:620px;overflow:auto"><table id="leaderTable"></table></div>
      </div>`;

    const loadLeaders = async () => {
      const data = await App.api('/api/access/leader/accounts');
      state.rows = data.items || [];
      const missing = state.rows.filter((d) => !d.has_password && d.active).length;
      const withAccount = state.rows.filter((d) => d.has_account).length;
      $('#consoleSummary').innerHTML = `
        寝室 <b>${data.total}</b> 间 · 已设密码 <b>${data.with_password}</b> 间 · 已建寝室长账号 <b>${withAccount}</b> 个 ·
        未设密码 <b style="color:${missing ? '#dc2626' : '#16a34a'}">${missing}</b> 间
        <div class="hint-text" style="margin-top:6px">
          没设密码的寝室：谁都能直接选它填报；设了密码的寝室：只有该寝室长登录后才能填报，你作为管理员不受限制。
        </div>`;

      const key = state.keyword.trim().toLowerCase();
      const rows = state.rows.filter((d) => !key
        || `${d.room_no}${d.leader_name}${d.room_label}`.toLowerCase().includes(key));

      $('#leaderTable').innerHTML = `
        <thead><tr>
          <th>宿舍号</th><th>寝室长</th><th>电话</th><th class="num">人数</th>
          <th>登录账号</th><th>密码状态</th><th style="min-width:320px">操作</th>
        </tr></thead>
        <tbody>${rows.map((d) => `<tr data-dorm="${d.dorm_id}" data-room="${App.attr(d.room_no)}">
          <td><b>${App.esc(d.room_no)}</b>${d.room_label ? `<div class="hint-text">${App.esc(d.room_label)}</div>` : ''}</td>
          <td>${d.leader_name ? App.esc(d.leader_name) : '<span class="chip warn">未指定</span>'}</td>
          <td>${App.esc(d.leader_phone || '—')}</td>
          <td class="num">${d.member_count}</td>
          <td><code>${App.esc(d.account_username)}</code>${d.has_account ? '' : ' <span class="hint-text">（按宿舍号登录）</span>'}</td>
          <td>${d.has_password ? '<span class="chip ok">已设置</span>' : '<span class="chip warn">未设置</span>'}
              ${d.has_account && !d.account_active ? '<span class="chip bad">账号已停用</span>' : ''}</td>
          <td>
            <input class="pwd-input" data-dorm="${d.dorm_id}" placeholder="填密码（≥6 位）" style="width:130px">
            <button class="btn tiny primary" data-act="savePwd" data-id="${d.dorm_id}">${d.has_password ? '改密码' : '设密码'}</button>
            <button class="btn tiny" data-act="randPwd" data-id="${d.dorm_id}">重置</button>
            ${d.has_account ? '' : `<button class="btn tiny" data-act="makeAccount" data-id="${d.dorm_id}" data-room="${App.attr(d.room_no)}">建账号</button>`}
            ${d.has_password ? `<button class="btn tiny danger" data-act="clearPwd" data-id="${d.dorm_id}" data-room="${App.attr(d.room_no)}">取消密码</button>` : ''}
          </td>
        </tr>`).join('') || '<tr><td colspan="7" class="empty">没有匹配的寝室</td></tr>'}</tbody>`;

      $$('#leaderTable [data-act]').forEach((btn) => {
        btn.onclick = async () => {
          const dormId = Number(btn.dataset.id);
          const roomNo = btn.dataset.room;
          const act = btn.dataset.act;
          const row = btn.closest('tr');
          const input = row.querySelector('.pwd-input');

          if (act === 'clearPwd') {
            App.confirmBox(
              `取消 ${roomNo} 的验证密码？取消后这间寝室谁都能直接填报。`,
              async () => {
                btn.disabled = true;
                try {
                  const res = await App.api('/api/access/leader/password', 'POST', { dorm_id: dormId, action: 'clear' });
                  App.toast(res.message || '已取消密码', 'ok');
                  await loadLeaders();
                } catch (e) { App.toast(e.message, 'err'); } finally { btn.disabled = false; }
              },
              '取消密码',
            );
            return;
          }

          if (act === 'makeAccount') {
            btn.disabled = true;
            try {
              const res = await App.api('/api/accounts', 'POST', { username: roomNo, role: 'leader', room_no: roomNo });
              App.showResetCredential({ ...res, username: res.account.username, room_no: roomNo }, 'leader', `寝室长账号 ${res.account.username}`);
              await loadLeaders();
            } catch (e) { App.toast(e.message, 'err'); } finally { btn.disabled = false; }
            return;
          }

          const isRandom = act === 'randPwd';
          const password = isRandom ? '' : input.value.trim();
          if (!isRandom && password.length < 6) {
            App.toast('密码至少 6 位', 'err');
            if (input) input.focus();
            return;
          }
          btn.disabled = true;
          try {
            const res = await App.api('/api/access/leader/password', 'POST', isRandom
              ? { dorm_id: dormId, action: 'random' }
              : { dorm_id: dormId, action: 'set', password });
            if (input) input.value = '';
            App.showResetCredential(res, 'leader', `${res.room_no} 的登录密码`);
            await loadLeaders();
          } catch (e) {
            App.toast(e.message, 'err');
          } finally {
            btn.disabled = false;
          }
        };
      });
    };

    $('#consoleSearch').oninput = (e) => {
      state.keyword = e.target.value;
      clearTimeout(state.timer);
      state.timer = setTimeout(loadLeaders, 250);
    };
    $('#btnConsoleRefresh').onclick = () => loadLeaders();
    $('#btnGenAll').onclick = () => App.confirmBox(
      '给所有还没有密码的寝室各随机生成一个密码？',
      async () => {
        const targets = state.rows.filter((d) => !d.has_password && d.active);
        if (!targets.length) { App.toast('所有寝室都已经有密码了', 'ok'); return; }
        const lines = [];
        for (const dorm of targets) {
          try {
            const res = await App.api('/api/access/leader/password', 'POST', { dorm_id: dorm.dorm_id, action: 'random' });
            lines.push(`${res.room_no}  ${res.password}`);
          } catch (e) {
            lines.push(`${dorm.room_no}  失败：${e.message}`);
          }
        }
        App.modal({
          title: `已为 ${lines.length} 间寝室生成密码`,
          hideOk: true,
          cancelText: '关闭',
          html: `<div class="hint-text">复制下面的内容发给各寝室长（宿舍号 + 密码）：</div>
            <div class="logbox" style="white-space:pre-wrap;margin-top:8px">${App.esc(lines.join('\n'))}</div>
            <div style="margin-top:10px"><button class="btn tiny primary" id="btnCopyAll">复制全部</button></div>`,
          onMount: (modalBox) => {
            modalBox.querySelector('#btnCopyAll').onclick = () => App.copy(lines.join('\n'));
          },
        });
        await loadLeaders();
      },
      '批量生成',
    );

    await loadLeaders();
  },
});
