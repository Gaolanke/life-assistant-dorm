/* 班费管理：统计、明细编辑、Excel 导入导出、发班级群 */
App.page('fund', {
  async render(box) {
    const state = { tab: 'overview', items: [], summary: {}, selected: new Set(), keyword: '', scope: 'latest' };

    box.innerHTML = `
      <div class="card">
        <div class="card-head">
          <h2>💰 班费管理</h2>
          <span class="sub">数据以导入的班费收支明细表为准，可在线修改、编辑、追加</span>
          <span class="spacer"></span>
          <button class="btn tiny" id="fundExport">⬇️ 导出 Excel</button>
          <button class="btn tiny" id="fundImport">⬆️ 导入班费表</button>
          <button class="btn tiny primary" id="fundAdd">➕ 添加费用</button>
        </div>
        <div class="tabs" id="fundTabs">
          <button class="tab active" data-t="overview">班费概览</button>
          <button class="tab" data-t="ledger">收支明细</button>
          <button class="tab" data-t="push">发到班级群</button>
        </div>
        <div class="hint-text" id="fundHint">加载中…</div>
      </div>
      <div id="fundBody"></div>`;

    const money = (n) => {
      const value = Number(n || 0);
      return Math.abs(value - Math.round(value)) < 0.005 ? String(Math.round(value)) : value.toFixed(2);
    };

    /* ---------------- 概览 ---------------- */
    const renderOverview = () => {
      const s = state.summary;
      $('#fundBody').innerHTML = `
        <div class="card">
          <div class="card-head"><h3>班费公式</h3>
            <span class="sub">改了这几个数，下面所有统计立刻跟着变</span>
            <span class="spacer"></span>
            <button class="btn tiny primary" id="fundSaveSettings">保存设置</button>
          </div>
          <div class="grid cols-4" style="gap:14px">
            ${App.field('班级 / 备注名', `<input id="fundClass" value="${App.attr(s.class_name || '')}" placeholder="例如 物联网25-2">`)}
            ${App.field('每人班费（元）', `<input id="fundPer" type="number" step="0.01" value="${s.per_person ?? 50}">`)}
            ${App.field('人数', `<input id="fundHead" type="number" step="1" value="${s.headcount ?? 0}">`)}
            ${App.field('班费合计（元，留空=每人×人数）', `<input id="fundTotal" type="number" step="0.01" value="${s.base_fund || ''}" placeholder="自动算">`)}
            ${App.field('额外收入 / 补收（元）', `<input id="fundExtra" type="number" step="0.01" value="${s.extra_in || 0}">`)}
            ${App.field('班级群（发班费用）', `<input id="fundGroup" value="${App.attr(s.qq_group_id || '')}" placeholder="留空则用系统配置里的群">`, '填 QQ 群 openid（在群里 @ 机器人后到「系统配置 → QQ 官方机器人」复制）')}
          </div>
          <div class="hint-text" style="margin-top:10px">
            公式：<code>班费余额 = 班费合计（每人 × 人数）+ 额外收入 − 已使用</code>
          </div>
        </div>

        <div class="grid cols-4" style="gap:14px">
          ${[
            ['班费合计', money(s.total_fund), '元', `每人 ${money(s.per_person)} × ${s.headcount} 人`],
            ['已使用', money(s.spent), '元', `${s.expense_count || 0} 笔支出`],
            ['班费余额', money(s.balance), '元', '合计 − 已使用'],
            ['人均已花', money(s.avg_per_person), '元', s.headcount ? `按 ${s.headcount} 人平摊` : '未填人数'],
          ].map(([label, value, unit, hint]) => `
            <div class="card stat-card">
              <div class="hint-text">${label}</div>
              <div class="stat-value">${value}<span class="stat-unit">${unit}</span></div>
              <div class="hint-text">${hint}</div>
            </div>`).join('')}
        </div>

        <div class="card">
          <div class="card-head"><h3>最近支出</h3><span class="spacer"></span>
            <button class="btn tiny" id="fundGoLedger">查看全部明细</button>
          </div>
          <div class="table-wrap"><table>
            <thead><tr><th>日期</th><th>项目</th><th class="num">金额</th><th>经手人</th><th>备注</th></tr></thead>
            <tbody>${state.items.filter((i) => i.direction === 'expense').slice(-8).reverse().map((i) => `<tr>
              <td>${App.esc(i.date_text)}</td><td>${App.esc(i.item)}</td>
              <td class="num">${money(i.amount)}</td><td>${App.esc(i.handler || '—')}</td>
              <td>${App.esc(i.note || '')}</td></tr>`).join('')
              || '<tr><td colspan="5" class="empty">还没有班费记录，先导入或添加</td></tr>'}</tbody>
          </table></div>
        </div>`;

      $('#fundSaveSettings').onclick = async () => {
        const res = await App.api(`/api/fund/settings?${App.classQuery()}`, 'PUT', {
          class_name: $('#fundClass').value.trim(),
          per_person: Number($('#fundPer').value || 0),
          headcount: Number($('#fundHead').value || 0),
          total_fund: Number($('#fundTotal').value || 0),
          extra_in: Number($('#fundExtra').value || 0),
          qq_group_id: $('#fundGroup').value.trim(),
        });
        App.toast(res.message || '已保存', 'ok');
        await reload();
      };
      $('#fundGoLedger').onclick = () => switchTab('ledger');
    };

    /* ---------------- 明细 ---------------- */
    const renderLedger = () => {
      const items = state.items.filter((i) => !state.keyword
        || `${i.item}${i.handler}${i.checker}${i.note}${i.date_text}${i.amount}`.toLowerCase().includes(state.keyword.toLowerCase()));
      const total = items.reduce((sum, i) => sum + Number(i.amount || 0), 0);
      $('#fundBody').innerHTML = `
        <div class="card">
          <div class="toolbar">
            <input id="fundSearch" placeholder="搜索项目 / 经手人 / 备注" style="width:220px" value="${App.attr(state.keyword)}">
            <span class="chip">共 ${items.length} 条 · 合计 ${money(total)} 元</span>
            <span style="flex:1"></span>
            <span class="hint-text" id="fundSelInfo">已选 ${state.selected.size} 条</span>
            <button class="btn tiny" id="fundSelAll">全选</button>
            <button class="btn tiny" id="fundSelNone">清空选择</button>
            <button class="btn tiny" id="fundPushSel">发送选定费用</button>
            <button class="btn tiny danger" id="fundDelSel">删除选中</button>
          </div>
          <div class="table-wrap" style="max-height:620px;overflow:auto"><table>
            <thead><tr>
              <th style="width:34px"></th><th style="width:60px">序号</th><th style="width:110px">日期</th>
              <th>支出项目</th><th style="width:90px">单价</th><th style="width:80px">数量</th>
              <th style="width:100px">金额</th><th style="width:120px">经手人</th><th style="width:110px">核对人</th>
              <th style="width:150px">备注</th><th style="width:150px">操作</th>
            </tr></thead>
            <tbody>${items.map((i) => `<tr data-id="${i.id}">
              <td><input type="checkbox" class="fund-ck" data-id="${i.id}" ${state.selected.has(i.id) ? 'checked' : ''}></td>
              <td><input class="f-seq" value="${i.seq}" style="width:52px"></td>
              <td><input class="f-date" value="${App.attr(i.date_text)}" style="width:96px"></td>
              <td><input class="f-item" value="${App.attr(i.item)}"></td>
              <td><input class="f-price" type="number" step="0.01" value="${i.unit_price ?? ''}" style="width:80px"></td>
              <td><input class="f-qty" type="number" step="0.01" value="${i.quantity ?? ''}" style="width:70px"></td>
              <td><input class="f-amount" type="number" step="0.01" value="${i.amount}" style="width:90px"></td>
              <td><input class="f-handler" value="${App.attr(i.handler)}" style="width:110px"></td>
              <td><input class="f-checker" value="${App.attr(i.checker)}" style="width:100px"></td>
              <td><input class="f-note" value="${App.attr(i.note)}" style="width:140px"></td>
              <td>
                <button class="btn tiny primary" data-act="save" data-id="${i.id}">保存</button>
                <button class="btn tiny" data-act="push" data-id="${i.id}">发群</button>
                <button class="btn tiny danger" data-act="del" data-id="${i.id}">删除</button>
              </td>
            </tr>`).join('') || '<tr><td colspan="11" class="empty">还没有记录</td></tr>'}</tbody>
          </table></div>
          <div class="hint-text" style="margin-top:8px">单价 × 数量 ≠ 金额 也没关系（有些是几个班 AA 后的金额），金额以你填的为准。</div>
        </div>`;

      const refreshSel = () => {
        $('#fundSelInfo').textContent = `已选 ${state.selected.size} 条`;
      };
      $$('.fund-ck').forEach((ck) => {
        ck.onchange = () => {
          const id = Number(ck.dataset.id);
          if (ck.checked) state.selected.add(id); else state.selected.delete(id);
          refreshSel();
        };
      });
      $('#fundSearch').oninput = (e) => {
        state.keyword = e.target.value;
        clearTimeout(state.timer);
        state.timer = setTimeout(renderLedger, 300);
      };
      $('#fundSelAll').onclick = () => { items.forEach((i) => state.selected.add(i.id)); renderLedger(); };
      $('#fundSelNone').onclick = () => { state.selected.clear(); renderLedger(); };
      $('#fundDelSel').onclick = () => {
        if (!state.selected.size) { App.toast('先勾选要删除的记录', 'err'); return; }
        App.confirmBox(`删除选中的 ${state.selected.size} 条班费记录？`, async () => {
          const res = await App.api(`/api/fund/entries/delete?${App.classQuery()}`, 'POST', { ids: [...state.selected] });
          state.selected.clear();
          App.toast(res.message, 'ok');
          await reload();
        }, '删除');
      };
      $('#fundPushSel').onclick = () => {
        if (!state.selected.size) { App.toast('先勾选要发送的费用', 'err'); return; }
        state.scope = 'selected';
        switchTab('push');
      };

      $$('#fundBody [data-act]').forEach((btn) => {
        btn.onclick = async () => {
          const id = Number(btn.dataset.id);
          const row = btn.closest('tr');
          const act = btn.dataset.act;
          btn.disabled = true;
          try {
            if (act === 'save') {
              await App.api(`/api/fund/entries/${id}?${App.classQuery()}`, 'PATCH', {
                seq: Number(row.querySelector('.f-seq').value || 0),
                date_text: row.querySelector('.f-date').value.trim(),
                item: row.querySelector('.f-item').value.trim(),
                unit_price: row.querySelector('.f-price').value === '' ? null : Number(row.querySelector('.f-price').value),
                quantity: row.querySelector('.f-qty').value === '' ? null : Number(row.querySelector('.f-qty').value),
                amount: Number(row.querySelector('.f-amount').value || 0),
                handler: row.querySelector('.f-handler').value.trim(),
                checker: row.querySelector('.f-checker').value.trim(),
                note: row.querySelector('.f-note').value.trim(),
              });
              App.toast('已保存', 'ok');
              await reload();
              return;
            }
            if (act === 'push') {
              const res = await App.api('/api/fund/push/preview', 'POST', { scope: 'selected', ids: [id], class_id: App.state.classId || 0 });
              openPushDialog(res, 'selected', [id]);
              return;
            }
            if (act === 'del') {
              App.confirmBox('删除这条班费记录？', async () => {
                await App.api(`/api/fund/entries/delete?${App.classQuery()}`, 'POST', { ids: [id] });
                App.toast('已删除', 'ok');
                await reload();
              }, '删除');
              return;
            }
          } catch (e) {
            App.toast(e.message, 'err');
          } finally {
            btn.disabled = false;
          }
        };
      });
      refreshSel();
    };

    /* ---------------- 发群 ---------------- */
    const renderPush = () => {
      const selectedIds = [...state.selected];
      $('#fundBody').innerHTML = `
        <div class="card">
          <div class="card-head"><h3>通过 QQ 机器人发到班级群</h3>
            <span class="spacer"></span>
            <span class="chip ${state.summary.qq_group_id ? 'ok' : 'warn'}">发送通道：${App.esc(state.summary.push_channel || '未配置')}</span>
            <span class="chip">${state.summary.qq_group_id ? `群：${App.esc((state.summary.qq_group_id || '').slice(0, 14))}…` : '群未设置'}</span>
          </div>
          <div class="grid cols-2" style="gap:14px">
            <div>
              <div class="hint-text">发送内容</div>
              <div class="grid cols-2" style="gap:8px;margin-top:6px">
                <button class="btn ${state.scope === 'latest' ? 'primary' : ''}" data-scope="latest">最新一笔费用</button>
                <button class="btn ${state.scope === 'recent' ? 'primary' : ''}" data-scope="recent">最近几笔</button>
                <button class="btn ${state.scope === 'selected' ? 'primary' : ''}" data-scope="selected">选定的 ${selectedIds.length} 笔</button>
                <button class="btn ${state.scope === 'all' ? 'primary' : ''}" data-scope="all">全部费用</button>
              </div>
              ${App.field('最近几笔的数量', `<input id="pushLimit" type="number" min="1" max="50" value="5" style="width:100px">`)}
              ${App.field('群 openid（留空用系统配置里的）', `<input id="pushGroup" placeholder="在群里 @ 机器人后可从系统配置复制">`)}
              ${App.field('标题（选填）', `<input id="pushTitle" placeholder="例如：9月班费公示">`)}
              <div style="display:flex;gap:8px;margin-top:10px">
                <button class="btn primary" id="pushPreviewBtn">预览要发的内容</button>
                <button class="btn" id="pushSendBtn">直接发送到群</button>
              </div>
              <div class="hint-text" style="margin-top:8px">发送前建议先点「预览」。发送失败的记录会出现在「提醒推送 → 推送日志」里。<br>
                ⚠️ 服务器到腾讯的网络不稳，发送会自动重试最多 4 次，点完可能要等十几秒到一两分钟，请不要关页面。</div>
            </div>
            <div>
              <div class="hint-text">预览</div>
              <div class="logbox" id="fundPreview" style="min-height:220px;white-space:pre-wrap">点左边「预览要发的内容」看看效果</div>
            </div>
          </div>
          <div class="card-head" style="margin-top:14px"><h3>群消息模板</h3><span class="spacer"></span>
            <button class="btn tiny primary" id="fundSaveTpl">保存模板</button>
            <button class="btn tiny" id="fundResetTpl">恢复默认</button>
          </div>
          <textarea id="fundTpl" rows="7" style="width:100%;font-family:ui-monospace,Consolas,monospace">${App.esc(state.summary.template || '')}</textarea>
          <div class="hint-text">可用变量：<code>{class_name}</code> <code>{per_person}</code> <code>{headcount}</code> <code>{total_fund}</code> <code>{spent}</code> <code>{balance}</code> <code>{count}</code> <code>{lines}</code></div>
        </div>`;

      $$('#fundBody [data-scope]').forEach((btn) => {
        btn.onclick = () => { state.scope = btn.dataset.scope; renderPush(); };
      });
      const payload = () => ({
        scope: state.scope,
        ids: [...state.selected],
        limit: Number($('#pushLimit').value || 5),
        group_id: $('#pushGroup').value.trim(),
        title: $('#pushTitle').value.trim(),
        class_id: App.state.classId || 0,
      });
      $('#pushPreviewBtn').onclick = async () => {
        try {
          const res = await App.api('/api/fund/push/preview', 'POST', payload());
          $('#fundPreview').textContent = res.text || '（无内容）';
        } catch (e) { App.toast(e.message, 'err'); }
      };
      $('#pushSendBtn').onclick = async () => {
        try {
          const res = await App.api('/api/fund/push', 'POST', payload());
          $('#fundPreview').textContent = res.text || '';
          App.toast(res.message || (res.ok ? '已发送' : '发送失败'), res.ok ? 'ok' : 'err');
          if (!res.ok) App.toast('详情请看「提醒推送 → 推送日志」', 'err');
        } catch (e) { App.toast(e.message, 'err'); }
      };
      $('#fundSaveTpl').onclick = async () => {
        await App.api(`/api/fund/settings?${App.classQuery()}`, 'PUT', { template: $('#fundTpl').value });
        App.toast('模板已保存', 'ok');
        await reload();
      };
      $('#fundResetTpl').onclick = () => {
        $('#fundTpl').value = state.summary.default_template || '';
        App.toast('已填回默认模板，记得点「保存模板」', 'ok');
      };
    };

    const openPushDialog = (preview, scope, ids) => {
      App.modal({
        title: '发送这条费用到班级群',
        okText: '发送',
        html: `<div class="hint-text">将要发送的内容：</div>
          <div class="logbox" style="white-space:pre-wrap">${App.esc(preview.text)}</div>
          ${App.field('群号（留空用设置里的）', '<input id="dlgGroup" placeholder="例如 123456789">')}`,
        onOk: async (m) => {
          const res = await App.api('/api/fund/push', 'POST', {
            scope: scope || 'selected',
            ids: ids || [],
            group_id: m.querySelector('#dlgGroup').value.trim(),
            class_id: App.state.classId || 0,
          });
          App.toast(res.message || (res.ok ? '已发送' : '发送失败'), res.ok ? 'ok' : 'err');
          return true;
        },
      });
    };

    /* ---------------- 数据加载 ---------------- */
    const loadData = async () => {
      const [summary, entries] = await Promise.all([
        App.api(`/api/fund/summary?${App.classQuery()}`),
        App.api(`/api/fund/entries?${App.classQuery()}`),
      ]);
      state.summary = summary;
      state.items = entries.items || [];
      $('#fundHint').innerHTML = `班费合计 <b>${money(summary.total_fund)}</b> 元 · 已使用 <b>${money(summary.spent)}</b> 元 · 余额 <b>${money(summary.balance)}</b> 元 · 共 ${summary.entry_count} 条明细`;
    };

    const reload = async () => {
      await loadData();
      renderTab();
    };

    const renderTab = () => {
      if (state.tab === 'overview') renderOverview();
      else if (state.tab === 'ledger') renderLedger();
      else renderPush();
    };

    const switchTab = (tab) => {
      state.tab = tab;
      $$('#fundTabs .tab').forEach((t) => t.classList.toggle('active', t.dataset.t === tab));
      renderTab();
    };

    $$('#fundTabs .tab').forEach((tab) => {
      tab.onclick = () => switchTab(tab.dataset.t);
    });

    /* 添加费用 */
    $('#fundAdd').onclick = () => {
      App.modal({
        title: '添加一条班费记录',
        okText: '添加',
        html: `
          ${App.field('日期', '<input id="addDate" placeholder="例如 2026.10.10">')}
          ${App.field('支出项目', '<input id="addItem" placeholder="例如 打印费">')}
          <div class="grid cols-3" style="gap:10px">
            ${App.field('单价', '<input id="addPrice" type="number" step="0.01">')}
            ${App.field('数量', '<input id="addQty" type="number" step="0.01" value="1">')}
            ${App.field('金额（元）', '<input id="addAmount" type="number" step="0.01">')}
          </div>
          <div class="grid cols-2" style="gap:10px">
            ${App.field('经手人', '<input id="addHandler">')}
            ${App.field('核对人', '<input id="addChecker">')}
          </div>
          ${App.field('备注', '<input id="addNote" placeholder="例如 两个班AA">')}
          ${App.field('类型', `<select id="addDir"><option value="expense">支出</option><option value="income">收入 / 补收</option></select>`)}`,
        onOk: async (m) => {
          const res = await App.api(`/api/fund/entries?${App.classQuery()}`, 'POST', {
            date_text: m.querySelector('#addDate').value.trim(),
            item: m.querySelector('#addItem').value.trim(),
            unit_price: Number(m.querySelector('#addPrice').value || 0) || null,
            quantity: Number(m.querySelector('#addQty').value || 0) || null,
            amount: Number(m.querySelector('#addAmount').value || 0),
            handler: m.querySelector('#addHandler').value.trim(),
            checker: m.querySelector('#addChecker').value.trim(),
            note: m.querySelector('#addNote').value.trim(),
            direction: m.querySelector('#addDir').value,
          });
          App.toast(res.message || '已添加', 'ok');
          await reload();
          return true;
        },
      });
    };

    /* 导入 */
    $('#fundImport').onclick = () => openFundImport(reload);

    /* 导出 */
    $('#fundExport').onclick = () => App.download(`/api/fund/export?${App.classQuery()}`);

    await loadData();
    renderTab();
  },
});

