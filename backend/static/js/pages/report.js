/* 每日填报表单：选好寝室 -> 直接勾选每人是否在寝 */
App.page('report', {
  async render(box) {
    const day = App.today();
    const leader = App.state.leader;
    const usable = (App.state.dorms || []).filter((d) => d.active !== false);
    const dormList = usable.length ? usable : (App.state.dorms || []);
    if (!dormList.length) {
      box.innerHTML = `<div class="card"><div class="empty">还没有寝室数据，请先到「宿舍与人员」导入名单。</div></div>`;
      return;
    }
    // 寝室长：进入专属界面，只能看到 / 填写自己寝室
    // 管理员：可以填任何寝室（在管理端口）
    // 普通同学：用入口页选的寝室，没选就用第一个
    let defaultDormId = leader ? leader.dorm_id : (App.state.roomId || dormList[0].id);
    if (!dormList.some((d) => d.id === defaultDormId)) defaultDormId = dormList[0].id;
    const lockedRoom = leader ? leader.room_no : '';
    const leaderDorm = leader ? dormList.find((d) => d.id === leader.dorm_id) : null;

    box.innerHTML = `
      <div class="grid side">
        <div>
          <div class="card">
            <div class="card-head">
              <h2>📝 今晚人员情况填报</h2>
              <span class="chip ok" id="reportRoomChip">当前寝室：—</span>
              <span class="spacer"></span>
              <button class="btn tiny ${leader ? 'hidden' : ''}" id="btnBackHome">换寝室</button>
              <button class="btn tiny" id="btnAllPresent">全部在寝</button>
            </div>
            ${leader ? `<div class="notice">🧑‍🎓 你正在用寝室长界面（${App.esc(leader.room_no)}），只能查看和填写自己寝室的信息。</div>` : ''}
            <div class="notice hidden" id="lockNotice"></div>
            <div class="grid cols-3">
              <label class="field"><span>填报日期</span><input type="date" id="reportDate" value="${day}" max="${day}"></label>
              <label class="field"><span>寝室 <b>*</b></span>
                <select id="reportDorm" ${lockedRoom ? 'disabled' : ''}>
                  ${(leader && leaderDorm ? [leaderDorm] : dormList).map((d) => `<option value="${d.id}" ${d.id === defaultDormId ? 'selected' : ''}>${App.esc(d.room_label || d.label || d.room_no)}${d.leader_name ? ` · ${App.esc(d.leader_name)}` : ''}</option>`).join('')}
                </select>
                ${lockedRoom ? `<div class="hint-text">已按寝室长身份锁定 ${App.esc(lockedRoom)}</div>` : '<div class="hint-text">没找到自己的寝室？点左侧「换寝室」重新选</div>'}
              </label>
              <label class="field"><span>填表人（你）</span>
                <input id="reportSubmitter" value="${App.attr(App.state.submitter)}" placeholder="名字或宿舍号，可留空">
              </label>
            </div>
            <div class="card-head" style="margin:6px 0 8px">
              <h3>人员是否齐全</h3>
              <span class="spacer"></span>
              <span class="chip" id="memberCount">—</span>
            </div>
            <div id="memberList"></div>
            <label class="field" style="margin-top:12px">
              <span>备注（不在的人员、意外问题、请假原因等）<b>*</b></span>
              <textarea id="reportNote" placeholder="例如：张三回家（已跟辅导员请假）；李四发烧去校医院，家长已知晓。"></textarea>
              <div class="hint-text">有人不在时请写清楚是谁、什么原因；没有问题可以填“无”。</div>
            </label>
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
              <button class="btn primary" id="btnSubmit">提交今晚填报</button>
              <button class="btn" id="btnReset">全部重置为「在寝」</button>
              <span class="chip gray" id="lastSubmitInfo">—</span>
            </div>
            <div class="hint-text">
              提交会<b>覆盖</b>本宿舍今天已有的记录，重复点击不会多算人数。填错了直接重新提交即可；
              想从头填就点「全部重置为「在寝」」。
            </div>
          </div>
        </div>

        <div>
          <div class="card">
            <div class="card-head"><h3>今日进度</h3><span class="spacer"></span><span class="chip" id="sideRate">—</span></div>
            <div id="sideStats" class="hint-text">加载中…</div>
          </div>
          <div class="card">
            <div class="card-head"><h3>还没填报的宿舍</h3></div>
            <div id="sideMissing" class="hint-text">—</div>
          </div>
          <div class="card ${leader ? 'hidden' : ''}">
            <div class="card-head"><h3>分享到宿舍群</h3></div>
            <div class="hint-text">把这个网址发到宿舍群，谁都能直接打开填报：</div>
            <div class="logbox" style="margin-top:8px" id="shareUrl"></div>
            <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn tiny" id="btnCopyUrl">复制网址</button>
              <button class="btn tiny" id="btnShowQr">显示二维码</button>
            </div>
            <div id="qrBox" style="margin-top:12px;text-align:center"></div>
          </div>
        </div>
      </div>`;

    const state = { members: [], dormId: defaultDormId, reasons: [] };

    // 寝室已设密码：未验证的访客不能填报，先引导验证
    const renderLock = () => {
      const wrap = $('#lockNotice');
      const btn = $('#btnSubmit');
      const locked = state.locked && !state.canWrite;
      if (wrap) {
        wrap.classList.toggle('hidden', !locked);
        if (locked) {
          wrap.innerHTML = `🔒 <b>这间寝室已由寝室长设置密码</b>，填报需要先用寝室长账户验证。
            <button class="btn tiny primary" id="btnLockVerify" style="margin-left:8px">立即验证</button>`;
          const verifyBtn = $('#btnLockVerify');
          if (verifyBtn) verifyBtn.onclick = () => App.showLeaderVerify(async () => { await loadDorm(state.dormId); });
        }
      }
      if (btn) {
        btn.disabled = locked;
        btn.textContent = locked ? '请先验证寝室长账户' : '提交今晚填报';
      }
      ['#btnAllPresent', '#reportNote', '#reportDorm'].forEach((selector) => {
        const el = $(selector);
        if (el) el.disabled = locked;
      });
    };

    const renderMembers = () => {      const list = $('#memberList');
      if (!state.members.length) {
        list.innerHTML = '<div class="empty">这个宿舍还没有人员信息，请到「宿舍与人员」添加或导入名单</div>';
        $('#memberCount').textContent = '0 人';
        return;
      }
      list.innerHTML = state.members.map((m) => `
        <div class="member-row ${m.present ? '' : 'absent'}" data-id="${m.id}">
          <div class="member-main">
            <strong>${App.esc(m.name)}${m.role === '宿舍长' ? ' <span class="chip">宿舍长</span>' : ''}</strong>
            <span>${App.esc(m.student_no || '未填学号')} · ${App.esc(m.phone || '未填电话')}</span>
            ${m.present ? '' : `<div class="reason-line">
              <select class="reasonSelect" data-id="${m.id}">
                ${state.reasons.map((r) => `<option ${r === m.reason ? 'selected' : ''}>${App.esc(r)}</option>`).join('')}
              </select>
              <input class="reasonInput" data-id="${m.id}" placeholder="补充说明（可选）" value="${App.attr(m.reasonNote || '')}">
            </div>`}
          </div>
          <div class="seg">
            <button class="on" data-act="present" data-id="${m.id}">在寝</button>
            <button class="off" data-act="absent" data-id="${m.id}">不在</button>
          </div>
        </div>`).join('');

      state.members.forEach((m) => {
        const row = list.querySelector(`.member-row[data-id="${m.id}"]`);
        const btnOn = row.querySelector('[data-act="present"]');
        const btnOff = row.querySelector('[data-act="absent"]');
        btnOn.classList.toggle('on', m.present);
        btnOff.classList.toggle('on', !m.present);
        btnOn.onclick = () => { m.present = true; renderMembers(); };
        btnOff.onclick = () => { m.present = false; if (!m.reason) m.reason = state.reasons[0] || ''; renderMembers(); };
        const sel = row.querySelector('.reasonSelect');
        if (sel) sel.onchange = () => { m.reason = sel.value; };
        const inp = row.querySelector('.reasonInput');
        if (inp) inp.oninput = () => { m.reasonNote = inp.value; };
      });
      const absent = state.members.filter((m) => !m.present).length;
      $('#memberCount').innerHTML = `应到 <b>${state.members.length}</b> 人 · 不在 <b style="color:${absent ? '#dc2626' : '#16a34a'}">${absent}</b> 人`;
    };

    const loadDorm = async (dormId) => {
      if (!dormId) { state.members = []; renderMembers(); return; }
      state.dormId = dormId;
      const dorm = (App.state.dorms || []).find((d) => d.id === Number(dormId));
      if (dorm && !App.state.leader) App.setRoom(dorm.id, dorm.room_no);
      const chip = $('#reportRoomChip');
      if (chip && dorm) chip.textContent = `当前寝室：${dorm.room_no}`;
      const detail = await App.api(`/api/reports/dorm/${dormId}?day=${$('#reportDate').value || day}`);
      state.locked = !!detail.locked;
      state.canWrite = detail.can_write !== false;
      renderLock();
      state.reasons = detail.absence_reasons && detail.absence_reasons.length ? detail.absence_reasons : ['回家', '病假', '事假', '外出', '其他'];
      state.members = (detail.members || []).map((m) => ({
        id: m.id, name: m.name, student_no: m.student_no, phone: m.phone, role: m.role,
        present: m.present, reason: m.reason || '', reasonNote: '',
      }));
      const report = detail.report;
      $('#lastSubmitInfo').innerHTML = report
        ? `${report.submitted_at ? report.submitted_at.slice(11, 16) : ''} 已由 ${App.esc(report.submitter || '匿名')} 填报（${App.esc(report.source_text || '')}）`
        : '今晚还没填报';
      $('#reportNote').value = report ? report.note || '' : '';
      if (report && !report.is_complete && report.absent_names) {
        const names = report.absent_names.split(/[、,，]/).map((s) => s.trim()).filter(Boolean);
        state.members.forEach((m) => { m.present = !names.some((n) => n && (m.name === n || n.includes(m.name))); });
      }
      renderMembers();
    };

    const loadSide = async () => {
      try {
        const status = await App.api(`/api/reports/today?day=${$('#reportDate').value || day}`);
        const s = status.stats;
        $('#sideRate').textContent = `${s.rate}%`;
        $('#sideRate').className = `chip ${App.rateClass(s.rate)}`;
        $('#sideStats').innerHTML = `
          已填报 <b>${s.reported}</b> / ${s.dorm_total} 间<br>
          在寝 <b>${s.present}</b> / ${s.total} 人，缺席 <b style="color:#dc2626">${s.absent}</b> 人次`;
        $('#sideMissing').innerHTML = s.missing_rooms.length
          ? `<span style="color:#dc2626">${App.esc(s.missing_rooms.join('、'))}</span>`
          : '全部宿舍已填报 ✅';
      } catch (e) { /* 忽略 */ }
    };

    $('#reportDorm').value = String(defaultDormId);
    $('#reportDorm').onchange = (e) => loadDorm(Number(e.target.value));
    $('#btnBackHome').onclick = async () => { location.hash = '#/home'; await App.navigate('home'); };
    $('#reportDate').onchange = async () => { await loadDorm(state.dormId); await loadSide(); };
    $('#reportSubmitter').onchange = (e) => App.setSubmitter(e.target.value);
    $('#btnAllPresent').onclick = () => {
      state.members.forEach((m) => { m.present = true; });
      renderMembers();
      App.toast('已把所有人标记为在寝，提交前请确认', 'ok');
    };
    $('#shareUrl').textContent = `${location.origin}/#/report`;
    $('#btnCopyUrl').onclick = () => App.copy(`${location.origin}/#/report`);
    $('#btnShowQr').onclick = () => {
      const target = `${location.origin}/#/report`;
      const img = new Image();
      img.src = `/api/system/qrcode?text=${encodeURIComponent(target)}`;
      img.style.maxWidth = '220px';
      img.onerror = () => { $('#qrBox').innerHTML = '<div class="hint-text">二维码生成失败，直接复制网址分享即可</div>'; };
      $('#qrBox').innerHTML = '';
      $('#qrBox').appendChild(img);
    };

    $('#btnSubmit').onclick = async () => {
      if (state.submitting) return;                       // 防止连点（双保险）
      if (!state.members.length) { App.toast('这个宿舍还没有人员，无法填报', 'err'); return; }
      const submitter = $('#reportSubmitter').value.trim();
      App.setSubmitter(submitter);
      const note = $('#reportNote').value.trim();
      const absent = state.members.filter((m) => !m.present);
      if (absent.length && !note) { App.toast('有人不在时，请在备注里写清原因', 'err'); return; }
      const payload = {
        dorm_id: state.dormId,
        report_date: $('#reportDate').value || day,
        is_complete: absent.length === 0,
        absent_names: absent.map((m) => m.name).join('、'),
        note,
        submitter,
        checkins: state.members.map((m) => ({
          member_id: m.id, name: m.name, present: m.present,
          reason: m.present ? '' : [m.reason, m.reasonNote].filter(Boolean).join(' '),
        })),
      };
      const btn = $('#btnSubmit');
      state.submitting = true;
      btn.disabled = true;
      const original = btn.textContent;
      btn.textContent = '提交中…';
      try {
        const res = await App.api('/api/reports/submit', 'POST', payload);
        App.toast(res.message || '提交成功', 'ok');
        await loadSide();
        await loadDorm(state.dormId);
      } catch (e) {
        App.toast(e.message || '提交失败', 'err');
      } finally {
        state.submitting = false;
        btn.disabled = false;
        btn.textContent = original;
      }
    };

    // 重置：全部标记为在寝、清空备注与原因（只改页面，不写库；要保存得点提交）
    const btnReset = $('#btnReset');
    if (btnReset) {
      btnReset.onclick = () => {
        if (state.submitting) return;
        state.members = state.members.map((m) => ({ ...m, present: true, reason: '', reasonNote: '' }));
        const noteEl = $('#reportNote');
        if (noteEl) noteEl.value = '';
        renderMembers();
        App.toast('已重置为全部在寝，确认后点提交覆盖', 'ok');
      };
    }

    await loadDorm(state.dormId);
    await loadSide();
  },
});
