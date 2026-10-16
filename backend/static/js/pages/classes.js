/* 班级管理：多班级支持（每个班级独立的宿舍、人员、班费与群绑定） */
App.page('classes', {
  async render(box) {
    // 页面打开时班级列表为空就先拉一次
    if (!App.state.classes.length) await App.loadClasses();
    const state = { groups: [] };

    box.innerHTML = `
      <div class="card">
        <div class="card-head">
          <h2>🏫 班级管理</h2>
          <span class="sub">每个班级有独立的宿舍、人员、班费和汇报时间；用顶部的班级切换器决定其他页面看哪个班</span>
          <span class="spacer"></span>
          <button class="btn tiny primary" id="btnNewClass">＋ 新增班级</button>
          <button class="btn tiny" id="btnClassRefresh">刷新</button>
        </div>
        <div class="hint-text" id="classSummary">加载中…</div>
      </div>
      <div class="card">
        <div class="table-wrap" style="max-height:420px;overflow:auto"><table id="classTable"></table></div>
      </div>
      <div class="card">
        <div class="card-head">
          <h2>🔗 QQ 群 ↔ 班级绑定</h2>
          <span class="sub">群绑定到班级后，群里 @ 机器人的汇报会记到对应班级</span>
          <span class="spacer"></span>
          <button class="btn tiny" id="btnGroupsRefresh">刷新群列表</button>
        </div>
        <div class="table-wrap" style="max-height:420px;overflow:auto"><table id="groupTable"></table></div>
      </div>`;

    /* ---------------- 班级列表 ---------------- */
    const renderClasses = () => {
      const items = App.state.classes || [];
      const current = items.find((c) => c.id === App.state.classId);
      $('#classSummary').innerHTML = `共 <b>${items.length}</b> 个班级 · 当前使用：<b>${App.esc(current ? current.name : '默认班级')}</b>`
        + `<div class="hint-text" style="margin-top:6px">删除班级不会删除宿舍和班费明细，但要求先把它们搬到其他班级。新建班级后到「宿舍与人员」给班级添加宿舍。</div>`;
      $('#classTable').innerHTML = `
        <thead><tr>
          <th>班级名称</th><th class="wrap">备注</th><th class="num">宿舍数</th><th class="num">成员数</th>
          <th class="num">班费条数</th><th class="num">群数</th><th>汇报时间</th><th>状态</th><th style="min-width:140px">操作</th>
        </tr></thead>
        <tbody>${items.map((c) => `<tr data-id="${c.id}">
          <td><b>${App.esc(c.name)}</b>${c.id === App.state.classId ? ' <span class="chip ok">当前</span>' : ''}</td>
          <td class="wrap">${App.esc(c.note || '—')}</td>
          <td class="num">${c.dorm_count ?? 0}</td>
          <td class="num">${c.member_count ?? 0}</td>
          <td class="num">${c.fund_entry_count ?? 0}</td>
          <td class="num">${(c.group_openids || []).length}</td>
          <td>${App.esc(c.qq_report_time || '全局时间')}</td>
          <td>${c.active ? '<span class="chip ok">启用</span>' : '<span class="chip gray">停用</span>'}</td>
          <td>
            <button class="btn tiny" data-act="edit" data-id="${c.id}">编辑</button>
            <button class="btn tiny danger" data-act="del" data-id="${c.id}" data-name="${App.attr(c.name)}">删除</button>
          </td>
        </tr>`).join('') || '<tr><td colspan="9" class="empty">还没有班级，点「新增班级」创建；不建班级就统一用「默认班级」</td></tr>'}</tbody>`;
      $$('#classTable [data-act]').forEach((btn) => {
        btn.onclick = () => {
          const id = Number(btn.dataset.id);
          if (btn.dataset.act === 'edit') editClass(items.find((c) => c.id === id));
          else delClass(id, btn.dataset.name);
        };
      });
    };

    const refreshAll = async () => {
      await App.loadClasses();
      renderClasses();
      App.renderChrome(); // 同步顶部班级切换器
    };

    /* 新增 / 编辑班级弹窗 */
    const editClass = (item) => {
      const isNew = !item;
      App.modal({
        title: isNew ? '新增班级' : `编辑班级：${item.name}`,
        okText: '保存',
        html: `
          ${App.field('班级名称', `<input id="cName" value="${App.attr(item ? item.name : '')}" placeholder="例如 物联网25-2">`, '', true)}
          ${App.field('备注', `<input id="cNote" value="${App.attr(item ? item.note : '')}" placeholder="例如 班主任张老师 / 3 号楼">`)}
          <div class="grid cols-2" style="gap:10px">
            ${App.field('排序（小的在前）', `<input id="cSort" type="number" value="${item ? item.sort_order : 0}">`)}
            ${App.field('状态', `<select id="cActive">
              <option value="1" ${!item || item.active ? 'selected' : ''}>启用</option>
              <option value="0" ${item && !item.active ? 'selected' : ''}>停用</option>
            </select>`)}
          </div>
          ${isNew ? '' : App.field('群汇报时间', `<input id="cReportTime" type="time" value="${App.attr(item.qq_report_time || '')}">`, '留空则用全局时间（系统配置 → 基本设置里的「每晚 QQ 群汇报时间」）')}`,
        onOk: async (m) => {
          const name = m.querySelector('#cName').value.trim();
          if (!name) { App.toast('班级名称不能为空', 'err'); return false; }
          const payload = {
            name,
            note: m.querySelector('#cNote').value.trim(),
            sort_order: Number(m.querySelector('#cSort').value) || 0,
          };
          if (isNew) {
            const res = await App.api('/api/classes', 'POST', payload);
            App.toast(res.message || '班级已创建', 'ok');
          } else {
            payload.active = m.querySelector('#cActive').value === '1';
            payload.settings = { qq_report_time: m.querySelector('#cReportTime').value.trim() };
            const res = await App.api(`/api/classes/${item.id}`, 'PUT', payload);
            App.toast(res.message || '已保存', 'ok');
          }
          await refreshAll();
          return true;
        },
      });
    };

    /* 删除班级 */
    const delClass = (id, name) => {
      App.confirmBox(
        `删除班级「${name}」？删除班级不会删除宿舍和班费明细，但要求先把它们搬到其他班级。`,
        async () => {
          try {
            const res = await App.api(`/api/classes/${id}`, 'DELETE');
            App.toast(res.message || '已删除', 'ok');
          } catch (e) {
            App.toast(e.message, 'err');
          }
          await refreshAll();
        },
        '删除',
      );
    };

    /* ---------------- QQ 群 ↔ 班级绑定 ---------------- */
    const renderGroups = async () => {
      const table = $('#groupTable');
      if (!table) return;
      table.innerHTML = '<tbody><tr><td class="empty">加载中…</td></tr></tbody>';
      try {
        const data = await App.api('/api/qqbot/groups');
        state.groups = data.items || [];
      } catch (e) {
        table.innerHTML = `<tbody><tr><td class="empty">加载失败：${App.esc(e.message)}</td></tr></tbody>`;
        return;
      }
      const options = ['<option value="0">未绑定</option>']
        .concat((App.state.classes || []).map((c) => `<option value="${c.id}">${App.esc(c.name)}</option>`))
        .join('');
      $('#groupTable').innerHTML = `
        <thead><tr>
          <th>群名称</th><th>群 openid</th><th>最近活跃</th><th>当前绑定</th><th style="min-width:260px">操作</th>
        </tr></thead>
        <tbody>${state.groups.map((g) => `<tr>
          <td><b>${App.esc(g.name || '未命名群')}</b></td>
          <td><code title="${App.attr(g.group_openid)}">${App.esc(String(g.group_openid || '').slice(0, 12))}${String(g.group_openid || '').length > 12 ? '…' : ''}</code></td>
          <td>${App.esc(g.last_seen || '—')}</td>
          <td>${g.class_name ? `<span class="chip ok">${App.esc(g.class_name)}</span>` : '<span class="chip gray">未绑定</span>'}</td>
          <td>
            <select class="bind-select" data-id="${g.id}" style="max-width:150px">${options}</select>
            <button class="btn tiny primary" data-bind="${g.id}">保存绑定</button>
          </td>
        </tr>`).join('') || '<tr><td colspan="5" class="empty">还没有收到任何群消息；把机器人拉进群并 @ 它发一句话就会出现在这里</td></tr>'}</tbody>`;
      // 回填当前绑定
      $$('#groupTable .bind-select').forEach((sel) => {
        const g = state.groups.find((x) => x.id === Number(sel.dataset.id));
        sel.value = String((g && g.class_id) || 0);
      });
      $$('#groupTable [data-bind]').forEach((btn) => {
        btn.onclick = async () => {
          const id = Number(btn.dataset.bind);
          const sel = $(`#groupTable .bind-select[data-id="${id}"]`);
          btn.disabled = true;
          try {
            const res = await App.api(`/api/qqbot/groups/${id}/bind`, 'PUT', { class_id: Number(sel.value) || 0 });
            App.toast(res.message || '已保存绑定', 'ok');
            await renderGroups();
            await refreshAll();
          } catch (e) {
            App.toast(e.message, 'err');
          } finally {
            btn.disabled = false;
          }
        };
      });
    };

    $('#btnNewClass').onclick = () => editClass(null);
    $('#btnClassRefresh').onclick = refreshAll;
    $('#btnGroupsRefresh').onclick = renderGroups;

    renderClasses();
    await renderGroups();
  },
});