/* 导入班费表：预览 → 确认 */
function openFundImport(after) {
  const state = { parsed: null };
  App.modal({
    title: '导入班费收支明细表',
    okText: '确认导入',
    html: `
      <div class="hint-text">选择那份「班费收支明细表 .xlsx」，表头里的「每人班费 / 人数 / 班费合计 / 已使用」会自动读进设置，下面的明细逐条导入。</div>
      ${App.field('选择文件', '<input type="file" id="fundFile" accept=".xlsx,.xlsm">')}
      <div style="margin-top:8px"><button class="btn tiny" id="fundPreviewBtn">先预览</button></div>
      <div id="fundPreviewBox" class="hidden" style="margin-top:12px"></div>
      ${App.field('导入方式', `<select id="fundMode">
          <option value="replace">覆盖：清空现有明细，用表格里的（推荐）</option>
          <option value="append">追加：保留现有明细，把表格里的加在后面</option>
        </select>`)}`,
    onOk: async (m) => {
      if (!state.parsed) {
        App.toast('请先选择文件并点「先预览」', 'err');
        return false;
      }
      const res = await App.api('/api/fund/import/commit', 'POST', {
        entries: state.parsed.entries,
        summary: state.parsed.summary,
        replace: m.querySelector('#fundMode').value === 'replace',
        apply_summary: true,
        class_id: App.state.classId || 0,
      });
      App.toast(res.message || '导入完成', 'ok');
      if (typeof after === 'function') await after();
      return true;
    },
    onMount: (m) => {
      m.querySelector('#fundPreviewBtn').onclick = async () => {
        const input = m.querySelector('#fundFile');
        if (!input.files || !input.files.length) {
          App.toast('请先选择一个 .xlsx 文件', 'err');
          return;
        }
        const btn = m.querySelector('#fundPreviewBtn');
        btn.disabled = true;
        btn.textContent = '解析中…';
        try {
          const res = await App.upload(`/api/fund/import/preview?${App.classQuery()}`, input.files[0]);
          state.parsed = res;
          const s = res.summary || {};
          const rows = res.entries.slice(0, 6).map((e) => `<tr>
            <td>${App.esc(e.date_text || '')}</td><td>${App.esc(e.item || '')}</td>
            <td class="num">${e.amount}</td><td>${App.esc(e.handler || '')}</td></tr>`).join('');
          m.querySelector('#fundPreviewBox').classList.remove('hidden');
          m.querySelector('#fundPreviewBox').innerHTML = `
            <div class="notice">读到 <b>${res.entry_count}</b> 条明细，合计 <b>${res.spent_parsed}</b> 元${res.spent_in_sheet ? `（表格里写的已使用：${res.spent_in_sheet} 元，${res.spent_match ? '一致 ✅' : '<span style="color:#dc2626">对不上，请检查</span>'}）` : ''}</div>
            <div class="hint-text">表头设置：每人 ${s.per_person ?? '—'} 元 · 人数 ${s.headcount ?? '—'} · 班费合计 ${s.total_fund ?? '—'} 元</div>
            <div class="table-wrap" style="max-height:200px;overflow:auto;margin-top:8px"><table>
              <thead><tr><th>日期</th><th>项目</th><th class="num">金额</th><th>经手人</th></tr></thead>
              <tbody>${rows}</tbody></table></div>
            <div class="hint-text">只预览了前 6 条，导入后会全部写入。</div>`;
        } catch (e) {
          App.toast(e.message, 'err');
        } finally {
          btn.disabled = false;
          btn.textContent = '先预览';
        }
      };
    },
  });
}
