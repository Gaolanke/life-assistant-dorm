/* 填报记录查询 */
App.page('records', {
  async render(box) {
    const state = {
      start: App.shiftDate(-6),
      end: App.today(),
      dormId: '',
      onlyIncomplete: false,
      keyword: '',
    };

    box.innerHTML = `
      <div class="card">
        <div class="toolbar">
          <label style="display:flex;gap:6px;align-items:center;font-size:13px">开始
            <input type="date" id="recStart" value="${state.start}" style="width:150px">
          </label>
          <label style="display:flex;gap:6px;align-items:center;font-size:13px">结束
            <input type="date" id="recEnd" value="${state.end}" style="width:150px">
          </label>
          <select id="recDorm"><option value="">全部宿舍</option>
            ${(App.state.dorms || []).map((d) => `<option value="${d.id}">${App.esc(d.label || d.room_no)}</option>`).join('')}
          </select>
          <label style="display:flex;gap:6px;align-items:center;font-size:13px">
            <input type="checkbox" id="recOnlyAbsent" style="width:auto"> 只看缺人
          </label>
          <input id="recKeyword" placeholder="搜索姓名/备注/宿舍" style="width:170px">
          <button class="btn tiny primary" id="btnRecSearch">查询</button>
          <span style="flex:1"></span>
          <button class="btn tiny" id="btnRecExport">导出 Excel</button>
          <button class="btn tiny" id="btnRecFiles">服务器已存文件</button>
          <button class="btn tiny" id="btnRecBackfill">补填 / 修改</button>
        </div>
        <div id="recSummary" class="hint-text">加载中…</div>
      </div>

      <div class="card">
        <div class="card-head"><h2>填报记录</h2><span class="spacer"></span><span class="sub" id="recCount"></span></div>
        <div class="table-wrap" style="max-height:520px;overflow:auto"><table id="recTable"></table></div>
      </div>

      <div class="card">
        <div class="card-head"><h2>缺勤明细</h2><span class="sub">区间内所有“人员不齐”记录，可按人统计谁经常不在</span></div>
        <div class="table-wrap" style="max-height:380px;overflow:auto"><table id="absentTable"></table></div>
      </div>
    `;

    const load = async () => {
      const query = new URLSearchParams({
        start: state.start, end: state.end, only_incomplete: String(state.onlyIncomplete), keyword: state.keyword,
      });
      if (state.dormId) query.set('dorm_id', state.dormId);
      query.set('class_id', String(App.state.classId || 0));
      const data = await App.api(`/api/reports/records?${query.toString()}`);
      const items = data.items || [];
      $('#recCount').textContent = `${data.start} ~ ${data.end}，共 ${items.length} 条`;
      const incomplete = items.filter((i) => !i.is_complete).length;
      const absentTotal = items.reduce((sum, i) => sum + (i.absent_count || 0), 0);
      $('#recSummary').innerHTML = `已填报 <b>${items.length}</b> 条 · 缺人记录 <b style="color:#dc2626">${incomplete}</b> 条 · 累计缺席 <b>${absentTotal}</b> 人次`;

      $('#recTable').innerHTML = `
        <thead><tr><th>日期</th><th>宿舍</th><th>状态</th><th class="num">在寝/应到</th><th class="wrap">不在人员</th><th class="wrap">备注</th><th>填报人</th><th>填报时间</th><th>方式</th><th>来源 IP</th><th>填写设备</th><th>操作</th></tr></thead>
        <tbody>${items.map((item) => `<tr data-id="${item.id}">
          <td>${App.esc(item.report_date)}<div class="hint-text">${App.weekday(item.report_date)}</div></td>
          <td><b>${App.esc(item.room_no)}</b></td>
          <td>${App.statusChip(item.is_complete ? '齐全' : '缺人')}</td>
          <td class="num">${item.present_count}/${item.total_count}</td>
          <td class="wrap" style="color:${item.absent_names ? '#dc2626' : ''}">${App.esc(item.absent_names || '—')}</td>
          <td class="wrap">${App.esc(item.note || '')}</td>
          <td>${App.esc(item.submitter || '—')}</td>
          <td>${App.esc(item.submitted_at)}</td>
          <td>${App.esc(item.source_text || '')}</td>
          <td>${App.esc(item.ip || '—')}</td>
          <td>${App.esc(item.device || '—')}</td>
          <td>
            <button class="btn tiny" data-act="detail" data-id="${item.id}">详情</button>
            <button class="btn tiny danger" data-act="del" data-id="${item.id}" data-room="${App.attr(item.room_no)}" data-date="${item.report_date}">删除</button>
          </td>
        </tr>`).join('') || '<tr><td colspan="12" class="empty">这个时间段没有记录</td></tr>'}</tbody>`;

      items.forEach((item) => {
        const row = $(`#recTable tr[data-id="${item.id}"]`);
        if (!row) return;
        const detailBtn = row.querySelector('[data-act="detail"]');
        if (detailBtn) detailBtn.onclick = () => App.showReportDetail(item);
        const delBtn = row.querySelector('[data-act="del"]');
        if (delBtn) {
          delBtn.onclick = () => App.confirmBox(`删除 ${item.room_no} 在 ${item.report_date} 的填报记录？`, async () => {
            await App.api(`/api/reports/${item.id}`, 'DELETE');
            App.toast('已删除', 'ok');
            await load();
          }, '删除');
        }
      });

      const absents = data.absents || [];
      const counter = {};
      absents.forEach((a) => {
        (a.absent_names || '').split(/[、,，]/).map((s) => s.trim()).filter(Boolean).forEach((name) => {
          counter[name] = (counter[name] || 0) + 1;
        });
      });
      const top = Object.entries(counter).sort((a, b) => b[1] - a[1]).slice(0, 8);
      $('#absentTable').innerHTML = `
        <thead><tr><th>日期</th><th>宿舍</th><th class="num">缺席人数</th><th class="wrap">不在人员</th><th class="wrap">备注</th><th>填报人</th></tr></thead>
        <tbody>${absents.map((a) => `<tr>
          <td>${App.esc(a.date)}</td><td>${App.esc(a.room_no)}</td>
          <td class="num" style="color:#dc2626">${a.absent_count}</td>
          <td class="wrap">${App.esc(a.absent_names || '未说明')}</td>
          <td class="wrap">${a.note || ''}</td>
          <td>${App.esc(a.submitter || '')}</td>
        </tr>`).join('') || '<tr><td colspan="6" class="empty">区间内没有人缺席 ✅</td></tr>'}</tbody>`;
      if (top.length) {
        $('#recSummary').innerHTML += `<br>缺席次数最多：${top.map(([name, count]) => `${App.esc(name)}（${count} 次）`).join('、')}`;
      }
      App.applyPermission();
    };

    $('#btnRecSearch').onclick = async () => {
      state.start = $('#recStart').value || App.shiftDate(-6);
      state.end = $('#recEnd').value || App.today();
      state.dormId = $('#recDorm').value;
      state.onlyIncomplete = $('#recOnlyAbsent').checked;
      state.keyword = $('#recKeyword').value.trim();
      await load();
    };
    $('#btnRecExport').onclick = async () => {
      try {
        const name = await App.download(`/api/reports/export?start=${state.start}&end=${state.end}&${App.classQuery()}`, 'reports.xlsx');
        App.toast(`已导出 ${name}`, 'ok');
      } catch (e) { App.toast(e.message, 'err'); }
    };
    $('#btnRecFiles').onclick = async () => {
      const data = await App.api('/api/reports/export-files');
      App.modal({
        title: '服务器上已保存的 Excel',
        hideOk: true,
        cancelText: '关闭',
        wide: true,
        html: `<div class="hint-text" style="margin-bottom:8px">系统每天自动导出一次（可在系统配置里改时间），文件名按日期命名，从这里可以直接下载。</div>
          <div class="table-wrap" style="max-height:380px;overflow:auto"><table>
            <thead><tr><th>文件名</th><th class="num">大小</th><th>生成时间</th><th>操作</th></tr></thead>
            <tbody>${(data.items || []).map((f) => `<tr>
              <td>${App.esc(f.name)}</td><td class="num">${App.esc(f.size_text)}</td><td>${App.esc(f.modified)}</td>
              <td><button class="btn tiny" data-file="${App.attr(f.name)}">下载</button></td>
            </tr>`).join('') || '<tr><td colspan="4" class="empty">还没有自动导出的文件</td></tr>'}</tbody></table></div>`,
        onMount: (modalBox) => {
          modalBox.querySelectorAll('[data-file]').forEach((btn) => {
            btn.onclick = async () => {
              try {
                await App.download(`/api/reports/export-files/${encodeURIComponent(btn.dataset.file)}`, btn.dataset.file);
                App.toast('开始下载', 'ok');
              } catch (e) { App.toast(e.message, 'err'); }
            };
          });
        },
      });
    };
    $('#btnRecBackfill').onclick = () => App.showBackfill(state.end);

    await load();
  },
});

