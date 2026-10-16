/* 宿舍与人员管理 */
App.page('dorms', {
  async render(box) {
    const client = App.state.client;
    const state = { keyword: '', expanded: new Set() };

    box.innerHTML = `
      <div class="card">
        <div class="toolbar">
          <input id="dormSearch" placeholder="搜索宿舍号 / 姓名 / 学号 / 电话" style="width:230px">
          <button class="btn tiny primary" id="btnSearchDorm">搜索</button>
          <span style="flex:1"></span>
          <button class="btn tiny primary" id="btnImport">📥 导入人员信息</button>
          <button class="btn tiny" id="btnTemplate">下载导入模板</button>
          <button class="btn tiny" id="btnExportMembers">导出全部名单</button>
          <button class="btn tiny" id="btnAddDorm">＋ 新增宿舍</button>
        </div>
        <div class="hint-text" id="dormSummary">加载中…</div>
      </div>

      <div class="card">
        <div class="card-head">
          <h2>宿舍列表</h2>
          <span class="sub">点“成员”可以逐个添加、编辑、删除人员</span>
          <span class="spacer"></span>
          <span class="chip" id="dormCount">—</span>
        </div>
        <div class="table-wrap" style="max-height:600px;overflow:auto"><table id="dormTable"></table></div>
      </div>`;

    const load = async () => {
      const dorms = await App.api(`/api/dorms?with_members=true&active_only=false&${App.classQuery()}`);
      App.state.dorms = dorms.items || [];
      const keyword = state.keyword.trim().toLowerCase();
      let items = App.state.dorms;
      if (keyword) {
        items = items.filter((d) => {
          const hay = `${d.room_no}${d.building}${d.leader_name}${d.leader_phone}` +
            (d.members || []).map((m) => `${m.name}${m.student_no}${m.phone}`).join('');
          return hay.toLowerCase().includes(keyword);
        });
      }
      $('#dormCount').textContent = `${items.length} 间宿舍`;
      $('#dormSummary').innerHTML = `共 <b>${dorms.total}</b> 间宿舍、<b>${dorms.member_total}</b> 名人员。所有内容都可以直接编辑修改，不需要登录。`;

      const rows = items.map((d) => {
        const expanded = state.expanded.has(d.id);
        const members = d.members || [];
        return `
          <tr data-dorm="${d.id}">
            <td><b>${App.esc(d.room_no)}</b>${d.active ? '' : ' <span class="chip gray">已停用</span>'}${d.room_label ? `<div class="hint-text">${App.esc(d.room_label)}</div>` : ''}</td>
            <td>${App.esc(d.building || '—')}</td>
            <td>${App.esc(d.leader_name || '—')}</td>
            <td>${App.esc(d.leader_phone || '—')}</td>
            <td>${App.esc(d.qq_group_id || '—')}</td>
            <td class="num">${d.member_count}</td>
            <td>${d.leader_name ? '<span class="chip ok">已指定</span>' : '<span class="chip warn">未指定</span>'}</td>
            <td class="wrap">${App.esc(d.note || '')}</td>
            <td>
              <button class="btn tiny" data-act="toggle" data-id="${d.id}">${expanded ? '收起' : '成员'}</button>
              <button class="btn tiny" data-act="edit" data-id="${d.id}">编辑</button>
              <button class="btn tiny" data-act="addMember" data-id="${d.id}">加人</button>
              <button class="btn tiny danger" data-act="del" data-id="${d.id}">删除</button>
            </td>
          </tr>
          ${expanded ? `<tr><td colspan="9" style="background:#fafcff">
            <div class="table-wrap"><table>
              <thead><tr><th>姓名</th><th>学号</th><th>电话号</th><th>宿舍号</th><th>身份</th><th>备注</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>${members.map((m) => `<tr>
                <td><b>${App.esc(m.name)}</b></td>
                <td>${App.esc(m.student_no || '—')}</td>
                <td>${App.esc(m.phone || '—')}</td>
                <td>${App.esc(m.room_no || d.room_no)}</td>
                <td>${App.esc(m.role || '成员')}</td>
                <td class="wrap">${App.esc(m.note || '')}</td>
                <td>${m.active ? '<span class="chip ok">在册</span>' : '<span class="chip gray">已移除</span>'}</td>
                <td>
                  <button class="btn tiny" data-act="editMember" data-id="${m.id}" data-dorm="${d.id}">编辑</button>
                  <button class="btn tiny" data-act="setLeader" data-id="${m.id}" data-dorm="${d.id}">设为宿舍长</button>
                  <button class="btn tiny danger" data-act="delMember" data-id="${m.id}" data-name="${App.attr(m.name)}">删除</button>
                </td>
              </tr>`).join('') || '<tr><td colspan="8" class="empty">这个宿舍还没有成员，点“加人”或“导入人员信息”</td></tr>'}</tbody>
            </table></div>
          </td></tr>` : ''}`;
      }).join('');

      $('#dormTable').innerHTML = `
        <thead><tr><th>宿舍号</th><th>楼栋</th><th>宿舍长</th><th>电话</th><th>QQ群号</th><th class="num">人数</th><th>宿舍长</th><th class="wrap">备注</th><th>操作</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="9" class="empty">还没有宿舍，点右上角“导入人员信息”或“新增宿舍”开始</td></tr>'}</tbody>`;

      const find = (id) => App.state.dorms.find((d) => d.id === Number(id));
      $$('#dormTable [data-act]').forEach((btn) => {
        const act = btn.dataset.act;
        const id = Number(btn.dataset.id);
        btn.onclick = async () => {
          if (act === 'toggle') {
            if (state.expanded.has(id)) state.expanded.delete(id); else state.expanded.add(id);
            await load();
          } else if (act === 'edit') {
            App.editDorm(find(id), load);
          } else if (act === 'addMember') {
            App.editMember(null, id, load);
          } else if (act === 'editMember') {
            const dorm = find(Number(btn.dataset.dorm));
            const member = (dorm.members || []).find((m) => m.id === id);
            App.editMember(member, Number(btn.dataset.dorm), load);
          } else if (act === 'delMember') {
            App.confirmBox(`删除人员 ${btn.dataset.name}？删除后该宿舍应到人数会减少。`, async () => {
              await App.api(`/api/members/${id}`, 'DELETE');
              App.toast('已删除', 'ok');
              await load();
            }, '删除');
          } else if (act === 'setLeader') {
            const dormId = Number(btn.dataset.dorm);
            const res = await App.api(`/api/dorms/${dormId}/leader?member_id=${id}`, 'POST');
            App.toast(res.message || '已设为宿舍长', 'ok');
            await load();
          } else if (act === 'del') {
            const dorm = find(id);
            App.modal({
              title: `删除宿舍 ${dorm.room_no}`,
              okText: '确认删除',
              html: `<div class="hint-text">“停用”会保留历史填报记录（推荐）；“彻底删除”会连同人员、填报记录一起删掉，无法恢复。</div>
                <label class="field" style="margin-top:10px"><span>操作方式</span>
                  <select id="delMode">
                    <option value="soft">停用宿舍（保留历史填报数据）</option>
                    <option value="hard">彻底删除宿舍及其人员、填报记录</option>
                  </select>
                </label>`,
              onOk: async (modalBox) => {
                const mode = modalBox.querySelector('#delMode').value;
                const res = await App.api(`/api/dorms/${id}?purge_reports=${mode === 'hard'}`, 'DELETE');
                App.toast(res.message || '已处理', 'ok');
                await load();
                return true;
              },
            });
          }
        };
      });
      App.applyPermission();
    };

    $('#btnSearchDorm').onclick = async () => { state.keyword = $('#dormSearch').value; await load(); };
    $('#dormSearch').onkeydown = async (e) => { if (e.key === 'Enter') { state.keyword = e.target.value; await load(); } };
    $('#btnAddDorm').onclick = () => App.editDorm(null, load);
    $('#btnTemplate').onclick = async () => {
      try {
        await App.download('/api/members/template', 'member_template.xlsx');
        App.toast('模板已下载', 'ok');
      } catch (e) { App.toast(e.message, 'err'); }
    };
    $('#btnExportMembers').onclick = async () => {
      try {
        await App.download(`/api/members/export?${App.classQuery()}`, 'members.xlsx');
        App.toast('名单已导出', 'ok');
      } catch (e) { App.toast(e.message, 'err'); }
    };
    $('#btnImport').onclick = () => App.showImport(load);

    await load();
  },
});

