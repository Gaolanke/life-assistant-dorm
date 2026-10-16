/* 统计图表：天 / 周 / 月 */
App.page('stats', {
  async render(box) {
    const state = { granularity: 'day', points: 14, anchor: App.today() };

    box.innerHTML = `
      <div class="card">
        <div class="toolbar">
          <div class="tabs" id="granTabs" style="margin:0">
            <button class="tab active" data-g="day">按天</button>
            <button class="tab" data-g="week">按周</button>
            <button class="tab" data-g="month">按月</button>
          </div>
          <span style="flex:1"></span>
          <label style="display:flex;gap:6px;align-items:center;font-size:13px">截止日期
            <input type="date" id="statAnchor" value="${state.anchor}" style="width:150px">
          </label>
          <label style="display:flex;gap:6px;align-items:center;font-size:13px">显示点数
            <input type="number" id="statPoints" value="14" min="3" max="60" style="width:80px">
          </label>
          <button class="btn tiny primary" id="btnStatApply">应用</button>
          <button class="btn tiny" id="btnExportRange">导出区间 Excel</button>
          <button class="btn tiny" id="btnExportZip">按天打包</button>
        </div>
      </div>

      <div class="grid cols-4" style="margin-bottom:16px" id="statKpis"></div>

      <div class="card">
        <div class="card-head"><h2 id="trendTitle">每日填报率与人数趋势</h2><span class="sub">填报率 = 已填报宿舍数 / 应填报宿舍数</span></div>
        <div class="chart-box"><canvas id="chartTrend"></canvas></div>
      </div>

      <div class="grid side">
        <div class="card">
          <div class="card-head"><h2>在寝 / 缺席人数</h2><span class="sub">看整体晚归情况</span></div>
          <div class="chart-box short"><canvas id="chartPeople"></canvas></div>
        </div>
        <div class="card">
          <div class="card-head"><h2>本月填报时间分布</h2><span class="sub">宿舍长习惯几点填</span></div>
          <div class="chart-box short"><canvas id="chartHourly"></canvas></div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>各宿舍填报情况</h2>
          <span class="sub" id="rankRange"></span>
          <span class="spacer"></span>
          <div class="tabs" style="margin:0">
            <button class="tab active" data-rank="week">本周</button>
            <button class="tab" data-rank="month">本月</button>
          </div>
        </div>
        <div class="table-wrap" style="max-height:420px;overflow:auto"><table id="rankTable"></table></div>
      </div>

      <div class="card">
        <div class="card-head"><h2 id="dayDetailTitle">当日各宿舍明细</h2><span class="spacer"></span><button class="btn tiny" id="btnExportDay">导出这一天</button></div>
        <div class="table-wrap" style="max-height:420px;overflow:auto"><table id="dayTable"></table></div>
      </div>
    `;

    const renderAll = async () => {
      const data = await App.api(`/api/reports/stats?granularity=${state.granularity}&anchor=${state.anchor}&points=${state.points}&day=${state.anchor}&${App.classQuery()}`);
      const items = data.items || [];
      const unit = { day: '天', week: '周', month: '月' }[state.granularity];
      $('#trendTitle').textContent = `每${unit}填报率与填报数量趋势`;

      const rates = items.map((i) => i.rate);
      const avgRate = rates.length ? (rates.reduce((a, b) => a + b, 0) / rates.length).toFixed(1) : '0';
      const best = items.reduce((a, b) => (b.rate > (a ? a.rate : -1) ? b : a), null);
      const worst = items.reduce((a, b) => (b.rate < (a ? a.rate : 101) ? b : a), null);
      const totalAbsent = items.reduce((sum, i) => sum + (i.absent || 0), 0);
      $('#statKpis').innerHTML = `
        <div class="card kpi blue"><span class="label">平均填报率</span><span class="value">${avgRate}<small>%</small></span><span class="hint">共 ${items.length} 个${unit}</span></div>
        <div class="card kpi green"><span class="label">最好的一天/周</span><span class="value" style="font-size:18px">${best ? App.esc(best.full_label || best.label) : '—'}</span><span class="hint">填报率 ${best ? best.rate : 0}%</span></div>
        <div class="card kpi red"><span class="label">最差的一天/周</span><span class="value" style="font-size:18px">${worst ? App.esc(worst.full_label || worst.label) : '—'}</span><span class="hint">填报率 ${worst ? worst.rate : 0}%</span></div>
        <div class="card kpi amber"><span class="label">累计缺席人次</span><span class="value">${totalAbsent}<small> 人次</small></span><span class="hint">区间内所有缺人记录</span></div>`;

      App.lineChart($('#chartTrend'), items.map((i) => i.label), [
        { label: '填报率 %', data: items.map((i) => i.rate), color: '#1f6feb', yAxisID: 'y' },
        { label: '已填报宿舍数', data: items.map((i) => i.reported), color: '#16a34a', type: 'bar', fill: false, yAxisID: 'y1' },
      ], { hasY1: true });
      App.lineChart($('#chartPeople'), items.map((i) => i.label), [
        { label: '在寝人数', data: items.map((i) => i.present), color: '#16a34a' },
        { label: '缺席人数', data: items.map((i) => i.absent), color: '#dc2626' },
      ], { type: 'bar' });
      App.barChart($('#chartHourly'), (data.hourly || []).map((i) => i.label), (data.hourly || []).map((i) => i.value), { label: '填报次数', color: '#7c3aed' });

      const renderRank = (key) => {
        const rows = key === 'week' ? data.ranking_week : data.ranking_month;
        $('#rankRange').textContent = key === 'week' ? '本周（周一至今）' : '本月（1 号至今）';
        $('#rankTable').innerHTML = `
          <thead><tr><th>宿舍</th><th>宿舍长</th><th>联系电话</th><th class="num">已填</th><th class="num">漏填</th><th style="min-width:130px">填报率</th><th class="num">缺勤天数</th><th class="num">缺勤人次</th><th>最近填报</th></tr></thead>
          <tbody>${(rows || []).map((r) => `<tr>
            <td><b>${App.esc(r.room_no)}</b></td>
            <td>${App.esc(r.leader_name || '—')}</td>
            <td>${App.esc(r.leader_phone || '—')}</td>
            <td class="num">${r.reported}/${r.days}</td>
            <td class="num" style="color:${r.missing ? '#dc2626' : '#16a34a'}">${r.missing}</td>
            <td>${App.progress(r.rate)}<span class="hint-text">${r.rate}%</span></td>
            <td class="num">${r.absent_days}</td>
            <td class="num">${r.absent_total}</td>
            <td>${App.esc(r.last_report || '—')}</td>
          </tr>`).join('') || '<tr><td colspan="9" class="empty">暂无数据</td></tr>'}</tbody>`;
      };
      renderRank('week');
      $$('[data-rank]').forEach((tab) => {
        tab.onclick = () => {
          $$('[data-rank]').forEach((t) => t.classList.toggle('active', t === tab));
          renderRank(tab.dataset.rank);
        };
      });

      const dayRows = data.dorm_rows || [];
      $('#dayDetailTitle').textContent = `${state.anchor}（${App.weekday(state.anchor)}）各宿舍明细`;
      $('#dayTable').innerHTML = `
        <thead><tr><th>宿舍</th><th>宿舍长</th><th>状态</th><th class="num">在寝/应到</th><th class="wrap">不在人员</th><th class="wrap">备注</th><th>填报人</th><th>时间</th><th>方式</th></tr></thead>
        <tbody>${dayRows.map((r) => `<tr>
          <td><b>${App.esc(r.room_no)}</b></td>
          <td>${App.esc(r.leader_name || '—')}</td>
          <td>${App.statusChip(r.status_text)}</td>
          <td class="num">${r.reported ? r.present_count : '—'}/${r.total_count}</td>
          <td class="wrap">${App.esc(r.absent_names || '')}</td>
          <td class="wrap">${App.esc(r.note || '')}</td>
          <td>${App.esc(r.submitter || '')}</td>
          <td>${App.esc(r.submitted_time || '')}</td>
          <td>${App.esc(r.source_text || '')}</td>
        </tr>`).join('')}</tbody>`;
    };

    $$('#granTabs .tab').forEach((tab) => {
      tab.onclick = async () => {
        state.granularity = tab.dataset.g;
        $$('#granTabs .tab').forEach((t) => t.classList.toggle('active', t === tab));
        state.points = state.granularity === 'day' ? 14 : state.granularity === 'week' ? 8 : 6;
        $('#statPoints').value = state.points;
        await renderAll();
      };
    });
    $('#btnStatApply').onclick = async () => {
      state.anchor = $('#statAnchor').value || App.today();
      state.points = Math.max(3, Math.min(60, Number($('#statPoints').value) || 14));
      await renderAll();
    };
    $('#btnExportDay').onclick = async () => {
      try {
        const name = await App.download(`/api/reports/export?day=${state.anchor}&${App.classQuery()}`, `宿舍填报_${state.anchor}.xlsx`);
        App.toast(`已导出 ${name}`, 'ok');
      } catch (e) { App.toast(e.message, 'err'); }
    };
    $('#btnExportRange').onclick = async () => {
      const start = App.shiftDate(-(state.points - 1), state.anchor);
      try {
        const name = await App.download(`/api/reports/export?start=${start}&end=${state.anchor}&${App.classQuery()}`, 'reports.xlsx');
        App.toast(`已导出 ${name}`, 'ok');
      } catch (e) { App.toast(e.message, 'err'); }
    };
    $('#btnExportZip').onclick = async () => {
      const start = App.shiftDate(-(state.points - 1), state.anchor);
      try {
        const name = await App.download(`/api/reports/export?start=${start}&end=${state.anchor}&as_zip=true&${App.classQuery()}`, 'reports.zip');
        App.toast(`已打包 ${name}`, 'ok');
      } catch (e) { App.toast(e.message, 'err'); }
    };

    await renderAll();
  },
});
