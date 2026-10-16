/* 数据看板 */
App.page('dashboard', {
  async render(box) {
    const data = await App.api(`/api/reports/dashboard?${App.classQuery()}`);
    App.state.lastStatus = data.stats.reported;
    box.innerHTML = `
      <div class="grid cols-4" style="margin-bottom:16px">
        <div class="card kpi blue">
          <span class="label">今晚已填报</span>
          <span class="value">${data.stats.reported}<small> / ${data.stats.dorm_total} 间</small></span>
          <span class="hint">未填报 <b style="color:#dc2626">${data.stats.unreported}</b> 间 · 填报率 ${data.stats.rate}%</span>
        </div>
        <div class="card kpi ${data.stats.absent ? 'red' : 'green'}">
          <span class="label">在寝人数</span>
          <span class="value">${data.stats.present}<small> / ${data.stats.total} 人</small></span>
          <span class="hint">缺席 <b>${data.stats.absent}</b> 人次 · 齐全省 ${data.stats.complete} / 缺人 ${data.stats.incomplete}</span>
        </div>
        <div class="card kpi amber">
          <span class="label">本周平均填报率</span>
          <span class="value">${data.week_avg_rate}<small>%</small></span>
          <span class="hint">本月宿舍平均 ${data.month_avg_rate}%</span>
        </div>
        <div class="card kpi green">
          <span class="label">连续填报提醒</span>
          <span class="value" style="font-size:17px">${data.stats.unreported ? `还差 ${data.stats.unreported} 间` : '今晚已收齐'}</span>
          <span class="hint">${data.stats.unreported ? '到「提醒推送」可以一键催填' : '全部宿舍都填报完成 🎉'}</span>
        </div>
      </div>

      <div class="card" style="background:linear-gradient(90deg,#eef4ff,#f5fbff);border-color:#dbe7ff">
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <span class="chip">📢 ${App.esc(data.notice || '')}</span>
          <span class="spacer" style="flex:1"></span>
          <span class="chip gray">今日 ${App.esc(data.today)} ${App.esc(data.weekday || '')}</span>
          <span class="chip ${data.stats.unreported ? 'bad' : 'ok'}">${data.stats.unreported ? `还差 ${data.stats.unreported} 间没填` : '全部宿舍已填报'}</span>
        </div>
      </div>

      <div class="grid side">
        <div class="card">
          <div class="card-head">
            <h2>近 14 天填报趋势</h2>
            <span class="sub">柱：每日填报宿舍数 · 线：填报率</span>
            <span class="spacer"></span>
            <button class="btn tiny" id="btnRefreshChart">刷新</button>
          </div>
          <div class="chart-box"><canvas id="chartDash"></canvas></div>
        </div>
        <div class="card">
          <div class="card-head"><h2>今日填报状态</h2><span class="spacer"></span><span class="chip ${App.rateClass(data.stats.rate)}">${data.stats.rate}%</span></div>
          <div class="chart-box short"><canvas id="chartDonut"></canvas></div>
          <div class="hint-text">未填报宿舍：${data.stats.missing_rooms.length ? App.esc(data.stats.missing_rooms.join('、')) : '无，全部已填报 🎉'}</div>
        </div>
      </div>

      <div class="grid side">
        <div class="card">
          <div class="card-head">
            <h2>各宿舍今晚情况</h2>
            <span class="sub">点击宿舍可查看/代填</span>
            <span class="spacer"></span>
            <span class="chip gray" id="dashUpdate">—</span>
          </div>
          <div class="table-wrap" style="max-height:420px;overflow-y:auto">
            <table id="dashDormTable"></table>
          </div>
        </div>
        <div class="card">
          <div class="card-head"><h2>最新填报动态</h2><span class="spacer"></span><span class="sub" id="dashRecentTime"></span></div>
          <div id="dashRecent"></div>
          <div class="card-head" style="margin-top:14px"><h3>本月填报最不积极</h3></div>
          <div id="dashWorst"></div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h2>缺席情况汇总</h2><span class="sub">今晚需要重点关注</span></div>
        <div id="dashAbsent"></div>
      </div>
    `;

    const renderTable = (items) => {
      const rows = items.map((item) => `
        <tr data-dorm="${item.dorm_id}" style="cursor:pointer">
          <td><b>${App.esc(item.room_no)}</b>${item.building ? `<span class="hint-text"> ${App.esc(item.building)}</span>` : ''}</td>
          <td>${App.esc(item.leader_name || '—')}</td>
          <td>${item.reported ? App.statusChip(item.status_text) : '<span class="chip bad">未填报</span>'}</td>
          <td class="num">${item.reported ? `${item.present_count}/${item.total_count}` : `—/${item.total_count}`}</td>
          <td class="wrap">${App.esc(item.absent_names || '')}</td>
          <td class="wrap">${App.esc(item.note || '')}</td>
          <td>${App.esc(item.submitted_time || (item.submitted_at ? item.submitted_at.slice(11, 16) : ''))}</td>
        </tr>`).join('');
      $('#dashDormTable').innerHTML = `
        <thead><tr><th>宿舍</th><th>宿舍长</th><th>状态</th><th class="num">在寝/应到</th><th class="wrap">不在人员</th><th class="wrap">备注</th><th>填报时间</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="7" class="empty">还没有宿舍数据，请先到「宿舍与人员」导入名单</td></tr>'}</tbody>`;
      $$('#dashDormTable tbody tr[data-dorm]').forEach((tr) => {
        tr.onclick = () => App.openDormDetail(Number(tr.dataset.dorm), App.today());
      });
    };

    const renderStats = () => {
      renderTable(data.items || []);
      $('#dashRecent').innerHTML = (data.recent || []).length
        ? data.recent.map((item) => `
            <div class="member-row" style="grid-template-columns:1fr">
              <div class="member-main">
                <strong>${App.esc(item.room_no)} · ${item.is_complete ? '人员齐全' : `缺 ${item.absent_count} 人`}</strong>
                <span>${App.esc(item.submitted_at)} · ${App.esc(item.submitter || '')} · ${App.esc(item.source_text || '')}</span>
                ${item.absent_names ? `<span style="color:#dc2626">不在：${App.esc(item.absent_names)}</span>` : ''}
                ${item.note ? `<span>备注：${App.esc(item.note)}</span>` : ''}
              </div>
            </div>`).join('')
        : '<div class="empty">今晚还没有人填报</div>';

      $('#dashWorst').innerHTML = (data.worst_dorms || []).map((item) => `
        <div style="margin-bottom:9px">
          <div style="display:flex;justify-content:space-between;font-size:13px">
            <span>${App.esc(item.room_no)} · ${App.esc(item.leader_name || '未指定宿舍长')}</span>
            <span>${item.rate}%（缺 ${item.missing} 天）</span>
          </div>
          ${App.progress(item.rate)}
        </div>`).join('') || '<div class="empty">暂无数据</div>';

      const absents = (data.stats.absent_rooms || []);
      $('#dashAbsent').innerHTML = absents.length
        ? `<div class="table-wrap"><table>
            <thead><tr><th>宿舍</th><th class="num">缺席人数</th><th class="wrap">不在人员</th><th class="wrap">备注</th><th>宿舍长</th></tr></thead>
            <tbody>${absents.map((item) => `<tr>
              <td><b>${App.esc(item.room_no)}</b></td>
              <td class="num" style="color:#dc2626">${item.absent_count}</td>
              <td class="wrap">${App.esc(item.absent_names || '未说明')}</td>
              <td class="wrap">${App.esc(item.note || '')}</td>
              <td>${App.esc((rowIndex[item.room_no] || {}).leader_name || '')}</td>
            </tr>`).join('')}</tbody></table></div>`
        : '<div class="empty">今晚没有缺勤记录 ✅</div>';
      $('#dashUpdate').textContent = `更新于 ${data.server_time}`;
    };

    const renderCharts = async () => {
      try {
        const trend = await App.api(`/api/reports/stats?granularity=day&points=14&${App.classQuery()}`);
        App.lineChart($('#chartDash'), trend.items.map((i) => i.label), [
          { label: '填报率 %', data: trend.items.map((i) => i.rate), color: '#1f6feb', yAxisID: 'y' },
          { label: '已填宿舍数', data: trend.items.map((i) => i.reported), color: '#16a34a', type: 'bar', fill: false, yAxisID: 'y1' },
        ], { hasY1: true });
      } catch (e) { /* 忽略 */ }
      App.donutChart($('#chartDonut'),
        ['已填报', '未填报'],
        [data.stats.reported, data.stats.unreported],
        ['#16a34a', '#dc2626']);
    };

    const rowIndex = {};
    (data.items || []).forEach((row) => { rowIndex[row.room_no] = row; });
    renderStats();
    App.state.lastStatus = data.stats.reported;
    await renderCharts();

    const tick = async () => {
      if (App.currentPage !== 'dashboard') return;
      try {
        const status = await App.api(`/api/reports/status?${App.classQuery()}`);
        App.state.lastStatus = status.stats.reported;
        const todayChip = $('#todayChip');
        if (todayChip) todayChip.textContent = `${data.today} 已填 ${status.stats.reported}/${status.stats.dorm_total}`;
        const fresh = await App.api(`/api/reports/dashboard?${App.classQuery()}`);
        Object.keys(fresh).forEach((k) => { data[k] = fresh[k]; });
        (data.items || []).forEach((row) => { rowIndex[row.room_no] = row; });
        renderStats();
      } catch (e) { /* 忽略 */ }
    };
    if (App.state.dashTimer) clearInterval(App.state.dashTimer);
    App.state.dashTimer = setInterval(tick, 20000);
    document.querySelectorAll('.nav-item').forEach((el) => el.addEventListener('click', () => {
      if (App.state.dashTimer) { clearInterval(App.state.dashTimer); App.state.dashTimer = null; }
    }, { once: true }));

    $('#todayChip').textContent = `${data.today} 已填 ${data.stats.reported}/${data.stats.dorm_total}`;
    const btn = $('#btnRefreshChart');
    if (btn) btn.onclick = () => App.reloadCurrent();
  },
});