/* 新增 / 编辑宿舍 */
App.editDorm = function editDorm(dorm, after) {
  const isNew = !dorm;
  App.modal({
    title: isNew ? '新增宿舍' : `编辑宿舍 ${dorm.room_no}`,
    okText: '保存',
    html: `
      <div class="grid cols-2" style="gap:10px">
        ${App.field('宿舍号', `<input id="fRoom" value="${App.attr(dorm ? dorm.room_no : '')}" placeholder="例如 207 或 3-201">`, '用于识别宿舍，也用于群里回消息填报', true)}
        ${App.field('楼栋', `<input id="fBuilding" value="${App.attr(dorm ? dorm.building : '')}" placeholder="例如 6号楼">`)}
      </div>
      ${App.field('完整宿舍名称（选填）', `<input id="fLabel" value="${App.attr(dorm ? dorm.room_label : '')}" placeholder="例如 新区校区6号学生公寓207">`, '填了就按这个名字显示和汇报')}
      ${isNew
        ? App.field('所属班级', `<select id="fClass">
            ${(App.state.classes || []).map((c) => `<option value="${c.id}" ${c.id === (App.state.classId || 0) ? 'selected' : ''}>${App.esc(c.name)}</option>`).join('') || '<option value="0">默认班级</option>'}
          </select>`, '宿舍创建后不能更换班级')
        : App.field('所属班级', `<input value="${App.attr(dorm.class_name || '默认班级')}" disabled>`, '宿舍创建后不能更换班级')}
      <div class="grid cols-2" style="gap:10px">
        ${App.field('宿舍长姓名', `<input id="fLeader" value="${App.attr(dorm ? dorm.leader_name : '')}">`)}
        ${App.field('宿舍长电话', `<input id="fPhone" value="${App.attr(dorm ? dorm.leader_phone : '')}">`)}
      </div>
      <div class="grid cols-2" style="gap:10px">
        ${App.field('QQ 群号', `<input id="fGroup" value="${App.attr(dorm ? dorm.qq_group_id : '')}" placeholder="该宿舍所在群，用于群消息填报">`, '留空则用系统默认汇报群号')}
        ${App.field('排序', `<input id="fSort" type="number" value="${dorm ? dorm.sort_order : 0}">`)}
      </div>
      ${App.field('备注', `<textarea id="fNote">${App.esc(dorm ? dorm.note : '')}</textarea>`)}
      <label class="field"><span>状态</span><select id="fActive">
        <option value="1" ${!dorm || dorm.active ? 'selected' : ''}>启用</option>
        <option value="0" ${dorm && !dorm.active ? 'selected' : ''}>停用</option>
      </select></label>`,
    onOk: async (box) => {
      const payload = {
        room_no: box.querySelector('#fRoom').value.trim(),
        room_label: box.querySelector('#fLabel').value.trim(),
        building: box.querySelector('#fBuilding').value.trim(),
        leader_name: box.querySelector('#fLeader').value.trim(),
        leader_phone: box.querySelector('#fPhone').value.trim(),
        qq_group_id: box.querySelector('#fGroup').value.trim(),
        sort_order: Number(box.querySelector('#fSort').value) || 0,
        note: box.querySelector('#fNote').value.trim(),
        active: box.querySelector('#fActive').value === '1',
      };
      if (!payload.room_no) { App.toast('宿舍号不能为空', 'err'); return false; }
      if (isNew) {
        payload.class_id = Number(box.querySelector('#fClass').value) || 0;
        await App.api('/api/dorms', 'POST', payload);
      } else {
        await App.api(`/api/dorms/${dorm.id}`, 'PUT', payload);
      }
      App.toast('已保存', 'ok');
      await App.loadBase();
      await after();
      return true;
    },
  });
};