/* 记录详情 */
App.showReportDetail = function showReportDetail(item) {
  const checks = item.checks || [];
  App.modal({
    title: `${item.room_no} · ${item.report_date}`,
    hideOk: true,
    cancelText: '关闭',
    wide: true,
    html: `
      <div class="grid cols-2" style="gap:10px">
        <div><div class="hint-text">状态</div><div>${App.statusChip(item.is_complete ? '齐全' : '缺人')}</div></div>
        <div><div class="hint-text">填报人 / 时间</div><div><b>${App.esc(item.submitter || '—')}</b> · ${App.esc(item.submitted_at)}</div></div>
        <div><div class="hint-text">应到 / 在寝 / 缺席</div><div>${item.total_count} / ${item.present_count} / <b style="color:#dc2626">${item.absent_count}</b></div></div>
        <div><div class="hint-text">填报方式</div><div>${App.esc(item.source_text || '')}${item.raw_message ? `（原文：${App.esc(item.raw_message)}）` : ''}</div></div>
      </div>
      ${item.note ? `<div class="hint-text" style="margin-top:10px">备注：${App.esc(item.note)}</div>` : ''}
      <div class="hint-text" style="margin-top:10px">提交人：${App.esc(item.submitter || '—')} · 填报方式：${App.esc(item.source_text || '')}${item.raw_message ? `（群消息原文：${App.esc(item.raw_message)}）` : ''}</div>
      <div class="table-wrap" style="margin-top:12px">
        <table><thead><tr><th>姓名</th><th>学号</th><th>是否在寝</th><th>原因</th></tr></thead>
        <tbody>${checks.map((c) => `<tr>
          <td>${App.esc(c.name)}</td><td>${App.esc(c.student_no || '—')}</td>
          <td>${c.present ? App.statusChip('在寝') : App.statusChip('缺人')}</td>
          <td>${App.esc(c.reason || '')}</td>
        </tr>`).join('') || '<tr><td colspan="4" class="empty">没有成员明细（可能是群消息或导入的记录）</td></tr>'}</tbody></table>
      </div>`,
  });
};

