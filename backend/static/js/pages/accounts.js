/* 账号管理：管理员账号 + 寝室长账号 */
App.page('accounts', {
  async render(box) {
    const state = { tab: 'admin', keyword: '', accounts: [], dorms: [] };

    box.innerHTML = `
      <div class="card">
        <div class="card-head">
          <h2>👥 账号管理</h2>
          <span class="sub">管理员账号用于登录管理端；寝室长账号用宿舍号登录，只能填自己寝室</span>
          <span class="spacer"></span>
          <button class="btn tiny primary" id="btnChangeMyPwd">🔑 修改我的密码</button>
          <button class="btn tiny" id="btnNewAccount">➕ 添加账号</button>
          <button class="btn tiny" id="btnBatchLeader">给所有寝室批量建寝室长账号</button>
          <button class="btn tiny" id="btnAccountsRefresh">刷新</button>
        </div>
        <div class="toolbar">
          <div class="tabs" id="accTabs" style="margin:0">
            <button class="tab active" data-t="admin">管理员账号</button>
            <button class="tab" data-t="leader">寝室长账号</button>
          </div>
          <span style="flex:1"></span>
          <input id="accKeyword" placeholder="搜索用户名 / 姓名 / 宿舍号" style="width:220px">
        </div>
        <div class="hint-text" id="accSummary">加载中…</div>
      </div>
      <div class="card">
        <div class="table-wrap" style="max-height:660px;overflow:auto"><table id="accTable"></table></div>
      </div>`;

    const roleText = (role) => (role === 'admin' ? '管理员' : '寝室长');

    const renderAdmin = (items) => {
      $('#accTable').innerHTML = `
        <thead><tr>
          <th>用户名</th><th>姓名</th><th>电话</th><th>状态</th><th>最近登录</th><th>登录 IP / 设备</th><th style="min-width:300px">操作</th>
        </tr></thead>
        <tbody>${items.map((a) => `<tr data-id="${a.id}">
          <td><b>${App.esc(a.username)}</b>${a.is_owner ? ' <span class="chip warn">超级管理员</span>' : ''}${a.must_change ? ' <span class="chip">待改密码</span>' : ''}</td>
          <td><input class="acc-name" data-id="${a.id}" value="${App.attr(a.display_name)}" style="width:110px"></td>
          <td><input class="acc-phone" data-id="${a.id}" value="${App.attr(a.phone)}" style="width:120px"></td>
          <td>${a.active ? '<span class="chip ok">启用</span>' : '<span class="chip bad">已停用</span>'}</td>
          <td>${App.esc(a.last_login_at || '—')}</td>
          <td>${App.esc(a.last_login_ip || '—')}${a.last_login_device ? `<div class="hint-text">${App.esc(a.last_login_device)}</div>` : ''}</td>
          <td>
            <button class="btn tiny" data-act="save" data-id="${a.id}">保存</button>
            ${a.id === (App.state.account || {}).id
              ? '<button class="btn tiny primary" data-act="myPwd">改我的密码</button>'
              : `<button class="btn tiny primary" data-act="setPwd" data-id="${a.id}" data-name="${App.attr(a.username)}">设密码</button>`}
            <button class="btn tiny" data-act="resetPwd" data-id="${a.id}" data-name="${App.attr(a.username)}">随机重置</button>
            <button class="btn tiny" data-act="toggle" data-id="${a.id}" data-active="${a.active}">${a.active ? '停用' : '启用'}</button>
            ${a.is_owner ? '' : `<button class="btn tiny danger" data-act="del" data-id="${a.id}" data-name="${App.attr(a.username)}">删除</button>`}
          </td>
        </tr>`).join('') || '<tr><td colspan="7" class="empty">还没有管理员账号</td></tr>'}</tbody>`;
    };

    const renderLeader = (items) => {
      $('#accTable').innerHTML = `
        <thead><tr>
          <th>宿舍号</th><th>寝室长</th><th class="num">人数</th><th>登录账号</th><th>状态</th><th style="min-width:330px">操作</th>
        </tr></thead>
        <tbody>${items.map((d) => `<tr data-dorm="${d.dorm_id}">
          <td><b>${App.esc(d.room_no)}</b>${d.room_label ? `<div class="hint-text">${App.esc(d.room_label)}</div>` : ''}</td>
          <td>${d.leader_name ? App.esc(d.leader_name) : '<span class="chip warn">未指定</span>'}</td>
          <td class="num">${d.member_count}</td>
          <td>${d.has_account ? `<code>${App.esc(d.account_username)}</code>` : `<code>${App.esc(d.room_no)}</code> <span class="hint-text">（按宿舍号登录）</span>`}</td>
          <td>${d.has_password ? '<span class="chip ok">密码已设</span>' : '<span class="chip warn">未设密码</span>'}
              ${d.has_account && !d.account_active ? '<span class="chip bad">账号已停用</span>' : ''}</td>
          <td>
            <input class="pwd-input" data-dorm="${d.dorm_id}" placeholder="填密码（≥6 位）" style="width:130px">
            <button class="btn tiny primary" data-act="savePwd" data-id="${d.dorm_id}">${d.has_password ? '改密码' : '设密码'}</button>
            <button class="btn tiny" data-act="randPwd" data-id="${d.dorm_id}">重置</button>
            <button class="btn tiny" data-act="makeAccount" data-id="${d.dorm_id}" data-room="${App.attr(d.room_no)}">${d.has_account ? '重置账号' : '建账号'}</button>
            ${d.has_password ? `<button class="btn tiny danger" data-act="clearPwd" data-id="${d.dorm_id}" data-room="${App.attr(d.room_no)}">取消密码</button>` : ''}
          </td>
        </tr>`).join('') || '<tr><td colspan="6" class="empty">还没有寝室</td></tr>'}</tbody>`;
    };

    const bind = () => {
      $$('#accTable [data-act]').forEach((btn) => {
        btn.onclick = async () => {
          const id = Number(btn.dataset.id);
          const act = btn.dataset.act;
          const row = btn.closest('tr');
          btn.disabled = true;
          try {
            if (act === 'save') {
              const body = {
                display_name: row.querySelector('.acc-name').value,
                phone: row.querySelector('.acc-phone').value,
              };
              await App.api(`/api/accounts/${id}`, 'PATCH', body);
              App.toast('已保存', 'ok');
            } else if (act === 'myPwd') {
              App.showChangePassword();
              btn.disabled = false;
              return;
            } else if (act === 'setPwd') {
              App.showSetAccountPassword(btn.dataset.name, id, async () => { await load(); });
              btn.disabled = false;
              return;
            } else if (act === 'resetPwd') {
              const res = await App.api(`/api/accounts/${id}/password`, 'POST', {});
              App.showResetCredential(res, 'password', `账号 ${btn.dataset.name} 的新密码`);
            } else if (act === 'toggle') {
              const next = btn.dataset.active !== 'true';
              await App.api(`/api/accounts/${id}`, 'PATCH', { active: next });
              App.toast(next ? '已启用' : '已停用', 'ok');
            } else if (act === 'del') {
              App.confirmBox(`删除账号 ${btn.dataset.name}？这个账号将无法再登录。`, async () => {
                await App.api(`/api/accounts/${id}`, 'DELETE');
                App.toast('已删除', 'ok');
                await load();
              }, '删除');
              btn.disabled = false;
              return;
            } else if (act === 'savePwd' || act === 'randPwd') {
              const input = row.querySelector('.pwd-input');
              const isRandom = act === 'randPwd';
              const password = isRandom ? '' : input.value.trim();
              if (!isRandom && password.length < 6) {
                App.toast('密码至少 6 位', 'err');
                if (input) input.focus();
                btn.disabled = false;
                return;
              }
              const res = await App.api('/api/access/leader/password', 'POST', isRandom
                ? { dorm_id: id, action: 'random' }
                : { dorm_id: id, action: 'set', password });
              if (input) input.value = '';
              App.showResetCredential(res, 'leader', `${res.room_no} 的验证密码`);
            } else if (act === 'makeAccount') {
              const res = await App.api('/api/accounts', 'POST', {
                username: btn.dataset.room, role: 'leader', room_no: btn.dataset.room,
              });
              App.showResetCredential(
                { password: res.password, room_no: btn.dataset.room, username: res.account.username },
                'leader',
                `寝室长账号 ${res.account.username}`,
              );
            } else if (act === 'clearPwd') {
              App.confirmBox(
                `取消 ${btn.dataset.room} 的验证密码？取消后这间寝室谁都能直接填报。`,
                async () => {
                  await App.api('/api/access/leader/password', 'POST', { dorm_id: id, action: 'clear' });
                  App.toast('已取消密码', 'ok');
                  await load();
                },
                '取消密码',
              );
              btn.disabled = false;
              return;
            }
            await load();
          } catch (e) {
            App.toast(e.message, 'err');
          } finally {
            btn.disabled = false;
          }
        };
      });
    };

    const load = async () => {
      const key = state.keyword.trim();
      if (state.tab === 'admin') {
        const data = await App.api(`/api/accounts?role=admin&keyword=${encodeURIComponent(key)}`);
        state.accounts = data.items || [];
        $('#accSummary').innerHTML = `管理员账号 <b>${state.accounts.length}</b> 个 · 全部账号 <b>${data.total}</b> 个`
          + `<div class="hint-text" style="margin-top:6px">管理员账号能登录管理端（${location.origin}），可以查看和修改所有寝室的数据。
             密码随你设：点「改我的密码」改自己的，点「设密码」直接给别人定一个，点「随机重置」生成 6 位随机码。</div>`;
        renderAdmin(state.accounts);
      } else {
        const data = await App.api('/api/access/leader/accounts');
        const items = (data.items || []).filter((d) => !key
          || `${d.room_no}${d.leader_name}${d.room_label}`.toLowerCase().includes(key.toLowerCase()));
        $('#accSummary').innerHTML = `寝室 <b>${data.total}</b> 间 · 已设密码 <b>${data.with_password}</b> 间 · 已建账号 <b>${data.with_account}</b> 个`
          + `<div class="hint-text" style="margin-top:6px">寝室长用「宿舍号 + 密码」在填报端登录，登录后只能看和填自己寝室。</div>`;
        renderLeader(items);
      }
      bind();
    };

    $$('#accTabs .tab').forEach((tab) => {
      tab.onclick = async () => {
        state.tab = tab.dataset.t;
        $$('#accTabs .tab').forEach((t) => t.classList.toggle('active', t === tab));
        await load();
      };
    });
    $('#accKeyword').oninput = (e) => {
      state.keyword = e.target.value;
      clearTimeout(state.timer);
      state.timer = setTimeout(load, 300);
    };
    $('#btnAccountsRefresh').onclick = () => load();
    $('#btnChangeMyPwd').onclick = () => App.showChangePassword();
    $('#btnNewAccount').onclick = () => openNewAccount(load);
    $('#btnBatchLeader').onclick = () => App.confirmBox(
      '给所有还没有账号的寝室各建一个寝室长账号（用户名=宿舍号，密码随机生成）？',
      async () => {
        const res = await App.api('/api/accounts/batch-leader?only_missing=true', 'POST', {});
        App.showResetCredential(res, 'batch');
        await load();
      },
      '批量创建',
    );

    await load();
  },
});