/* 新增 / 编辑成员 */
App.editMember = function editMember(member, dormId, after) {
  const isNew = !member;
  App.modal({
    title: isNew ? '添加人员' : `编辑 ${member.name}`,
    okText: '保存',
    html: `
      <div class="grid cols-2" style="gap:10px">
        ${App.field('姓名', `<input id="mName" value="${App.attr(member ? member.name : '')}">`, '', true)}
        ${App.field('学号', `<input id="mNo" value="${App.attr(member ? member.student_no : '')}">`)}
      </div>
      <div class="grid cols-2" style="gap:10px">
        ${App.field('电话号', `<input id="mPhone" value="${App.attr(member ? member.phone : '')}">`)}
        ${App.field('宿舍号', `<input id="mRoom" value="${App.attr(member ? member.room_no : '')}" placeholder="留空自动用宿舍号">`)}
      </div>
      <div class="grid cols-2" style="gap:10px">
        ${App.field('身份', `<select id="mRole">
          <option value="成员" ${!member || member.role !== '宿舍长' ? 'selected' : ''}>成员</option>
          <option value="宿舍长" ${member && member.role === '宿舍长' ? 'selected' : ''}>宿舍长</option>
        </select>`)}
        ${App.field('状态', `<select id="mActive">
          <option value="1" ${!member || member.active ? 'selected' : ''}>在册</option>
          <option value="0" ${member && !member.active ? 'selected' : ''}>已移除</option>
        </select>`)}
      </div>
      ${App.field('备注', `<textarea id="mNote">${App.esc(member ? member.note : '')}</textarea>`)}`,
    onOk: async (box) => {
      const payload = {
        name: box.querySelector('#mName').value.trim(),
        student_no: box.querySelector('#mNo').value.trim(),
        phone: box.querySelector('#mPhone').value.trim(),
        room_no: box.querySelector('#mRoom').value.trim(),
        role: box.querySelector('#mRole').value,
        active: box.querySelector('#mActive').value === '1',
        note: box.querySelector('#mNote').value.trim(),
      };
      if (!payload.name) { App.toast('姓名不能为空', 'err'); return false; }
      if (isNew) await App.api(`/api/dorms/${dormId}/members`, 'POST', payload);
      else await App.api(`/api/members/${member.id}`, 'PUT', payload);
      App.toast('已保存', 'ok');
      await after();
      return true;
    },
  });
};

