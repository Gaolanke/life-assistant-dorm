/* 入口页：选班级（多班级时）→ 选寝室 → 直接进去填写 */
App.page('home', {
  async render(box) {
    const state = {
      keyword: '',
      classId: Number(localStorage.getItem('dorm_public_class_id') || 0),
      visibleDorms: [],
    };

    box.innerHTML = `
      <div class="card hero">
        <div class="hero-main">
          <h2 id="homeTitle">请选择你的寝室</h2>
          <p class="hint-text" id="homeSub">点一下自己的寝室，直接开始今晚的填报，不需要账号。</p>
        </div>
        <div class="hero-side">
          <input id="homeSearch" placeholder="输入宿舍号快速查找，例如 6-213">
          <div class="hero-btns">
            <button class="btn primary" id="btnHomeGo">进入填报</button>
            <button class="btn" id="btnHomeLeader">我是寝室长（验证）</button>
          </div>
          <div class="hint-text" id="homeAdminHint"></div>
        </div>
      </div>

      <div class="card hidden" id="classCard">
        <div class="card-head">
          <h2>第一步：选择你的班级</h2>
          <span class="sub" id="classStats">—</span>
        </div>
        <div class="room-grid" id="classGrid"></div>
      </div>

      <div class="card" id="roomCard">
        <div class="card-head">
          <h2 id="roomCardTitle">全部寝室</h2>
          <span class="sub" id="homeStats">—</span>
          <span class="spacer"></span>
          <button class="btn tiny hidden" id="btnChangeClass">← 重选班级</button>
          <span class="chip" id="homeRoomChip">未选择</span>
        </div>
        <div class="room-grid" id="roomGrid"></div>
      </div>

      <div class="grid side" id="progressArea">
        <div class="card">
          <div class="card-head"><h2>今晚进度</h2><span class="spacer"></span><span class="chip" id="homeRate">—</span></div>
          <div id="homeProgress" class="hint-text">加载中…</div>
        </div>
        <div class="card">
          <div class="card-head"><h2>还差这些寝室没填</h2></div>
          <div id="homeMissing" class="hint-text">—</div>
        </div>
      </div>`;

    const selected = () => App.state.roomNo || '';

    /* 从宿舍列表里汇总出班级清单（顺序保持不变） */
    const classesOf = (dorms) => {
      const map = new Map();
      dorms.forEach((d) => {
        const cid = d.class_id || 0;
        if (!map.has(cid)) map.set(cid, { id: cid, name: d.class_name || '默认班级', rooms: 0, members: 0 });
        const c = map.get(cid);
        c.rooms += 1;
        c.members += d.member_count || 0;
      });
      return Array.from(map.values());
    };

    const setPublicClass = (cid) => {
      state.classId = Number(cid) || 0;
      if (state.classId) localStorage.setItem('dorm_public_class_id', String(state.classId));
      else localStorage.removeItem('dorm_public_class_id');
    };

    const renderRooms = () => {
      const dorms = state.visibleDorms || [];
      const keyword = state.keyword.trim().toLowerCase();
      const list = keyword
        ? dorms.filter((d) => (`${d.room_no}${d.room_label}${d.building}${d.leader_name}`).toLowerCase().includes(keyword))
        : dorms;
      const current = selected();
      $('#homeRoomChip').textContent = current ? `已选：${current}` : '未选择';
      $('#homeRoomChip').className = `chip ${current ? 'ok' : 'warn'}`;
      $('#roomGrid').innerHTML = list.length
        ? list.map((d) => `
          <button class="room-card ${d.room_no === current ? 'active' : ''}" data-room="${App.attr(d.room_no)}" data-id="${d.id}">
            <span class="room-no">${App.esc(d.room_no)}${d.locked ? ' <span class="lock-tag">🔒 需密码</span>' : ''}</span>
            <span class="room-meta">${App.esc(d.leader_name || '未指定寝室长')} · ${d.member_count} 人</span>
            <span class="room-label">${App.esc(d.room_label || d.building || '')}</span>
          </button>`).join('')
        : '<div class="empty">没有匹配的寝室</div>';
      $$('#roomGrid .room-card').forEach((btn) => {
        btn.onclick = async () => {
          App.setRoom(Number(btn.dataset.id), btn.dataset.room);
          await App.navigate('report');
        };
      });
    };

    const loadProgress = async (classId) => {
      try {
        const today = await App.api(`/api/reports/today${classId ? `?class_id=${classId}` : ''}`);
        const s = today.stats;
        $('#homeRate').textContent = `${s.rate}%`;
        $('#homeRate').className = `chip ${App.rateClass(s.rate)}`;
        $('#homeProgress').innerHTML = `
          已填报 <b>${s.reported}</b> / ${s.dorm_total} 间<br>
          在寝 <b>${s.present}</b> / ${s.total} 人，缺席 <b style="color:#dc2626">${s.absent}</b> 人次`;
        $('#homeMissing').innerHTML = s.missing_rooms.length
          ? `<span style="color:#dc2626">${App.esc(s.missing_rooms.join('、'))}</span>`
          : '全部寝室已填报 ✅';
      } catch (e) { /* 忽略 */ }
    };

    /* 按「是否多班级 / 是否已选班级」切换三种视图 */
    const renderView = async () => {
      const allDorms = App.state.dorms || [];
      const classes = classesOf(allDorms);
      const multi = classes.length > 1;
      if (multi && state.classId && !classes.some((c) => c.id === state.classId)) setPublicClass(0);
      const picking = multi && !state.classId;
      const currentClass = multi ? classes.find((c) => c.id === state.classId) : null;

      // 班级卡片（多班级才出现）
      $('#classCard').classList.toggle('hidden', !multi);
      if (multi) {
        $('#classStats').textContent = `共 ${classes.length} 个班`;
        $('#classGrid').innerHTML = classes.map((c) => `
          <button class="room-card ${c.id === state.classId ? 'active' : ''}" data-cid="${c.id}">
            <span class="room-no">🏫 ${App.esc(c.name)}</span>
            <span class="room-meta">${c.rooms} 间寝室 · ${c.members} 名同学</span>
            <span class="room-label">${c.id === state.classId ? '当前班级' : '点击进入'}</span>
          </button>`).join('');
        $$('#classGrid .room-card').forEach((btn) => {
          btn.onclick = async () => {
            setPublicClass(Number(btn.dataset.cid));
            await renderView();
          };
        });
      }

      // 寝室区：多班级未选班时隐藏，选班后只显示本班寝室
      const visibleDorms = multi
        ? allDorms.filter((d) => (d.class_id || 0) === state.classId)
        : allDorms;
      $('#roomCard').classList.toggle('hidden', picking);
      $('#progressArea').classList.toggle('hidden', picking);
      $('#btnChangeClass').classList.toggle('hidden', !multi);
      $('#roomCardTitle').textContent = currentClass ? `${currentClass.name} 的寝室` : '全部寝室';
      $('#homeTitle').textContent = picking ? '请选择你的班级' : '请选择你的寝室';
      $('#homeSub').textContent = picking
        ? '先点自己的班级，再选寝室；以后打开会记住你的选择。'
        : '点一下自己的寝室，直接开始今晚的填报，不需要账号。';

      state.visibleDorms = visibleDorms;
      renderRooms();

      const memberTotal = visibleDorms.reduce((sum, d) => sum + (d.member_count || 0), 0);
      $('#homeStats').innerHTML = `共 <b>${visibleDorms.length}</b> 间寝室 · <b>${memberTotal}</b> 名同学`;
      await loadProgress(multi ? state.classId : 0);
    };

    const load = async () => {
      const data = await App.api('/api/dorms?with_members=false&active_only=true&class_id=-1');
      App.state.dorms = (data.items || []).filter((d) => d.active !== false);
      await renderView();
    };

    $('#homeSearch').oninput = (e) => {
      state.keyword = e.target.value;
      renderRooms();
    };
    $('#homeSearch').onkeydown = (e) => {
      if (e.key === 'Enter') {
        const first = $('#roomGrid .room-card');
        if (first) first.click();
      }
    };
    $('#btnChangeClass').onclick = async () => {
      setPublicClass(0);
      state.keyword = '';
      $('#homeSearch').value = '';
      await renderView();
    };
    $('#btnHomeGo').onclick = async () => {
      if (!App.state.roomNo) {
        App.toast('请先在上面选择你的寝室', 'err');
        return;
      }
      await App.navigate('report');
    };
    $('#btnHomeLeader').onclick = () => App.showLeaderVerify(async () => { await App.navigate('report'); });
    const hint = $('#homeAdminHint');
    if (hint) {
      const adminUrl = App.adminUrl('');
      hint.innerHTML = `管理员请走：<a href="${App.esc(adminUrl)}" target="_blank">${App.esc(adminUrl)}</a>`;
    }

    await load();
  },
});
