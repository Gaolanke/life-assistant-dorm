/* 提醒推送：QQ 官方机器人汇报 + 定时提醒 */
App.page('push', {
  async render(box) {

    box.innerHTML = `
      <div class="card">
        <div class="toolbar">
          <span class="chip" id="pushDate">—</span>
          <input type="date" id="pushDay" value="${App.today()}" style="width:150px">
          <button class="btn tiny primary" id="btnPushRefresh">刷新预览</button>
          <span style="flex:1"></span>
          <span class="chip gray" id="chipQqbot">QQ 官方机器人</span>
          <button class="btn tiny" id="btnGoConfig">去修改配置</button>
        </div>
        <div class="hint-text">下面是<b>实际会发出去的内容</b>（每天自动发送，也可以在这里手动点发送）。发送记录请看页面最下方。</div>
        <div class="hint-text">⚠️ 服务器到腾讯的网络不稳，发送时会<b>自动重试最多 4 次</b>，所以点完按钮可能要等十几秒到一两分钟，<b>请不要关页面</b>。</div>
      </div>

      <div class="grid side">
        <div class="card">
          <div class="card-head">
            <h2>每晚 QQ 群汇报</h2>
            <span class="sub" id="reportTimeHint">—</span>
            <span class="spacer"></span>
            <button class="btn tiny" id="btnCopyReport">复制</button>
            <button class="btn tiny primary" id="btnSendReport">立即发送到 QQ 群</button>
          </div>
          <div class="logbox" id="previewReport">加载中…</div>
          <div class="hint-text" id="reportTargets">—</div>
        </div>
        <div class="card">
          <div class="card-head">
            <h2>定时提醒</h2>
            <span class="sub">可添加多条，每条有自己的时间和内容</span>
            <span class="spacer"></span>
            <button class="btn tiny primary" id="btnAddReminder">+ 添加提醒</button>
          </div>
          <div id="reminderList"><div class="hint-text">加载中…</div></div>
          <div class="hint-text" style="margin-top:8px">
            内容里可用变量：
            <span class="chip">{date}</span> <span class="chip">{time}</span> <span class="chip">{weekday}</span>
            <span class="chip">{site}</span> <span class="chip">{mention}</span>
            <span class="chip">{missing}</span> <span class="chip">{missing_list}</span> <span class="chip">{missing_count}</span>
            <span class="chip">{reported}</span> <span class="chip">{dorm_total}</span> <span class="chip">{unreported}</span>
            <span class="chip">{school}</span> <span class="chip">{class_name}</span> <span class="chip">{commissary}</span>
            <br>{mention} 会在这提醒开了「@全体成员」时自动换成 @所有人，否则为空。
          </div>
        </div>
        <div class="card">
          <div class="card-head">
            <h2>未填报提醒</h2>
            <span class="sub" id="remindTimeHint">—</span>
            <span class="spacer"></span>
            <button class="btn tiny" id="btnCopyRemind">复制</button>
            <button class="btn tiny primary" id="btnSendRemind">推送提醒</button>
          </div>
          <div class="logbox" id="previewRemind">加载中…</div>
          <div class="hint-text" id="remindMissing">—</div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h2>推送通道自检</h2><span class="spacer"></span><button class="btn tiny" id="btnCheckBot">检测通道</button></div>
        <div class="grid cols-2">
          <div>
            <div class="hint-text">QQ 官方机器人（主通道）</div>
            <div id="botStatus" class="hint-text">未检测</div>
          </div>
        </div>
        <div class="hint-text" style="margin-top:8px">
          机器人靠 <b>WebSocket 长连接</b> 收消息，不需要填回调地址；发送窗口的开关在「系统配置 → QQ 官方机器人」。
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>推送日志</h2>
          <span class="sub">谁也发不了假消息 —— 每次推送都留痕</span>
          <span class="spacer"></span>
          <select id="logChannel" style="width:150px">
            <option value="">全部渠道</option>
            <option value="qqbot">QQ 官方机器人</option>
          </select>
          <button class="btn tiny" id="btnLogRefresh">刷新</button>
        </div>
        <div class="table-wrap" style="max-height:420px;overflow:auto"><table id="logTable"></table></div>
      </div>

      <div class="card">
        <div class="card-head"><h2>群消息填报（QQ 官方机器人）</h2></div>
        <div class="hint-text">
          机器人靠 <b>WebSocket 长连接</b> 收群消息，<b>不用填回调地址</b>。宿舍长可以直接在群里 @ 机器人：<br>
          <b>@Xiaoai 汇报</b> → 机器人把当天填报情况发到群里<br>
          <b>@Xiaoai 谁没填</b> → 只发未填报清单<br>
          <b>@Xiaoai 6-213 人齐</b> → 自动记录这间寝室今天的填报<br>
          <span class="hint-text">（@ 之后的回复属于"被动回复"，不受官方主动消息权限限制）</span>
        </div>
      </div>`;

    const loadPreview = async () => {
      const day = $('#pushDay').value || App.today();
      const data = await App.api(`/api/reports/preview?day=${day}&${App.classQuery()}`);
      $('#pushDate').textContent = `${data.date} ${App.weekday(data.date)}`;
      $('#previewReport').textContent = data.group_report;
      $('#previewRemind').textContent = data.reminder;
      $('#remindMissing').innerHTML = data.missing.length
        ? `未填报宿舍：<b style="color:#dc2626">${App.esc(data.missing.join('、'))}</b>`
        : '全部宿舍已填报，不需要提醒 ✅';
      const settings = App.state.settings || {};
      $('#reportTimeHint').textContent = `每天 ${settings.qq_report_time || '22:40'} 自动发送`;
      $('#remindTimeHint').textContent = '定时任务已删除，仅支持手动推送';
      try {
        const status = await App.api(`/api/push/status?${App.classQuery()}`);
        $('#botStatus').innerHTML = status.ok
          ? `<span class="chip ok">在线</span> ${App.esc(status.message)}`
          : `<span class="chip bad">不可用</span> ${App.esc(status.message)}`;
        $('#reportTargets').innerHTML = `发送目标群${status.class_name ? `（${App.esc(status.class_name)}）` : ''}：${(status.targets || []).length
          ? `<code>${App.esc(status.targets.join('、'))}</code>`
          : '未绑定（去「班级管理」把机器人所在的群绑定到该班级）'}`;
        const chip = $('#chipQqbot');
        if (chip) {
          chip.textContent = `QQ 官方机器人 ${status.enabled ? (status.gateway_running ? '在线' : '已开·连接中') : '未启用'}`;
          chip.className = `chip ${status.ok ? 'ok' : (status.enabled ? 'warn' : 'gray')}`;
        }
      } catch (e) { /* 忽略 */ }
    };

    const loadLogs = async () => {
      const channel = $('#logChannel').value;
      const data = await App.api(`/api/logs/push?limit=60${channel ? `&channel=${channel}` : ''}`);
      $('#logTable').innerHTML = `
        <thead><tr><th>时间</th><th>渠道</th><th>场景</th><th>目标</th><th>结果</th><th>触发</th><th class="wrap">内容 / 错误</th></tr></thead>
        <tbody>${(data.items || []).map((log) => `<tr>
          <td>${App.esc(log.created_at)}</td>
          <td>${App.esc(log.channel_text)}</td>
          <td>${App.esc(log.scene_text)}</td>
          <td>${App.esc(log.target || '—')}</td>
          <td>${log.status === 'success' ? '<span class="chip ok">成功</span>' : '<span class="chip bad">失败</span>'}</td>
          <td>${App.esc(log.trigger)}</td>
          <td class="wrap"><details><summary>查看</summary><div class="logbox" style="margin-top:6px">${App.esc(log.detail || log.content || '')}</div></details></td>
        </tr>`).join('') || '<tr><td colspan="7" class="empty">还没有推送记录</td></tr>'}</tbody>`;
    };

    $('#btnPushRefresh').onclick = loadPreview;
    $('#pushDay').onchange = loadPreview;
    $('#btnLogRefresh').onclick = loadLogs;
    $('#logChannel').onchange = loadLogs;
    $('#btnGoConfig').onclick = () => { location.hash = '#/config'; };
    $('#btnCopyReport').onclick = () => App.copy($('#previewReport').textContent);
    $('#btnCopyRemind').onclick = () => App.copy($('#previewRemind').textContent);

    // ---------------- 定时提醒（多条，可增删改） ----------------
    const reminderState = { items: [], presets: [], jobs: [] };

    const nextRuns = () => {
      const map = {};
      (reminderState.jobs || []).forEach((j) => {
        if (j.id && j.id.startsWith('reminder_')) map[j.id.slice(9)] = j.next_run;
      });
      return map;
    };

    const saveReminders = async () => {
      const res = await App.api('/api/reminders', 'PUT', { items: reminderState.items, class_id: App.state.classId || 0 });
      reminderState.items = res.items || reminderState.items;
      reminderState.jobs = res.jobs || reminderState.jobs;
      App.toast(res.message || '已保存', 'ok');
      renderReminders();
    };

    const renderReminders = () => {
      const box2 = $('#reminderList');
      if (!box2) return;
      const runs = nextRuns();
      if (!reminderState.items.length) {
        box2.innerHTML = '<div class="hint-text">还没有定时提醒，点右上角「+ 添加提醒」新建一条。</div>';
        return;
      }
      box2.innerHTML = reminderState.items.map((r) => `
        <div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px dashed var(--line,#e5e7eb);flex-wrap:wrap">
          <span class="chip ${r.enabled ? 'ok' : 'gray'}">${r.enabled ? '定时中' : '已停用'}</span>
          <b>${App.esc(r.name)}</b>
          <span class="chip">每天 ${App.esc(r.time)}</span>
          ${r.mention_all ? '<span class="chip warn">@全体成员</span>' : ''}
          ${runs[r.id] ? `<span class="hint-text">下次：${App.esc(runs[r.id])}</span>` : ''}
          <span style="flex:1"></span>
          <button class="btn tiny" data-rprev="${App.attr(r.id)}">预览</button>
          <button class="btn tiny" data-redit="${App.attr(r.id)}">编辑</button>
          <button class="btn tiny primary" data-rsend="${App.attr(r.id)}">立即发送</button>
          <button class="btn tiny danger" data-rdel="${App.attr(r.id)}">删除</button>
        </div>`).join('');

      box2.querySelectorAll('[data-rprev]').forEach((btn) => {
        btn.onclick = async () => {
          const r = reminderState.items.find((x) => x.id === btn.dataset.rprev);
          if (!r) return;
          try {
            const res = await App.api('/api/reminders/render', 'POST', { content: r.content, mention_all: !!r.mention_all, class_id: App.state.classId || 0 });
            App.modal({
              title: `预览：${r.name}`,
              okText: '关闭',
              showCancel: false,
              html: `<div class="logbox" style="max-height:320px;overflow:auto">${App.esc(res.rendered || '')}</div>`,
              onOk: () => true,
            });
          } catch (e) { App.toast(e.message, 'err'); }
        };
      });
      box2.querySelectorAll('[data-redit]').forEach((btn) => {
        btn.onclick = () => editReminder(btn.dataset.redit);
      });
      box2.querySelectorAll('[data-rsend]').forEach((btn) => {
        btn.onclick = async () => {
          const r = reminderState.items.find((x) => x.id === btn.dataset.rsend);
          if (!r) return;
          if (!window.confirm(`确定现在向 QQ 群发送提醒「${r.name}」吗？${r.mention_all ? '\n\n会 @全体成员。' : ''}`)) return;
          btn.disabled = true;
          btn.textContent = '发送中…';
          try {
            const res = await App.api(`/api/reminders/${encodeURIComponent(r.id)}/send?${App.classQuery()}`, 'POST');
            App.toast(res.ok ? (res.message || '已发送') : `发送失败：${res.message}`, res.ok ? 'ok' : 'err');
            await loadLogs();
          } catch (e) { App.toast(e.message, 'err'); } finally {
            btn.disabled = false;
            btn.textContent = '立即发送';
          }
        };
      });
      box2.querySelectorAll('[data-rdel]').forEach((btn) => {
        btn.onclick = async () => {
          const r = reminderState.items.find((x) => x.id === btn.dataset.rdel);
          if (!r) return;
          if (!window.confirm(`确定删除提醒「${r.name}」（每天 ${r.time}）吗？`)) return;
          reminderState.items = reminderState.items.filter((x) => x.id !== r.id);
          try { await saveReminders(); } catch (e) { App.toast(e.message, 'err'); }
        };
      });
    };

    const editReminder = (rid) => {
      const isNew = !rid;
      const r = isNew
        ? { id: `r${Date.now().toString(36)}`, name: '', time: '21:30', enabled: true, mention_all: false, content: '' }
        : reminderState.items.find((x) => x.id === rid);
      if (!r) return;
      const presetOptions = reminderState.presets
        .map((p, i) => `<option value="${i}">${App.esc(p.name)}</option>`)
        .join('');
      App.modal({
        title: isNew ? '添加提醒' : `编辑提醒：${r.name}`,
        okText: '保存',
        html: `
          <label class="field"><span>提醒名称</span><input id="rName" value="${App.attr(r.name)}" placeholder="例如：填报提醒 / 未填名单 / 最后通报"></label>
          <div class="grid cols-2" style="margin-top:8px">
            <label class="field"><span>发送时间</span><input id="rTime" type="time" value="${App.attr(r.time)}"></label>
            <label class="field"><span>选择模板（选完还能改）</span>
              <select id="rPreset">
                <option value="">— 手动编写 / 保持当前 —</option>
                ${presetOptions}
              </select>
            </label>
          </div>
          <label class="field" style="margin-top:8px"><span>提醒内容</span>
            <textarea id="rContent" style="min-height:150px">${App.esc(r.content)}</textarea>
          </label>
          <div class="grid cols-2" style="margin-top:8px">
            <label class="field"><span>@全体成员</span>
              <select id="rMention">
                <option value="0" ${r.mention_all ? '' : 'selected'}>不 @</option>
                <option value="1" ${r.mention_all ? 'selected' : ''}>@全体成员</option>
              </select>
            </label>
            <label class="field"><span>定时开关</span>
              <select id="rEnabled">
                <option value="1" ${r.enabled ? 'selected' : ''}>开启（每天定时发）</option>
                <option value="0" ${r.enabled ? '' : 'selected'}>停用</option>
              </select>
            </label>
          </div>
          <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
            <button class="btn tiny" id="rPreviewBtn" type="button">预览效果</button>
          </div>
          <div id="rPreviewBox" class="logbox hidden" style="margin-top:8px;max-height:220px;overflow:auto"></div>`,
        onOk: async (modalBox) => {
          const name = modalBox.querySelector('#rName').value.trim();
          const time = modalBox.querySelector('#rTime').value.trim();
          const content = modalBox.querySelector('#rContent').value;
          if (!name) { App.toast('请填写提醒名称', 'err'); return false; }
          if (!time) { App.toast('请选择发送时间', 'err'); return false; }
          if (!content.trim()) { App.toast('提醒内容不能为空', 'err'); return false; }
          r.name = name;
          r.time = time;
          r.content = content;
          r.mention_all = modalBox.querySelector('#rMention').value === '1';
          r.enabled = modalBox.querySelector('#rEnabled').value === '1';
          if (isNew) reminderState.items.push(r);
          try {
            await saveReminders();
            return true;
          } catch (e) {
            App.toast(e.message, 'err');
            return false;
          }
        },
      });
      // 选模板 → 填入内容（不覆盖已有内容，除非确认）
      const presetSel = document.querySelector('#rPreset');
      if (presetSel) {
        presetSel.onchange = () => {
          const idx = presetSel.value;
          if (idx === '') return;
          const p = reminderState.presets[Number(idx)];
          if (!p) return;
          const contentEl = document.querySelector('#rContent');
          if (contentEl.value.trim() && !window.confirm('用模板覆盖当前内容吗？')) { presetSel.value = ''; return; }
          contentEl.value = p.content;
          document.querySelector('#rMention').value = p.mention_all ? '1' : '0';
          const nameEl = document.querySelector('#rName');
          if (!nameEl.value.trim()) nameEl.value = p.name;
          presetSel.value = '';
          App.toast(`已套用模板「${p.name}」，可以继续修改`, 'ok');
        };
      }
      const previewBtn = document.querySelector('#rPreviewBtn');
      if (previewBtn) {
        previewBtn.onclick = async () => {
          try {
            const res = await App.api('/api/reminders/render', 'POST', {
              content: document.querySelector('#rContent').value,
              mention_all: document.querySelector('#rMention').value === '1',
              class_id: App.state.classId || 0,
            });
            const boxEl = document.querySelector('#rPreviewBox');
            boxEl.classList.remove('hidden');
            boxEl.textContent = res.rendered || '';
          } catch (e) { App.toast(e.message, 'err'); }
        };
      }
    };

    const loadReminders = async () => {
      try {
        const res = await App.api(`/api/reminders?${App.classQuery()}`);
        reminderState.items = res.items || [];
        reminderState.presets = res.presets || [];
        reminderState.jobs = res.jobs || [];
        renderReminders();
      } catch (e) {
        const box2 = $('#reminderList');
        if (box2) box2.innerHTML = `<span class="chip bad">加载失败</span> ${App.esc(e.message)}`;
      }
    };

    const btnAddReminder = $('#btnAddReminder');
    if (btnAddReminder) btnAddReminder.onclick = () => editReminder('');

    $('#btnSendReport').onclick = async () => {
      const btn = $('#btnSendReport');
      btn.disabled = true;
      try {
        const res = await App.api('/api/settings/test', 'POST', { kind: 'notify', day: $('#pushDay').value, class_id: App.state.classId || 0 });
        App.toast(res.ok ? '已发送到本班 QQ 群' : `发送失败：${res.message || ''}`, res.ok ? 'ok' : 'err');
        await loadLogs();
      } catch (e) { App.toast(e.message, 'err'); } finally { btn.disabled = false; }
    };
    $('#btnSendRemind').onclick = async () => {
      const btn = $('#btnSendRemind');
      btn.disabled = true;
      try {
        const res = await App.api(`/api/jobs/missing_reminder_c${App.state.classId || 0}/run`, 'POST');
        App.toast(res.ok ? (res.message || '提醒已推送到本班 QQ 群') : `推送失败：${res.message}`, res.ok ? 'ok' : 'err');
        await loadLogs();
      } catch (e) { App.toast(e.message, 'err'); } finally { btn.disabled = false; }
    };
    $('#btnCheckBot').onclick = async () => {
      const status = await App.api('/api/push/status');
      $('#botStatus').innerHTML = status.ok
        ? `<span class="chip ok">已连接</span> ${App.esc(status.message)}`
        : `<span class="chip bad">未连接</span> ${App.esc(status.message)}`;
      App.toast(status.ok ? '连接正常' : '连接失败，请看下方提示', status.ok ? 'ok' : 'err');
    };

    await loadPreview();
    await loadReminders();
    await loadLogs();
  },
});