/* Excel 导入向导 */
App.showImport = function showImport(after) {
  let previewData = null;
  App.modal({
    title: '导入人员信息（Excel / CSV）',
    okText: '开始导入',
    wide: true,
    html: `
      <div class="hint-text">支持 .xlsx 和 .csv。表格里需要有“姓名”“宿舍号”两列，同一个宿舍号自动归为一组；学号、电话号可选。不确定格式就先<a href="#" id="dlTpl">下载导入模板</a>。</div>
      <label class="field" style="margin-top:12px"><span>选择文件</span><input type="file" id="impFile" accept=".xlsx,.xlsm,.csv"></label>
      <div id="impPreview" class="hint-text">还没有选择文件</div>`,
    onMount: async (box) => {
      box.querySelector('#dlTpl').onclick = async (e) => {
        e.preventDefault();
        try { await App.download('/api/members/template', 'member_template.xlsx'); } catch (err) { App.toast(err.message, 'err'); }
      };
      box.querySelector('#impFile').onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const preview = box.querySelector('#impPreview');
        preview.innerHTML = '解析中…';
        try {
          previewData = await App.upload(`/api/members/import/preview?${App.classQuery()}`, file);
          const groups = previewData.groups || [];
          preview.innerHTML = `
            <div class="hint-text">已解析工作表「${App.esc(previewData.sheet)}」：共 ${previewData.total_rows} 行 → ${previewData.total_dorms} 间宿舍、${previewData.total_members} 人。
            列识别：${Object.entries(previewData.mapping || {}).map(([k, v]) => `${App.esc(v)}→${App.esc({ name: '姓名', student_no: '学号', phone: '电话号', room_no: '宿舍号' }[k] || k)}`).join('，')}</div>
            ${(previewData.skipped || []).length ? `<div class="hint-text" style="color:#d97706">已跳过：${App.esc(previewData.skipped.join('；'))}</div>` : ''}
            <label class="field" style="margin-top:10px"><span>导入方式</span>
              <select id="impStrategy">
                <option value="merge">追加/更新：保留原有人员，补充新人员（推荐）</option>
                <option value="overwrite">覆盖：用表格名单替换这些宿舍的原有名单</option>
              </select>
            </label>
            <label class="field"><span>同名人员</span>
              <select id="impUpdate">
                <option value="1">用表格里的学号/电话更新原有记录</option>
                <option value="0">保留原有信息，不更新</option>
              </select>
            </label>
            <div class="table-wrap" style="max-height:300px;overflow:auto"><table>
              <thead><tr><th>宿舍号</th><th>楼栋</th><th>状态</th><th class="num">表格人数</th><th class="num">原有</th><th class="wrap">新增人员</th><th class="wrap">重复人员</th><th>宿舍长</th></tr></thead>
              <tbody>${groups.map((g) => `<tr>
                <td><b>${App.esc(g.room_no)}</b>${g.room_label ? `<div class="hint-text">${App.esc(g.room_label)}</div>` : ''}</td>
                <td>${App.esc(g.building || '—')}</td>
                <td>${g.exists ? '<span class="chip">已存在</span>' : '<span class="chip ok">新建宿舍</span>'}</td>
                <td class="num">${g.incoming_count}</td>
                <td class="num">${g.current.length}</td>
                <td class="wrap">${App.esc(g.new_members.join('、') || '—')}</td>
                <td class="wrap">${App.esc(g.duplicate.join('、') || '—')}</td>
                <td>${App.esc(g.leader_name || '—')}${(g.leaders || []).length ? ' <span class="chip ok">已标记</span>' : ' <span class="chip warn">未标记</span>'}</td>
              </tr>`).join('')}</tbody></table></div>`;
        } catch (err) {
          previewData = null;
          preview.innerHTML = `<div class="hint-text" style="color:#dc2626">解析失败：${App.esc(err.message)}</div>`;
        }
      };
    },
    onOk: async (box) => {
      if (!previewData) { App.toast('请先选择并解析文件', 'err'); return false; }
      const strategy = box.querySelector('#impStrategy').value;
      const updateMember = box.querySelector('#impUpdate').value === '1';
      const res = await App.api('/api/members/import/commit', 'POST', {
        token: previewData.token, strategy, update_member: updateMember,
      });
      App.toast(res.message || '导入完成', 'ok');
      await App.loadBase();
      await after();
      return true;
    },
  });
};
