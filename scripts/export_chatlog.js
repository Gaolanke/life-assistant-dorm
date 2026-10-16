// 生成结构化的聊天记录 JSON（含图片、工具调用摘要）
const fs = require('fs');
const path = require('path');
const os = require('os');

const SRC = process.argv[2];
const OUT = process.argv[3];

const lines = fs.readFileSync(SRC, 'utf8').split('\n').filter((l) => l.trim());
const records = [];
for (const l of lines) {
  try { records.push(JSON.parse(l)); } catch (e) {}
}
records.sort((a, b) => (a.seq || 0) - (b.seq || 0));

const ATT_ROOT = path.join(os.homedir(), '.dsh', 'attachments', 'v1', 'objects');

function resolveAttachment(att) {
  if (!att || !att.attachmentId) return null;
  const hash = String(att.attachmentId).replace(/^sha256:/, '');
  if (hash.length < 3) return null;
  const p = path.join(ATT_ROOT, hash.slice(0, 2), hash);
  return fs.existsSync(p) ? p : null;
}

function ts(ms) {
  if (!ms) return '';
  const d = new Date(ms);
  const p2 = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`;
}

// 工具调用摘要
function parseArgs(raw) {
  if (raw === null || raw === undefined) return {};
  if (typeof raw === 'object') return raw;
  const s = String(raw).trim();
  if (!s) return {};
  try {
    const o = JSON.parse(s);
    return typeof o === 'object' && o !== null ? o : { _value: o };
  } catch (e) {
    return { _raw: s };
  }
}

function summarizeTool(name, input) {
  if (!input || typeof input !== 'object') return '';
  const pick = (k) => (input[k] === undefined || input[k] === null ? '' : String(input[k]));
  switch (name) {
    case 'pwsh':
      return (pick('description') ? pick('description') + '：' : '') +
        pick('command').replace(/\s+/g, ' ').slice(0, 200);
    case 'read':
      return pick('file_path') + (input.offset ? ` (offset ${input.offset})` : '');
    case 'write':
      return pick('file_path') + (input.content ? `（${String(input.content).length} 字符）` : '');
    case 'edit':
      return pick('file_path');
    case 'grep':
      return `/${pick('pattern')}/ ${pick('path') || ''} ${pick('include') ? '(' + pick('include') + ')' : ''}`.trim();
    case 'glob':
      return `${pick('pattern')} ${pick('path') || ''}`.trim();
    case 'web_search':
      return JSON.stringify(input.queries || '').slice(0, 200);
    case 'web_fetch':
      return pick('url');
    case 'todo_write':
      return `${(input.todos || []).length} 项待办`;
    case 'present':
      return (input.files || []).map((f) => f.path).join(', ');
    case 'job_output':
    case 'job_kill':
      return pick('job_id');
    case 'ask_user_question':
      return (input.questions || []).map((q) => q.question || q.header || '').join(' | ').slice(0, 200);
    case 'skill':
      return pick('name');
    case 'spawn_teammate':
      return pick('name') + ' — ' + pick('description');
    case 'send_message':
      return `→ ${pick('target')}: ${pick('message').slice(0, 80)}`;
    case 'subagent':
    case 'subagent_fork':
      return pick('description');
    case 'workflow':
      return (input.meta && input.meta.name) || '';
    case 'schedule_create':
      return pick('title');
    case 'create_goal':
      return pick('objective').slice(0, 120);
    case 'update_goal':
      return `goal ${pick('action')}`;
    case 'load_workspace_dependencies':
      return '';
    default: {
      if (input._raw) return input._raw.slice(0, 180);
      const keys = Object.keys(input).slice(0, 3);
      return keys.map((k) => `${k}=${String(input[k]).replace(/\s+/g, ' ').slice(0, 70)}`).join(' ');
    }
  }
}

const turns = [];
let cur = null;
const toolCalls = [];   // 全局工具调用（带 turn）

for (const r of records) {
  if (r.type === 'turn/start') {
    cur = {
      turn: (r.data && r.data.turn) || turns.length + 1,
      time: ts(r.time),
      user: [],
      assistant: [],
      tools: [],
    };
    turns.push(cur);
    continue;
  }
  if (r.type === 'user/message') {
    const kind = (r.data.source || {}).kind;
    if (kind !== 'user') continue;
    const blocks = [];
    for (const c of r.data.content || []) {
      if (c.type === 'text' && c.text) blocks.push({ type: 'text', text: c.text });
      else if (c.type === 'image') {
        const p = resolveAttachment(c.attachment);
        blocks.push({
          type: 'image',
          name: (c.attachment && c.attachment.name) || 'image.png',
          width: c.attachment && c.attachment.width,
          height: c.attachment && c.attachment.height,
          path: p,
        });
      }
    }
    if (!blocks.length) continue;
    if (!cur) {
      cur = { turn: turns.length + 1, time: ts(r.time), user: [], assistant: [], tools: [] };
      turns.push(cur);
    }
    cur.user.push({ time: ts(r.time), blocks });
  } else if (r.type === 'assistant/message') {
    const msg = r.data.message || {};
    const text = (msg.content || []).filter((c) => c.type === 'text' && c.text).map((c) => c.text).join('').trim();
    if (!text) continue;
    if (!cur) {
      cur = { turn: turns.length + 1, time: ts(r.time), user: [], assistant: [], tools: [] };
      turns.push(cur);
    }
    cur.assistant.push({ time: ts(r.time), step: r.data.step, text });
  } else if (r.type === 'tool/call') {
    const d = r.data || {};
    const name = d.name || d.toolName || '?';
    const input = parseArgs(d.arguments !== undefined ? d.arguments : d.input || d.args);
    const item = { time: ts(r.time), name, summary: summarizeTool(name, input) };
    if (cur) cur.tools.push(item);
    toolCalls.push(item);
  }
}

const meta = records.find((r) => r.type === 'session') || {};
const result = {
  sessionId: meta.id || '',
  cwd: meta.cwd || '',
  createdAt: meta.createdAt ? ts(meta.createdAt) : '',
  exportedAt: ts(Date.now()),
  turns,
  toolCallTotal: toolCalls.length,
};

fs.writeFileSync(OUT, JSON.stringify(result, null, 1), 'utf8');

const userBlocks = turns.reduce((s, t) => s + t.user.reduce((a, u) => a + u.blocks.length, 0), 0);
const imgTotal = turns.reduce((s, t) => s + t.user.reduce((a, u) => a + u.blocks.filter((b) => b.type === 'image').length, 0), 0);
const asstText = turns.reduce((s, t) => s + t.assistant.reduce((a, x) => a + x.text.length, 0), 0);

console.log('轮数:', turns.length);
console.log('用户消息块:', userBlocks, '（其中图片', imgTotal, '张）');
console.log('助手文本块:', turns.reduce((s, t) => s + t.assistant.length, 0), `（${asstText.toLocaleString()} 字）`);
console.log('工具调用:', toolCalls.length);
console.log('图片已解析到本地文件的:', turns.reduce((s, t) => s + t.user.reduce((a, u) => a + u.blocks.filter((b) => b.type === 'image' && b.path).length, 0), 0));
console.log('已写入', OUT);
