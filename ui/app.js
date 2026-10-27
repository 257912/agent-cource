/* MiniCursor 前端：WebSocket 消费后端事件流，三栏展示对话 / 工具调用 / diff */

const el = (id) => document.getElementById(id);

const messages = el('messages');
const toolList = el('tool-list');
const input = el('input');
const btnSend = el('btn-send');
const btnStop = el('btn-stop');
const btnClear = el('btn-clear');

let ws = null;
let running = false;
let currentAssistant = null;
const cards = new Map(); // tool_call_id -> {card, body, head}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function addMsg(cls, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function setRunning(v) {
  running = v;
  btnStop.disabled = !v;
  btnSend.disabled = v;
  btnSend.textContent = v ? '运行中…' : '发送';
}

/* ---------- 工具卡片 ---------- */
function makeCard(ev) {
  const card = document.createElement('div');
  card.className = 'card';
  const head = document.createElement('div');
  head.className = 'card-head';
  head.innerHTML = `<span class="name">${escapeHtml(ev.name)}</span>` +
    `<span class="status running">运行中</span>`;
  const body = document.createElement('div');
  body.className = 'card-body';

  const args = document.createElement('pre');
  args.className = 'out';
  args.textContent = JSON.stringify(ev.args, null, 2);
  body.appendChild(args);

  card.appendChild(head);
  card.appendChild(body);
  toolList.appendChild(card);
  toolList.scrollTop = toolList.scrollHeight;

  const entry = { card, head, body };
  cards.set(ev.id, entry);
  return entry;
}

function finishCard(ev) {
  const entry = cards.get(ev.id) || makeCard({ id: ev.id, name: ev.name, args: {} });
  const status = entry.head.querySelector('.status');
  status.className = 'status ' + (ev.ok ? 'ok' : 'error');
  status.textContent = ev.ok ? '成功' : '失败' + (ev.error ? '：' + ev.error.slice(0, 60) : '');

  if (ev.error) {
    const p = document.createElement('pre');
    p.className = 'out';
    p.style.color = '#ffb3b3';
    p.textContent = ev.error;
    entry.body.appendChild(p);
  }
  if (ev.diff) {
    const p = document.createElement('pre');
    p.className = 'diff';
    p.innerHTML = renderDiff(ev.diff);
    entry.body.appendChild(p);
  }
  if (ev.output) {
    const kv = document.createElement('div');
    kv.className = 'kv';
    kv.textContent = '输出';
    const p = document.createElement('pre');
    p.className = 'out';
    p.textContent = ev.output;
    entry.body.appendChild(kv);
    entry.body.appendChild(p);
  }
  for (const img of ev.images || []) {
    const im = document.createElement('img');
    im.className = 'preview';
    im.src = `data:${img.mime};base64,${img.b64}`;
    entry.body.appendChild(im);
  }
  toolList.scrollTop = toolList.scrollHeight;
}

function renderDiff(diff) {
  return diff.split('\n').map((line) => {
    const safe = escapeHtml(line);
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) {
      return `<span class="diff-meta">${safe}</span>`;
    }
    if (line.startsWith('+')) return `<span class="diff-add">${safe}</span>`;
    if (line.startsWith('-')) return `<span class="diff-del">${safe}</span>`;
    return safe;
  }).join('\n');
}

/* ---------- 事件处理 ---------- */
function handleEvent(ev) {
  switch (ev.type) {
    case 'hello':
      el('badge-mode').textContent = ev.mode === 'remote' ? '已连接模型' : '离线假模型';
      el('badge-mode').className = 'badge' + (ev.mode === 'mock' ? ' mock' : '');
      el('badge-model').textContent = ev.mode === 'mock' ? 'mock' : ev.model;
      el('badge-ws').textContent = ev.workspace;
      if (ev.warning) addMsg('system', '提示：' + ev.warning);
      if (ev.mcp && ev.mcp.tools && ev.mcp.tools.length) {
        addMsg('system', 'MCP 已接入：' + ev.mcp.tools.join(', '));
      }
      break;
    case 'run.start':
      setRunning(true);
      currentAssistant = null;
      break;
    case 'assistant.delta':
      if (!currentAssistant) {
        currentAssistant = addMsg('assistant', '');
        currentAssistant.classList.add('cursor');
      }
      currentAssistant.textContent += ev.text;
      messages.scrollTop = messages.scrollHeight;
      break;
    case 'assistant.message':
      if (currentAssistant) {
        currentAssistant.textContent = ev.text;
        currentAssistant.classList.remove('cursor');
      } else if (ev.text) {
        addMsg('assistant', ev.text);
      }
      currentAssistant = null;
      break;
    case 'tool.call':
      makeCard(ev);
      break;
    case 'tool.result':
      finishCard(ev);
      break;
    case 'error':
      addMsg('error', ev.message || '未知错误');
      break;
    case 'run.end':
      if (currentAssistant) currentAssistant.classList.remove('cursor');
      if (ev.reason === 'cancelled') addMsg('system', '已中断（用户主动停止）');
      else if (ev.reason === 'max_steps') addMsg('system', '达到最大步数，已停止');
      setRunning(false);
      break;
    case 'session.reset':
      messages.innerHTML = '';
      toolList.innerHTML = '<div class="empty">会话已清空。</div>';
      cards.clear();
      break;
  }
}

/* ---------- WebSocket ---------- */
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => {
    try { handleEvent(JSON.parse(e.data)); } catch (err) { console.error(err); }
  };
  ws.onclose = () => {
    el('badge-mode').textContent = '已断开，重连中…';
    setRunning(false);
    setTimeout(connect, 1500);
  };
}

function send(text) {
  if (!text || running) return;
  addMsg('user', text);
  input.value = '';
  ws.send(JSON.stringify({ type: 'run', text }));
  setRunning(true);
}

/* ---------- 文件树 ---------- */
async function loadTree(path = '') {
  const res = await fetch('/api/tree?path=' + encodeURIComponent(path));
  const data = await res.json();
  renderTree(data.root, data.items);
}

function renderTree(root, items) {
  const tree = el('tree');
  tree.innerHTML = '';
  const head = document.createElement('div');
  head.className = 'node';
  head.innerHTML = `<span class="kind">▾</span><span>${escapeHtml(root || '.')}</span>`;
  head.onclick = () => loadTree('');
  tree.appendChild(head);

  for (const item of items) {
    const node = document.createElement('div');
    node.className = 'node ' + item.type;
    node.innerHTML = `<span class="kind">${item.type === 'dir' ? '▸' : '·'}</span><span>${escapeHtml(item.name)}</span>`;
    node.title = item.path;
    node.onclick = () => {
      if (item.type === 'dir') loadTree(item.path);
      else insertPath(item.path);
    };
    tree.appendChild(node);
  }
}

function insertPath(path) {
  input.value += (input.value ? ' ' : '') + path;
  input.focus();
}

/* ---------- 绑定 ---------- */
btnSend.onclick = () => send(input.value.trim());
btnStop.onclick = () => ws && ws.send(JSON.stringify({ type: 'cancel' }));
btnClear.onclick = () => {
  if (ws) ws.send(JSON.stringify({ type: 'reset' }));
};
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send(input.value.trim());
  }
});

connect();
loadTree('');