/* 通用：宿舍详情弹窗（管理员可直接代填） */
App.openDormDetail = async function openDormDetail(dormId, day) {
  const detail = await App.api(`/api/reports/dorm/${dormId}?day=${day || App.today()}`);
  const members = detail.members || [];
  const report = detail.report;
  const html = `
    <div class="grid cols-2" style="gap:10px">
      <div>
        <div class="hint-text">寝室长</div>
        <div><b>${App.esc(detail.dorm.leader_name || '未指定')}</b> ${App.esc(detail.dorm.leader_phone || '')}</div>
      </div>
      <div>
        <div class="hint-text">填报状态</div>
        <div>${report ? App.statusChip(report.is_complete ? '齐全' : '缺人') + ` <span class="hint-text">${App.esc(report.submitted_at)}</span>` : '<span class="chip bad">未填报</span>'}</div>
      </div>
      <div>
        <div class="hint-text">填写来源</div>
        <div>${App.esc(report ? report.ip || '—' : '—')} · ${App.esc(report ? (report.device || '—') : '—')}</div>
      </div>
      <div>
        <div class="hint-text">寝室密码</div>
        <div>${detail.locked ? '<span class="chip warn">已设置（操作需寝室长账户）</span>' : '<span class="chip ok">未设置（谁都能填）</span>'}</div>
      </div>
    </div>
    <div class="table-wrap" style="margin-top:12px">
      <table>
        <thead><tr><th>姓名</th><th>学号</th><th>电话号</th><th>状态</th><th>原因</th></tr></thead>
        <tbody>${members.map((m) => `<tr>
          <td>${App.esc(m.name)}${m.role === '宿舍长' ? ' <span class="chip">宿舍长</span>' : ''}</td>
          <td>${App.esc(m.student_no || '—')}</td>
          <td>${App.esc(m.phone || '—')}</td>
          <td>${m.present ? App.statusChip('在寝') : App.statusChip('缺人')}</td>
          <td>${App.esc(m.reason || '')}</td>
        </tr>`).join('') || '<tr><td colspan="5" class="empty">该宿舍还没有人员信息</td></tr>'}</tbody>
      </table>
    </div>
    ${report && report.raw_message ? `<div class="hint-text" style="margin-top:10px">群消息原文：${App.esc(report.raw_message)}</div>` : ''}
    ${report && report.note ? `<div class="hint-text" style="margin-top:6px">备注：${App.esc(report.note)}</div>` : ''}
    <div class="hint-text" style="margin-top:10px">填报来源：${App.esc(report ? (report.source_text || '') : '—')} · 提交人：${App.esc(report ? report.submitter || '—' : '—')}${report && report.raw_message ? ` · 群消息原文：${App.esc(report.raw_message)}` : ''}</div>
  `;
  App.modal({
    title: `宿舍 ${detail.dorm.room_no} · ${day}`,
    html,
    hideOk: true,
    showCancel: true,
    cancelText: '关闭',
    footerExtra: `<button class="btn primary" id="btnGoReport">去填这间宿舍</button>`,
    onMount: (box) => {
      const go = box.querySelector('#btnGoReport');
      if (go) {
        go.onclick = async () => {
          App.closeModal();
          await App.navigate('report');
          const select = $('#reportDorm');
          if (select) { select.value = String(dormId); select.dispatchEvent(new Event('change')); }
        };
      }
    },
  });
};
