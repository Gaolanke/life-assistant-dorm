/* 用户填写日志（管理端）：谁在什么时间、用什么设备、什么 IP 提交的 */
App.page('logs', {
  async render(box) {
    const state = { tab: 'submissions', limit: 200, keyword: '' };

    box.innerHTML = `
      <div class="card">
        <div class="card-head">
          <h2>📋 用户填写日志</h2>
          <span class="sub">每条都记录填表人、来源 IP 和填写设备</span>
          <span class="spacer"></span>
          <button class="btn tiny" id="btnLogsRefresh">刷新</button>
        </div>
        <div class="toolbar">
          <div class="tabs" id="logTabs" style="margin:0">
            <button class="tab active" data-t="submissions">填报提交记录</button>
            <button class="tab" data-t="audit">全部操作日志</button>
          </div>
          <span style="flex:1"></span>
          <input id="logKeyword" placeholder="搜索宿舍号 / 填表人 / IP" style="width:200px">
          <label style="display:flex;gap:6px;align-items:center;font-size:13px">显示条数
            <input type="number" id="logLimit" value="200" min="20" max="1000" style="width:90px">
          </label>
        </div>
        <div class="hint-text" id="logSummary">加载中…</div>
      </div>
      <div class="card">
        <div class="table-wrap" style="max-height:640px;overflow:auto"><table id="logTable"></table></div>
      </div>`;

    const deviceOf = (row) => row.device || row.user_agent || '—';

    const renderSubmissions = (items) => {
      $('#logTable').innerHTML = `
        <thead><tr>
          <th>提交时间</th><th>宿舍</th><th>状态</th><th class="wrap">不在人员 / 备注</th>
          <th>填表人</th><th>方式</th><th>来源 IP</th><th>填写设备</th><th>操作</th>
        </tr></thead>
        <tbody>${items.map((row) => `<tr>
          <td>${App.esc(row.submitted_at)}</td>
          <td><b>${App.esc(row.room_no)}</b>${row.room_label ? `<div class="hint-text">${App.esc(row.room_label)}</div>` : ''}</td>
          <td>${row.is_complete ? App.statusChip('齐全') : App.statusChip('缺人')}</td>
          <td class="wrap">${row.absent_names ? `<span style="color:#dc2626">${App.esc(row.absent_names)}</span>` : '—'}${row.note ? `<div class="hint-text">${App.esc(row.note)}</div>` : ''}${row.raw_message ? `<div class="hint-text">群消息：${App.esc(row.raw_message)}</div>` : ''}</td>
          <td>${App.esc(row.submitter || '匿名填报')}</td>
          <td>${App.esc(row.source_text || '')}</td>
          <td>${App.esc(row.ip || '—')}</td>
          <td>${App.esc(deviceOf(row))}${row.device_raw ? `<div class="hint-text" title="${App.attr(row.device_raw)}">${App.esc(row.device_raw.slice(0, 46))}…</div>` : ''}</td>
          <td><button class="btn tiny" data-ua="${App.attr(row.device_raw || '')}">原始 UA</button></td>
        </tr>`).join('') || '<tr><td colspan="9" class="empty">还没有填报提交记录</td></tr>'}</tbody>`;
      bindUaButtons();
    };

    const renderAudit = (items) => {
      $('#logTable').innerHTML = `
        <thead><tr><th>时间</th><th>操作人</th><th>角色</th><th>操作</th><th>对象</th><th class="wrap">详情</th><th>来源 IP</th><th>设备</th></tr></thead>
        <tbody>${items.map((row) => `<tr>
          <td>${App.esc(row.created_at)}</td>
          <td>${App.esc(row.actor || '匿名')}</td>
          <td>${App.esc({ public: '公开填报', leader: '寝室长', admin: '管理员', qq: 'QQ群' }[row.role] || row.role || '')}</td>
          <td>${App.esc(row.action)}</td>
          <td>${App.esc(row.target || '')}</td>
          <td class="wrap">${App.esc(row.detail || '')}</td>
          <td>${App.esc(row.ip || '—')}</td>
          <td>${App.esc(deviceOf(row))}</td>
        </tr>`).join('') || '<tr><td colspan="8" class="empty">还没有操作日志</td></tr>'}</tbody>`;
    };

    const bindUaButtons = () => {
      $$('#logTable [data-ua]').forEach((btn) => {
        btn.onclick = () => {
          App.modal({
            title: '原始 User-Agent',
            hideOk: true,
            cancelText: '关闭',
            html: `<div class="logbox">${App.esc(btn.dataset.ua || '（没有记录）')}</div>`,
          });
        };
      });
    };

    const load = async () => {
      const keyword = state.keyword.trim().toLowerCase();
      if (state.tab === 'submissions') {
        const data = await App.api(`/api/logs/submissions?limit=${state.limit}&${App.classQuery()}`);
        const items = (data.items || []).filter((row) => !keyword
          || `${row.room_no}${row.submitter}${row.ip}${row.device}${row.note}${row.absent_names}`.toLowerCase().includes(keyword));
        const ips = new Set(items.map((row) => row.ip).filter(Boolean));
        const people = new Set(items.map((row) => row.submitter).filter(Boolean));
        $('#logSummary').innerHTML = `共 <b>${items.length}</b> 条提交记录 · 涉及 <b>${people.size}</b> 个填表人 · <b>${ips.size}</b> 个来源 IP`;
        renderSubmissions(items);
      } else {
        const data = await App.api(`/api/logs/audit?limit=${state.limit}`);
        const items = (data.items || []).filter((row) => !keyword
          || `${row.actor}${row.action}${row.target}${row.ip}${row.device}${row.detail}`.toLowerCase().includes(keyword));
        const ips = new Set(items.map((row) => row.ip).filter(Boolean));
        $('#logSummary').innerHTML = `共 <b>${items.length}</b> 条操作日志 · <b>${ips.size}</b> 个来源 IP`;
        renderAudit(items);
      }
    };

    $$('#logTabs .tab').forEach((tab) => {
      tab.onclick = async () => {
        state.tab = tab.dataset.t;
        $$('#logTabs .tab').forEach((item) => item.classList.toggle('active', item === tab));
        await load();
      };
    });
    $('#btnLogsRefresh').onclick = () => load();
    $('#logLimit').onchange = (e) => {
      state.limit = Math.max(20, Math.min(1000, Number(e.target.value) || 200));
      load();
    };
    $('#logKeyword').oninput = (e) => {
      state.keyword = e.target.value;
      clearTimeout(state.timer);
      state.timer = setTimeout(load, 300);
    };

    await load();
  },
});