/* 新建账号弹窗 */
function openNewAccount(after) {
  const html = `
    <div class="hint-text">账号密码可以用字母、数字、下划线，长度 3 位以上。</div>
    ${App.field('账号类型', `<select id="newRole">
        <option value="admin">管理员（能管理全部数据）</option>
        <option value="leader">寝室长（只能管自己寝室）</option>
      </select>`)}
    ${App.field('用户名', '<input id="newUsername" placeholder="管理员填英文名，如 teacher01">')}
    ${App.field('姓名 / 备注名', '<input id="newDisplay" placeholder="例如 班主任 张老师">')}
    <div id="leaderBox" class="hidden">
      ${App.field('绑定寝室（宿舍号）', `<input id="newRoom" placeholder="例如 6-213">`)}
      <div class="hint-text">寝室长账号的用户名默认就是宿舍号；登录后只能查看和填写这间寝室。</div>
    </div>
    ${App.field('电话（选填）', '<input id="newPhone" placeholder="11 位手机号">')}
    ${App.field('密码', '<input id="newPassword" placeholder="留空则自动生成一个">')}`;

  App.modal({
    title: '添加账号',
    okText: '创建',
    html,
    onMount: (box) => {
      const role = box.querySelector('#newRole');
      const leaderBox = box.querySelector('#leaderBox');
      role.onchange = () => {
        leaderBox.classList.toggle('hidden', role.value !== 'leader');
      };
    },
    onOk: async (box) => {
      const role = box.querySelector('#newRole').value;
      const username = box.querySelector('#newUsername').value.trim();
      const room = box.querySelector('#newRoom') ? box.querySelector('#newRoom').value.trim() : '';
      if (role === 'leader' && !username && !room) {
        App.toast('寝室长账号要填宿舍号', 'err');
        return false;
      }
      const res = await App.api('/api/accounts', 'POST', {
        role,
        username,
        display_name: box.querySelector('#newDisplay').value.trim(),
        room_no: room,
        phone: box.querySelector('#newPhone').value.trim(),
        password: box.querySelector('#newPassword').value.trim(),
      });
      if (res.generated) App.showResetCredential({ ...res, room_no: room || res.account.username }, 'new', '新账号已创建');
      else App.toast(res.message || '账号已创建', 'ok');
      if (typeof after === 'function') await after();
      return true;
    },
  });
}
