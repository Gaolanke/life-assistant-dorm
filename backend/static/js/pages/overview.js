/* 总览：登录后一屏看完今晚填报、班费和系统状态 */
App.page('overview', {
  async render(box) {
    box.innerHTML = '<div class="empty">加载中…</div>';
    const [today, fund, info] = await Promise.all([
      App.api(`/api/reports/today?${App.classQuery()}`).catch(() => null),
      App.api(`/api/fund/summary?${App.classQuery()}`).catch(() => null),
      App.api('/api/system/info').catch(() => null),
    ]);

    const stats = (today && today.stats) || {};
    const money = (n) => {
      const value = Number(n || 0);
      return Math.abs(value - Math.round(value)) < 0.005 ? String(Math.round(value)) : value.toFixed(2);
    };
    const missing = (today && today.missing) || [];
    const percent = stats.total ? Math.round(((stats.reported || 0) / stats.total) * 100) : 0;

    box.innerHTML = `
      <div class="grid cols-3" style="gap:14px">
        <div class="card stat-card">
          <div class="hint-text">今晚填报</div>
          <div class="stat-value">${stats.reported || 0}<span class="stat-unit">/ ${stats.total || 0} 间</span></div>
          <div class="progress"><div class="progress-bar" style="width:${percent}%"></div></div>
          <div class="hint-text">完成 ${percent}% · 未填 ${missing.length} 间</div>
        </div>
        <div class="card stat-card">
          <div class="hint-text">在寝 / 缺席</div>
          <div class="stat-value">${stats.present || 0}<span class="stat-unit">/ ${stats.absent || 0} 人</span></div>
          <div class="hint-text">应到 ${stats.checkins || 0} 人次</div>
        </div>
        <div class="card stat-card">
          <div class="hint-text">班费余额</div>
          <div class="stat-value">${money(fund && fund.balance)}<span class="stat-unit">元</span></div>
          <div class="hint-text">合计 ${money(fund && fund.total_fund)} · 已用 ${money(fund && fund.spent)}</div>
        </div>
      </div>

      <div class="grid cols-2" style="gap:14px">
        <div class="card">
          <div class="card-head"><h3>还没填的寝室</h3><span class="spacer"></span>
            <button class="btn tiny" id="ovGoPush">去催填</button></div>
          <div class="chips">${missing.length
            ? missing.map((d) => `<span class="chip bad">${App.esc(d.room_no)}</span>`).join('')
            : '<span class="chip ok">全部都填了 🎉</span>'}</div>
        </div>
        <div class="card">
          <div class="card-head"><h3>最近提交</h3><span class="spacer"></span>
            <button class="btn tiny" id="ovGoLogs">填写日志</button></div>
          <div class="table-wrap" style="max-height:240px;overflow:auto"><table>
            <thead><tr><th>时间</th><th>宿舍</th><th>状态</th><th>填表人</th></tr></thead>
            <tbody>${((today && today.recent) || []).slice(0, 8).map((r) => `<tr>
              <td>${App.esc((r.submitted_at || '').slice(11, 16) || r.submitted_at)}</td>
              <td>${App.esc(r.room_no)}</td>
              <td>${r.is_complete ? App.statusChip('齐全') : App.statusChip('缺人')}</td>
              <td>${App.esc(r.submitter || '匿名')}</td></tr>`).join('')
              || '<tr><td colspan="4" class="empty">今天还没有提交</td></tr>'}</tbody>
          </table></div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h3>系统状态</h3><span class="spacer"></span>
          <span class="chip">${App.esc((App.state.account && App.state.account.display_name) || 'admin')} 已登录</span></div>
        <div class="grid cols-4" style="gap:12px">
          <div><div class="hint-text">寝室 / 人员</div><b>${(info && info.counts && info.counts.dorms) || 0} 间 · ${(info && info.counts && info.counts.members) || 0} 人</b></div>
          <div><div class="hint-text">填报记录</div><b>${(info && info.counts && info.counts.reports) || 0} 条</b></div>
          <div><div class="hint-text">班费明细</div><b>${(fund && fund.entry_count) || 0} 条</b></div>
          <div><div class="hint-text">服务器时间</div><b>${App.esc((info && info.server_time) || '—')}</b></div>
        </div>
      </div>`;

    $('#ovGoPush').onclick = () => App.navigate('push');
    $('#ovGoLogs').onclick = () => App.navigate('logs');
  },
});