/* 补填 / 修改任意宿舍的填报（无需登录） */
App.showBackfill = async function showBackfill(day) {
  const dormId = Number($('#recDorm') ? $('#recDorm').value : 0);
  const dormOptions = (App.state.dorms || []).map((d) => `<option value="${d.id}" ${d.id === dormId ? 'selected' : ''}>${App.esc(d.label || d.room_no)}</option>`).join('');
  App.modal({
    title: '补填 / 修改填报',
    okText: '保存',
    html: `
      <div class="grid cols-2" style="gap:10px">
        <label class="field"><span>宿舍 <b>*</b></span><select id="bfDorm">${dormOptions}</select></label>
        <label class="field"><span>日期 <b>*</b></span><input type="date" id="bfDate" value="${day || App.today()}" max="${App.today()}"></label>
      </div>
      <label class="field"><span>人员是否齐全</span>
        <select id="bfComplete"><option value="1">齐全</option><option value="0">缺人</option></select>
      </label>
      <label class="field"><span>不在人员</span><input id="bfAbsent" placeholder="多个姓名用、分隔，例如：张三、李四"></label>
      <label class="field"><span>备注</span><textarea id="bfNote" placeholder="意外问题、请假说明等"></textarea></label>
      <div class="hint-text">补填会覆盖该宿舍当天的记录，并记为“代填/修改”。</div>`,
    onMount: async (box) => {
      const loadDorm = async () => {
        const id = box.querySelector('#bfDorm').value;
        if (!id) return;
        const detail = await App.api(`/api/reports/dorm/${id}?day=${box.querySelector('#bfDate').value}`);
        const report = detail.report;
        box.querySelector('#bfComplete').value = report ? (report.is_complete ? '1' : '0') : '1';
        box.querySelector('#bfAbsent').value = report ? report.absent_names || '' : '';
        box.querySelector('#bfNote').value = report ? report.note || '' : '';
      };
      box.querySelector('#bfDorm').onchange = loadDorm;
      box.querySelector('#bfDate').onchange = loadDorm;
      await loadDorm();
    },
    onOk: async (box) => {
      const payload = {
        dorm_id: Number(box.querySelector('#bfDorm').value),
        report_date: box.querySelector('#bfDate').value,
        is_complete: box.querySelector('#bfComplete').value === '1',
        absent_names: box.querySelector('#bfAbsent').value.trim(),
        note: box.querySelector('#bfNote').value.trim(),
        submitter: App.state.submitter,
      };
      const res = await App.api('/api/reports/admin', 'POST', payload);
      App.toast(res.message || '已保存', 'ok');
      await App.reloadCurrent();
      return true;
    },
  });
};
