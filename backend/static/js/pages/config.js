/* 系统配置：全部参数图形化修改 */
App.page('config', {
  async render(box) {
    // 支持 #/config/qqbot 直达某个页签
    const hashTab = (location.hash.split('/')[2] || '').trim();
    const KNOWN_TABS = ['basic', 'qqbot', 'tpl', 'jobs', 'accounts', 'sys'];
    const state = { tab: KNOWN_TABS.includes(hashTab) ? hashTab : 'basic' };

    const renderTabs = () => `
      <div class="card">
        <div class="tabs" id="cfgTabs">
          <button class="tab ${state.tab === 'basic' ? 'active' : ''}" data-t="basic">基本设置</button>
          <button class="tab ${state.tab === 'qqbot' ? 'active' : ''}" data-t="qqbot">QQ 官方机器人</button>
          <button class="tab ${state.tab === 'tpl' ? 'active' : ''}" data-t="tpl">消息模板</button>
          <button class="tab ${state.tab === 'jobs' ? 'active' : ''}" data-t="jobs">定时任务</button>
          <button class="tab ${state.tab === 'accounts' ? 'active' : ''}" data-t="accounts">宿舍长联系表</button>
          <button class="tab ${state.tab === 'sys' ? 'active' : ''}" data-t="sys">系统与备份</button>
        </div>
      </div>`;

    const val = (key, fallback = '') => {
      const settings = App.state.settings || {};
      return settings[key] !== undefined ? settings[key] : fallback;
    };

    const tabsHtml = {
      qqbot: () => `
        <div class="card">
          <div class="card-head"><h2>QQ 官方机器人</h2>
            <span class="sub">腾讯官方通道：不用挂 QQ 客户端、不用小号、不会被封号</span>
            <span class="spacer"></span>
            <a class="btn tiny" href="https://q.qq.com/" target="_blank">去 QQ 开放平台注册 →</a>
          </div>
          <div class="notice">
            <b>怎么开通（一次性，约 10 分钟）：</b>
            <ol style="margin:6px 0 0 18px;padding:0">
              <li>打开 <a href="https://q.qq.com/" target="_blank">QQ 开放平台</a>，用手机 QQ 登录 → 创建机器人（选「群聊」场景）</li>
              <li>在「开发设置」里拿到 <b>AppID</b> 和 <b>AppSecret</b>，填到下面</li>
              <li>把机器人<b>添加到你的班级群</b>（群主在群里启用机器人）</li>
              <li>在群消息里 <b>@机器人</b> 发一句话，让它上报一次，下面「最近上报的群」里就会出现</li>
              <li>在下方「推送群管理」里点「添加」把它加进来，开启开关，点「检测凭证」</li>
            </ol>
          </div>
          <div class="grid cols-2">
            ${App.field('AppID', `<input data-key="qqbot_app_id" value="${App.attr(val('qqbot_app_id'))}" placeholder="例如 102000001">`, '', true)}
            ${App.field('AppSecret', `<input data-key="qqbot_secret" type="password" value="${App.attr(val('qqbot_secret'))}" placeholder="开放平台里的 AppSecret">`, '保密，别外传；页面上不会明文显示给外人', true)}
            ${App.field('推送开关', `<select data-key="qqbot_enabled">
              <option value="1" ${val('qqbot_enabled') === '1' ? 'selected' : ''}>开启（到点自动发群）</option>
              <option value="0" ${val('qqbot_enabled') !== '1' ? 'selected' : ''}>关闭</option></select>`)}
            ${App.field('消息类型', `<select data-key="qqbot_msg_type">
              <option value="0" ${val('qqbot_msg_type', '0') !== '2' ? 'selected' : ''}>纯文本</option>
              <option value="2" ${val('qqbot_msg_type') === '2' ? 'selected' : ''}>Markdown</option></select>`)}
            ${App.field('沙箱环境', `<select data-key="qqbot_sandbox">
              <option value="0" ${val('qqbot_sandbox') !== '1' ? 'selected' : ''}>正式环境</option>
              <option value="1" ${val('qqbot_sandbox') === '1' ? 'selected' : ''}>沙箱环境</option></select>`)}
            ${App.field('官方接口地址', `<input data-key="qqbot_api" value="${App.attr(val('qqbot_api', 'https://api.sgroup.qq.com'))}">`, '一般不用改')}
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn primary" id="btnSaveQqbot">保存</button>
            <button class="btn" id="btnCheckQqbot">检测凭证</button>
            <button class="btn" id="btnTestQqbot">发测试消息到群</button>
            <button class="btn" id="btnLoadGroups">刷新群列表</button>
            <button class="btn" id="btnReconnect">重连长连接</button>
          </div>
          <div id="qqbotCheckResult" class="hint-text" style="margin-top:10px"></div>
          <div class="card" style="margin-top:14px;box-shadow:none">
            <div class="card-head"><h3>推送群管理</h3>
              <span class="sub">消息会发到这里的每个群；可以随时添加、修改、删除，立即生效</span>
            </div>
            <div id="qqbotStatus" class="hint-text">正在检查长连接状态…</div>
            <div id="qqbotTargets" style="margin-top:10px"></div>
            <div class="card-head" style="margin-top:16px"><h3>最近上报的群</h3>
              <span class="sub">把机器人拉进群、在群里 @ 它发一句话，这里就会出现群 openid，点「添加」即可推送</span>
            </div>
            <div id="qqbotGroups" class="hint-text">正在加载…</div>
            <div class="hint-text" style="margin-top:10px">
              回调地址（填到 QQ 开放平台后台的「事件订阅 / Webhook」里）：<br>
              <span class="logbox" style="display:inline-block;padding:4px 10px;max-width:none">${App.esc(App.publicBase || location.origin)}/api/qqbot/events</span>
              <br>（公开端、管理端两个地址都可用）
            </div>
          </div>
          <div class="hint-text" style="margin-top:12px">
            官方限制提醒：机器人在群里<b>主动推送有配额</b>（主要是「被 @ 之后 5 分钟内回复」）。
            如果发不出去，可以在群里 @ 机器人，它会用「被动回复」把内容发出来（不受配额限制）。
          </div>
        </div>`,

      basic: () => `
        <div class="card">
          <div class="card-head"><h2>基本设置</h2><span class="sub">学校名称、汇报时间、缺席原因等</span></div>
          <div class="grid cols-2">
            ${App.field('学校名称', `<input data-key="school_name" value="${App.attr(val('school_name'))}">`)}
            ${App.field('班级名称', `<input data-key="class_name" value="${App.attr(val('class_name'))}">`)}
            ${App.field('汇报人署名', `<input data-key="commissary_name" value="${App.attr(val('commissary_name'))}">`)}
            ${App.field('接收汇报的老师', `<input data-key="teacher_name" value="${App.attr(val('teacher_name'))}">`)}
            ${App.field('每晚 QQ 群汇报时间', `<input type="time" data-key="qq_report_time" value="${App.attr(val('qq_report_time'))}">`, '把当天填报情况汇总发到群里；每个班级可在「班级管理」里单独设置汇报时间')}
            ${App.field('公开端网址', `<input data-key="site_public_url" value="${App.attr(val('site_public_url'))}" placeholder="https://xiaoaiyun.top">`, '提醒消息里的「填报网址」用的就是这个')}
            ${App.field('每天自动导出 Excel 时间', `<input type="time" data-key="auto_export_time" value="${App.attr(val('auto_export_time'))}">`)}
            ${App.field('自动导出开关', `<select data-key="auto_export">
              <option value="1" ${val('auto_export') === '1' ? 'selected' : ''}>开启（每天自动存一份到服务器）</option>
              <option value="0" ${val('auto_export') !== '1' ? 'selected' : ''}>关闭</option></select>`)}
          </div>
          ${App.field('缺席原因候选项', `<input data-key="absence_reasons" value="${App.attr(val('absence_reasons'))}">`, '英文逗号分隔，会出现在宿舍长填报表单的下拉框里')}
          ${App.field('首页公告', `<input data-key="site_notice" value="${App.attr(val('site_notice'))}">`)}
          <div class="hint-text" style="margin:10px 0">
            定时提醒（填报提醒、未填名单、最后通报等）已移到「提醒推送」页管理：可添加多条、每条自定义时间和内容、可选模板。
            <a href="#/push">前往「提醒推送」→</a>
          </div>
          <button class="btn primary" id="btnSaveBasic">保存基本设置</button>
        </div>`,

      tpl: () => `
        <div class="card">
          <div class="card-head"><h2>消息模板</h2><span class="sub">下面这些文字就是实际发出去的内容，可以自由改</span></div>
          <div class="hint-text" style="margin-bottom:10px">可用变量：
            ${Object.entries(App.state.templateVars || {}).map(([k, v]) => `<span class="chip" title="${App.attr(v)}">{${App.esc(k)}}</span>`).join(' ')}
          </div>
          ${App.field('每晚 QQ 群汇报模板', `<textarea data-key="tpl_group_report" style="min-height:170px">${App.esc(val('tpl_group_report'))}</textarea>`)}
          <div class="hint-text" style="margin:4px 0 10px">
            提醒类消息（填报提醒、未填名单、最后通报）的内容已改为在「提醒推送」页逐条编辑，可添加多条、直接选模板。
            <a href="#/push">前往「提醒推送」→</a>
          </div>
          ${App.field('单宿舍催填模板', `<textarea data-key="tpl_dorm_pending">${App.esc(val('tpl_dorm_pending'))}</textarea>`)}
          ${App.field('群汇报里每间宿舍的明细行模板', `<textarea data-key="tpl_absent_dorm">${App.esc(val('tpl_absent_dorm'))}</textarea>`, '可用变量：{dorm}、{absent_count}、{absent_names}、{reason_text}')}
          <div style="display:flex;gap:8px">
            <button class="btn primary" id="btnSaveTpl">保存模板</button>
            <button class="btn" id="btnPreviewTpl">预览效果</button>
          </div>
          <div id="tplPreview" class="logbox hidden" style="margin-top:12px"></div>
        </div>`,

      jobs: () => `
        <div class="card">
          <div class="card-head">
            <h2>定时任务</h2>
            <span class="sub">提醒类任务可直接在这里添加、编辑、删除，保存后立即生效</span>
            <span class="spacer"></span>
            <button class="btn tiny primary" id="btnJobAddReminder">+ 添加提醒</button>
          </div>
          <div class="table-wrap"><table>
            <thead><tr><th>任务</th><th>作用</th><th>下次执行时间</th><th>操作</th></tr></thead>
            <tbody id="jobRows"></tbody>
          </table></div>
          <div class="hint-text" style="margin-top:10px">「立即执行」会真的发出消息，请谨慎使用。</div>
          <div class="hint-text" style="margin-top:6px">
            提醒内容里可用变量：
            <span class="chip">{date}</span> <span class="chip">{time}</span> <span class="chip">{weekday}</span>
            <span class="chip">{site}</span> <span class="chip">{mention}</span>
            <span class="chip">{missing}</span> <span class="chip">{missing_list}</span> <span class="chip">{missing_count}</span>
            <span class="chip">{reported}</span> <span class="chip">{dorm_total}</span> <span class="chip">{unreported}</span>
            <span class="chip">{school}</span> <span class="chip">{class_name}</span> <span class="chip">{commissary}</span>
            （{mention} 在开启「@全体成员」时自动变成 @所有人）
          </div>
        </div>`,

      accounts: () => `
        <div class="card">
          <div class="card-head">
            <h2>宿舍长联系方式</h2>
            <span class="sub">不用账号密码，只要登记宿舍长是谁</span>
            <span class="spacer"></span>
            <button class="btn tiny" id="btnContactRefresh">刷新</button>
          </div>
          <div id="contactSummary" class="hint-text">加载中…</div>
          <div class="table-wrap" style="max-height:480px;overflow:auto;margin-top:10px"><table id="userTable"></table></div>
        </div>`,

      sys: () => `
        <div class="card">
          <div class="card-head"><h2>系统信息</h2><span class="spacer"></span><button class="btn tiny" id="btnSysRefresh">刷新</button></div>
          <div id="sysInfo" class="grid cols-2"></div>
        </div>
        <div class="card">
          <div class="card-head"><h2>数据备份</h2></div>
          <div class="hint-text">点下面的按钮会下载一份完整的数据库备份（含所有人员、填报、配置）。建议每周备份一次，并把文件存到别的地方。</div>
          <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn primary" id="btnBackup">下载数据库备份</button>
            <button class="btn" id="btnExportAllMembers">导出全部人员名单</button>
            <button class="btn" id="btnExportAllReports">导出最近 30 天填报</button>
          </div>
        </div>
        <div class="card">
          <div class="card-head"><h2>操作日志</h2><span class="spacer"></span><button class="btn tiny" id="btnAuditRefresh">刷新</button></div>
          <div class="table-wrap" style="max-height:400px;overflow:auto"><table id="auditTable"></table></div>
        </div>
        <div class="card" style="border-color:#f3c0bd">
          <div class="card-head"><h2>⚠ 危险操作</h2><span class="sub">清空演示数据，正式使用前用一次</span></div>
          <div class="hint-text">
            会删除所有<b>宿舍、人员、填报记录、推送日志</b>，并解除宿舍长账号与宿舍的绑定。<br>
            管理员账户、系统配置（汇报时间、模板、机器人地址等）都会保留。此操作不可恢复，建议先下载上面的备份。
          </div>
          <div style="margin-top:12px">
            <button class="btn danger" id="btnResetData">清空全部业务数据（保留账户与配置）</button>
          </div>
        </div>`,
    };

    const bindSave = (selector, keys, extra = {}) => {
      const btn = $(selector);
      if (!btn) return;
      btn.onclick = async () => {
        const values = {};
        keys.forEach((key) => {
          const el = box.querySelector(`[data-key="${key}"]`);
          if (el) values[key] = el.value;
        });
        try {
          const res = await App.api('/api/settings', 'PUT', { values, ...extra });
          App.state.settings = res.values || App.state.settings;
          App.state.jobs = res.jobs || App.state.jobs;
          App.toast(res.message || '已保存', 'ok');
          await App.loadBase();
          await renderBody();
        } catch (e) { App.toast(e.message, 'err'); }
      };
    };

    const renderBody = async () => {
      box.innerHTML = `${renderTabs()}<div id="cfgBody"></div>`;
      $$('#cfgTabs .tab').forEach((tab) => {
        tab.onclick = async () => { state.tab = tab.dataset.t; await renderBody(); };
      });
      const body = $('#cfgBody');
      body.innerHTML = tabsHtml[state.tab] ? tabsHtml[state.tab]() : '<div class="card">未实现</div>';

      if (state.tab === 'basic') bindSave('#btnSaveBasic', ['school_name', 'class_name', 'commissary_name', 'teacher_name', 'qq_report_time', 'site_public_url', 'auto_export_time', 'auto_export', 'absence_reasons', 'site_notice']);

      if (state.tab === 'qqbot') {
        bindSave('#btnSaveQqbot', ['qqbot_app_id', 'qqbot_secret', 'qqbot_enabled', 'qqbot_msg_type', 'qqbot_sandbox', 'qqbot_api']);
        $('#btnCheckQqbot').onclick = async () => {
          const res = await App.api('/api/settings/test', 'POST', { kind: 'qqbot' });
          $('#qqbotCheckResult').innerHTML = res.ok
            ? `<span class="chip ok">凭证正常</span> ${App.esc(res.message)}`
            : `<span class="chip bad">不通</span> ${App.esc(res.message)}`;
        };
        // ---------------- 推送群管理（添加 / 修改 / 删除，立即生效） ----------------
        const targetState = { list: [] };
        const loadTargets = (configured) => {
          const box2 = $('#qqbotTargets');
          if (!box2) return;
          targetState.list = String(configured || '')
            .replace(/，/g, ',')
            .split(',')
            .map((x) => x.trim())
            .filter(Boolean);
          const list = targetState.list;
          const rows = list.map((o) => `
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap">
              <span class="chip ok">推送中</span>
              <input data-tedit="${App.attr(o)}" value="${App.attr(o)}" style="flex:1;min-width:260px;font-family:monospace;font-size:12px">
              <button class="btn tiny" data-tsave="${App.attr(o)}">保存修改</button>
              <button class="btn tiny danger" data-deltarget="${App.attr(o)}">删除</button>
            </div>`).join('');
          box2.innerHTML = `
            <div class="hint-text" style="margin-bottom:6px">
              已配置 <b>${list.length}</b> 个推送群。修改 openid 后点「保存修改」，点「删除」立即移出——都无需再点页面保存。
            </div>
            ${rows}
            <div style="display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap">
              <input id="newTargetOpenid" placeholder="输入群 openid（或到下面「最近上报的群」点添加）" style="flex:1;min-width:260px;font-family:monospace;font-size:12px">
              <button class="btn tiny primary" id="btnAddTarget">+ 添加推送群</button>
            </div>`;

          const btnAdd = $('#btnAddTarget');
          if (btnAdd) {
            btnAdd.onclick = async () => {
              const input = $('#newTargetOpenid');
              const openid = (input.value || '').trim();
              if (!openid) { App.toast('请先输入群 openid', 'err'); return; }
              btnAdd.disabled = true;
              try {
                const res = await App.api('/api/qqbot/targets', 'POST', { openid });
                App.toast(res.message || '已添加', 'ok');
                App.state.settings.qqbot_groups = res.configured_groups || '';
                loadTargets(res.configured_groups);
                await loadGroups();
                await loadStatus();
              } catch (e) {
                App.toast(e.message || '添加失败', 'err');
                btnAdd.disabled = false;
              }
            };
          }
          $$('#qqbotTargets [data-tsave]').forEach((btn) => {
            btn.onclick = async () => {
              const oldOpenid = btn.dataset.tsave;
              const input = box2.querySelector(`[data-tedit="${CSS.escape(oldOpenid)}"]`);
              const newOpenid = (input.value || '').trim();
              if (!newOpenid) { App.toast('openid 不能为空', 'err'); return; }
              if (newOpenid === oldOpenid) { App.toast('没有改动', 'ok'); return; }
              btn.disabled = true;
              try {
                const res = await App.api(`/api/qqbot/targets/${encodeURIComponent(oldOpenid)}`, 'PUT', { openid: newOpenid });
                App.toast(res.message || '已保存', 'ok');
                App.state.settings.qqbot_groups = res.configured_groups || '';
                loadTargets(res.configured_groups);
                await loadGroups();
                await loadStatus();
              } catch (e) {
                App.toast(e.message || '保存失败', 'err');
                btn.disabled = false;
              }
            };
          });
          $$('#qqbotTargets [data-deltarget]').forEach((btn) => {
            btn.onclick = async () => {
              const openid = btn.dataset.deltarget;
              if (!window.confirm(`确定把 ${openid.slice(0, 16)}… 从推送群里删除吗？\n\n（对应的群记录也会一并删除）`)) return;
              btn.disabled = true;
              try {
                const res = await App.api(`/api/qqbot/targets/${encodeURIComponent(openid)}`, 'DELETE');
                App.toast(res.message || '已删除', 'ok');
                App.state.settings.qqbot_groups = res.configured_groups || '';
                loadTargets(res.configured_groups);
                await loadGroups();
                await loadStatus();
              } catch (e) {
                App.toast(e.message || '删除失败', 'err');
                btn.disabled = false;
              }
            };
          });
        };
        const loadGroups = async () => {
          try {
            const res = await App.api('/api/qqbot/groups');
            const items = res.items || [];
            App.state.settings.qqbot_groups = res.configured_groups || '';
            loadTargets(res.configured_groups);
            if (!items.length) {
              $('#qqbotGroups').innerHTML = '<span class="chip warn">还没有收到任何群消息</span> 把机器人拉进群，在群里 @ 它说句话就会出现在这里。';
              return;
            }
            $('#qqbotGroups').innerHTML = items.map((g) => `
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap">
                ${g.is_target
                  ? '<span class="chip ok">推送中</span>'
                  : `<button class="btn tiny primary" data-add="${App.attr(g.group_openid)}">添加</button>`}
                <button class="btn tiny" data-del="${g.id}" data-openid="${App.attr(g.group_openid)}">删除</button>
                <code style="font-size:12px">${App.esc(g.group_openid)}</code>
                <span class="hint-text">最后消息：${App.esc((g.last_message || '').slice(0, 30) || '—')} · ${App.esc(g.last_user || '')} · 共 ${g.message_count} 条 · ${App.esc(g.last_seen)}</span>
              </div>`).join('')
              + `<div style="margin-top:10px">
                   <button class="btn tiny" id="btnClearGroups">清空全部群记录</button>
                   <span class="hint-text">删除会同时把它从「推送群管理」里去掉</span>
                 </div>`;
            $$('#qqbotGroups [data-add]').forEach((btn) => {
              btn.onclick = async () => {
                btn.disabled = true;
                try {
                  const res2 = await App.api('/api/qqbot/targets', 'POST', { openid: btn.dataset.add });
                  App.toast(res2.message || '已添加', 'ok');
                  await loadGroups();
                  await loadStatus();
                } catch (e) {
                  App.toast(e.message || '添加失败', 'err');
                  btn.disabled = false;
                }
              };
            });
            $$('#qqbotGroups [data-del]').forEach((btn) => {
              btn.onclick = async () => {
                const short = (btn.dataset.openid || '').slice(0, 12);
                if (!window.confirm(`确定删除群 ${short}… 吗？\n\n会同时把它从「推送群管理」里移除。`)) return;
                try {
                  const res = await App.api(`/api/qqbot/groups/${btn.dataset.del}`, 'DELETE');
                  App.toast(res.message || '已删除', 'ok');
                  await loadGroups();
                  await loadStatus();
                } catch (e) {
                  App.toast(e.message || '删除失败', 'err');
                }
              };
            });
            const btnClear = $('#btnClearGroups');
            if (btnClear) {
              btnClear.onclick = async () => {
                if (!window.confirm('确定清空全部群记录吗？\n\n「推送群管理」里的群也会被一并清空。')) return;
                try {
                  const res = await App.api('/api/qqbot/groups', 'DELETE');
                  App.toast(res.message || '已清空', 'ok');
                  await loadGroups();
                  await loadStatus();
                } catch (e) {
                  App.toast(e.message || '清空失败', 'err');
                }
              };
            }
          } catch (e) {
            $('#qqbotGroups').innerHTML = `<span class="chip bad">加载失败</span> ${App.esc(e.message)}`;
          }
        };
        const loadStatus = async () => {
          try {
            const res = await App.api('/api/qqbot/status');
            const running = res.gateway_running;
            const chip = running
              ? '<span class="chip ok">长连接在线</span>'
              : '<span class="chip bad">长连接未运行</span>';
            const cred = res.has_credentials ? '<span class="chip ok">凭证已配</span>' : '<span class="chip warn">缺 AppID/Secret</span>';
            $('#qqbotStatus').innerHTML = `
              ${chip} ${cred} ${res.enabled ? '<span class="chip ok">推送已开</span>' : '<span class="chip warn">推送未开</span>'}
              已上报群 <b>${res.known_groups}</b> 个 · 已配置推送群 <b>${res.configured_groups}</b> 个
              <div class="hint-text">${App.esc(res.message)}${res.last_group ? ` · 最近：${App.esc(res.last_group.group_openid)}（${App.esc(res.last_group.last_seen)}）` : ''}</div>`;
          } catch (e) {
            $('#qqbotStatus').innerHTML = `<span class="chip bad">状态读取失败</span> ${App.esc(e.message)}`;
          }
        };
        $('#btnLoadGroups').onclick = () => { loadStatus(); loadGroups(); };
        const btnReconnect = $('#btnReconnect');
        if (btnReconnect) {
          btnReconnect.onclick = async () => {
            btnReconnect.disabled = true;
            btnReconnect.textContent = '重连中…';
            try {
              const res = await App.api('/api/qqbot/reconnect', 'POST');
              App.toast(res.message || '已重启', res.ok ? 'ok' : 'err');
              await new Promise((r) => setTimeout(r, 5000));
              await loadStatus();
              await loadGroups();
            } catch (e) {
              App.toast(e.message || '重连失败', 'err');
            } finally {
              btnReconnect.disabled = false;
              btnReconnect.textContent = '重连长连接';
            }
          };
        }
        loadStatus();
        loadGroups();
        $('#btnTestQqbot').onclick = async () => {
          const group = (targetState.list[0] || '').trim();
          if (!group) {
            $('#qqbotCheckResult').innerHTML = '<span class="chip warn">还没有推送群</span> 请先在「推送群管理」里添加一个群';
            return;
          }
          const res = await App.api('/api/settings/test', 'POST', { kind: 'qqbot', group_id: group });
          $('#qqbotCheckResult').innerHTML = res.ok
            ? `<span class="chip ok">已发送</span> ${App.esc(res.message)}`
            : `<span class="chip bad">发送失败</span> ${App.esc(res.message)}`;
        };
      }

      if (state.tab === 'tpl') {
        bindSave('#btnSaveTpl', ['tpl_group_report', 'tpl_dorm_pending', 'tpl_absent_dorm']);
        $('#btnPreviewTpl').onclick = async () => {
          const res = await App.api('/api/settings/test', 'POST', { kind: 'preview' });
          const preview = $('#tplPreview');
          preview.classList.remove('hidden');
          preview.textContent = `【QQ 群汇报预览】\n${res.group_report}\n\n【未填报提醒预览】\n${res.reminder}`;
        };
      }

      if (state.tab === 'jobs') {
        const className = (cid) => {
          const c = (App.state.classes || []).find((x) => x.id === cid);
          return c ? c.name : `班级${cid}`;
        };

        /* 提醒编辑弹窗（添加 / 编辑共用），cid 为所属班级 */
        const editReminderJob = async (cid, rid) => {
          let items;
          try {
            const res = await App.api(`/api/reminders?class_id=${cid}`);
            items = res.items || [];
          } catch (e) { App.toast(e.message, 'err'); return; }
          const isNew = !rid;
          const r = isNew
            ? { id: `r${Date.now().toString(36)}`, name: '', time: '21:30', enabled: true, mention_all: false, content: '' }
            : items.find((x) => x.id === rid);
          if (!r) { App.toast('这条提醒不存在（可能已被删除），请刷新', 'err'); return; }
          App.modal({
            title: isNew ? `添加提醒（${className(cid)}）` : `编辑提醒：${r.name}`,
            okText: '保存',
            html: `
              <label class="field"><span>提醒名称</span><input id="jrName" value="${App.attr(r.name)}" placeholder="例如：填报提醒"></label>
              <div class="grid cols-2" style="margin-top:8px">
                <label class="field"><span>发送时间</span><input id="jrTime" type="time" value="${App.attr(r.time)}"></label>
                <label class="field"><span>@全体成员</span>
                  <select id="jrMention">
                    <option value="0" ${r.mention_all ? '' : 'selected'}>不 @</option>
                    <option value="1" ${r.mention_all ? 'selected' : ''}>@全体成员</option>
                  </select>
                </label>
              </div>
              <label class="field" style="margin-top:8px"><span>提醒内容</span>
                <textarea id="jrContent" style="min-height:150px">${App.esc(r.content)}</textarea>
              </label>
              <label class="field" style="margin-top:8px"><span>定时开关</span>
                <select id="jrEnabled">
                  <option value="1" ${r.enabled ? 'selected' : ''}>开启（每天定时发）</option>
                  <option value="0" ${r.enabled ? '' : 'selected'}>停用</option>
                </select>
              </label>`,
            onOk: async (m) => {
              const name = m.querySelector('#jrName').value.trim();
              const time = m.querySelector('#jrTime').value.trim();
              const content = m.querySelector('#jrContent').value;
              if (!name) { App.toast('请填写提醒名称', 'err'); return false; }
              if (!time) { App.toast('请选择发送时间', 'err'); return false; }
              if (!content.trim()) { App.toast('提醒内容不能为空', 'err'); return false; }
              r.name = name;
              r.time = time;
              r.content = content;
              r.mention_all = m.querySelector('#jrMention').value === '1';
              r.enabled = m.querySelector('#jrEnabled').value === '1';
              if (isNew) items.push(r);
              try {
                await App.api('/api/reminders', 'PUT', { items, class_id: cid });
              } catch (e) { App.toast(e.message, 'err'); return false; }
              App.toast('已保存，定时任务已更新', 'ok');
              await renderJobs();
              return true;
            },
          });
        };

        /* 群汇报时间弹窗（按班级独立） */
        const editReportTime = (cid) => {
          const c = (App.state.classes || []).find((x) => x.id === cid);
          App.modal({
            title: `群汇报时间：${c ? c.name : `班级${cid}`}`,
            okText: '保存',
            html: `
              <label class="field"><span>每天自动发群汇报的时间</span><input id="jrtTime" type="time" value="${App.attr((c && c.qq_report_time) || '22:40')}"></label>
              <div class="hint-text" style="margin-top:6px">只改这一个班的时间；其他班在各自的任务行上改。</div>`,
            onOk: async (m) => {
              const t = m.querySelector('#jrtTime').value.trim();
              if (!t) { App.toast('请选择时间', 'err'); return false; }
              try {
                await App.api(`/api/classes/${cid}`, 'PUT', { settings: { qq_report_time: t } });
              } catch (e) { App.toast(e.message, 'err'); return false; }
              App.toast('群汇报时间已保存', 'ok');
              await App.loadClasses();
              await renderJobs();
              return true;
            },
          });
        };

        const renderJobs = async () => {
          const data = await App.api('/api/jobs');
          $('#jobRows').innerHTML = (data.jobs || []).map((job) => `<tr>
            <td><b>${App.esc(job.name)}</b></td>
            <td class="wrap">${App.esc(jobDesc(job.id))}</td>
            <td>${App.esc(job.next_run || '—')}</td>
            <td style="white-space:nowrap">${jobActions(job.id)}<button class="btn tiny" data-job="${App.attr(job.id)}">立即执行</button></td>
          </tr>`).join('') || '<tr><td colspan="4" class="empty">调度器没有任务</td></tr>';
          $$('#jobRows [data-job]').forEach((btn) => {
            btn.onclick = async () => {
              btn.disabled = true;
              try {
                const res = await App.api(`/api/jobs/${btn.dataset.job}/run`, 'POST');
                App.toast(res.message || (res.ok ? '执行完成' : '执行失败'), res.ok ? 'ok' : 'err');
                await renderJobs();
              } catch (e) { App.toast(e.message, 'err'); } finally { btn.disabled = false; }
            };
          });
          $$('#jobRows [data-edit-report]').forEach((btn) => {
            btn.onclick = () => editReportTime(Number(btn.dataset.editReport));
          });
          $$('#jobRows [data-edit-rem]').forEach((btn) => {
            btn.onclick = () => {
              const sep = btn.dataset.editRem.indexOf(':');
              editReminderJob(Number(btn.dataset.editRem.slice(0, sep)), btn.dataset.editRem.slice(sep + 1));
            };
          });
          $$('#jobRows [data-del-rem]').forEach((btn) => {
            btn.onclick = async () => {
              const sep = btn.dataset.delRem.indexOf(':');
              const cid = btn.dataset.delRem.slice(0, sep);
              const rid = btn.dataset.delRem.slice(sep + 1);
              if (!window.confirm(`确定删除这条提醒吗？（${className(Number(cid))}，删除后不再定时发送）`)) return;
              try {
                const res = await App.api(`/api/reminders?class_id=${cid}`);
                const items = (res.items || []).filter((x) => x.id !== rid);
                await App.api('/api/reminders', 'PUT', { items, class_id: Number(cid) });
                App.toast('已删除，定时任务已更新', 'ok');
                await renderJobs();
              } catch (e) { App.toast(e.message, 'err'); }
            };
          });
        };

        const jobDesc = (jid) => {
          if (/^group_report_c\d+$/.test(jid)) return '每晚把当天人员情况汇总发到该班的 QQ 群（点「编辑时间」改这个班的发送时间）';
          if (/^reminder_c\d+_.+$/.test(jid)) return '每天定时把自定义内容发到该班的 QQ 群';
          if (jid === 'job_auto_export') return '把当天填报保存成 Excel 文件（时间在「基本设置」里改）';
          if (jid === 'job_db_backup') return '每天凌晨自动备份数据库';
          return '';
        };
        const jobActions = (jid) => {
          const mReport = /^group_report_c(\d+)$/.exec(jid || '');
          const mRemind = /^reminder_c(\d+)_(.+)$/.exec(jid || '');
          if (mReport) return `<button class="btn tiny" data-edit-report="${mReport[1]}">编辑时间</button> `;
          if (mRemind) {
            return `<button class="btn tiny" data-edit-rem="${mRemind[1]}:${App.attr(mRemind[2])}">编辑</button> `
              + `<button class="btn tiny danger" data-del-rem="${mRemind[1]}:${App.attr(mRemind[2])}">删除</button> `;
          }
          return '';
        };

        const btnJobAdd = $('#btnJobAddReminder');
        if (btnJobAdd) btnJobAdd.onclick = () => editReminderJob(App.state.classId || 0, '');
        await renderJobs();
      }

      if (state.tab === 'accounts') {
        const loadContacts = async () => {
          const dorms = (await App.api('/api/dorms?with_members=false&active_only=false')).items || [];
          const missing = dorms.filter((d) => d.active && !d.leader_name);
          $('#contactSummary').innerHTML = `共 <b>${dorms.length}</b> 间宿舍，其中 <b style="color:${missing.length ? '#dc2626' : '#16a34a'}">${missing.length}</b> 间还没指定宿舍长。`
            + `<div class="hint-text">系统不做身份认证，这里不需要账号密码，只要登记宿舍长是谁、电话多少，提醒推送和汇报里会用到。</div>`;
          $('#userTable').innerHTML = `
            <thead><tr><th>宿舍号</th><th>宿舍长</th><th>电话</th><th>QQ 群号</th><th class="num">人数</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>${dorms.map((d) => `<tr>
              <td><b>${App.esc(d.room_no)}</b>${d.room_label ? `<div class="hint-text">${App.esc(d.room_label)}</div>` : ''}</td>
              <td>${d.leader_name ? App.esc(d.leader_name) : '<span class="chip warn">未指定</span>'}</td>
              <td>${App.esc(d.leader_phone || '—')}</td>
              <td>${App.esc(d.qq_group_id || '—')}</td>
              <td class="num">${d.member_count}</td>
              <td>${d.active ? '<span class="chip ok">启用</span>' : '<span class="chip gray">停用</span>'}</td>
              <td><button class="btn tiny" data-edit="${d.id}">编辑</button></td>
            </tr>`).join('')}</tbody>`;
          $$('#userTable [data-edit]').forEach((btn) => {
            btn.onclick = () => {
              const dorm = dorms.find((item) => item.id === Number(btn.dataset.edit));
              App.editDorm(dorm, loadContacts);
            };
          });
        };
        await loadContacts();
      }

      if (state.tab === 'sys') {
        const loadSys = async () => {
          const info = await App.api('/api/system/info');
          $('#sysInfo').innerHTML = `
            <div><div class="hint-text">系统版本</div><div>${App.esc(info.app)} v${App.esc(info.version)}</div></div>
            <div><div class="hint-text">服务器时间</div><div>${App.esc(info.server_time)}（${App.esc(info.timezone)}）</div></div>
            <div><div class="hint-text">宿舍 / 人员 / 填报记录 / 账户</div><div>${info.counts.dorms} / ${info.counts.members} / ${info.counts.reports} / ${info.counts.users}</div></div>
            <div><div class="hint-text">今日填报率</div><div>${info.today.rate}%（已填 ${info.today.reported}/${info.today.dorm_total}）</div></div>
            <div><div class="hint-text">数据目录</div><div class="hint-text">${App.esc(info.data_dir)}</div></div>
            <div><div class="hint-text">数据库文件</div><div class="hint-text">${App.esc(info.db_path)}</div></div>`;
        };
        const loadAudit = async () => {
          const data = await App.api('/api/audit?limit=120');
          $('#auditTable').innerHTML = `
            <thead><tr><th>时间</th><th>操作人</th><th>角色</th><th>操作</th><th>对象</th><th class="wrap">详情</th><th>IP</th></tr></thead>
            <tbody>${(data.items || []).map((l) => `<tr>
              <td>${App.esc(l.created_at)}</td><td>${App.esc(l.actor)}</td><td>${App.esc(l.role)}</td>
              <td>${App.esc(l.action)}</td><td>${App.esc(l.target || '')}</td>
              <td class="wrap">${App.esc(l.detail || '')}</td><td>${App.esc(l.ip || '')}</td>
            </tr>`).join('')}</tbody>`;
        };
        $('#btnSysRefresh').onclick = loadSys;
        $('#btnAuditRefresh').onclick = loadAudit;
        $('#btnBackup').onclick = async () => {
          try { await App.download('/api/system/backup', 'app_backup.db'); App.toast('备份已下载', 'ok'); } catch (e) { App.toast(e.message, 'err'); }
        };
        $('#btnExportAllMembers').onclick = async () => {
          try { await App.download('/api/members/export', 'members.xlsx'); } catch (e) { App.toast(e.message, 'err'); }
        };
        $('#btnExportAllReports').onclick = async () => {
          const start = App.shiftDate(-29);
          try { await App.download(`/api/reports/export?start=${start}&end=${App.today()}`, 'reports.xlsx'); } catch (e) { App.toast(e.message, 'err'); }
        };
        $('#btnResetData').onclick = () => {
          App.modal({
            title: '清空全部业务数据',
            okText: '确认清空',
            html: `<div class="hint-text">请输入 <b>清空</b> 两个字以确认：</div>
              <label class="field" style="margin-top:8px"><span>确认文字</span><input id="resetWord" placeholder="清空"></label>
              <div class="hint-text">宿舍、人员、填报记录、推送日志都会被删除，账户和系统配置保留。</div>`,
            onOk: async (modalBox) => {
              if (modalBox.querySelector('#resetWord').value.trim() !== '清空') {
                App.toast('请输入“清空”两个字', 'err');
                return false;
              }
              const res = await App.api('/api/system/reset-data', 'POST', { keep_accounts: true, keep_settings: true });
              App.toast(res.message || '已清空', 'ok');
              await App.loadBase();
              await renderBody();
              return true;
            },
          });
        };
        await loadSys();
        await loadAudit();
      }
      App.applyPermission();
    };

    // 模板变量说明
    try {
      const settings = await App.api('/api/settings');
      App.state.settings = settings.values || {};
      App.state.templateVars = settings.template_vars || {};
      App.state.jobs = settings.jobs || [];
    } catch (e) { /* 忽略 */ }

    await renderBody();
  },
});
