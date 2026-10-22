'use strict';
const $ = id => document.getElementById(id);
let csrf = '', publicJoin = false, refreshing = false;
let accountCSRF = '';
let bandwidthUnit = 'MB/s', bandwidthSample = null;
try { if (localStorage.getItem('bandwidth-unit') === 'Mbps') bandwidthUnit = 'Mbps'; } catch {}
function renderBandwidth() {
  const ready = bandwidthSample?.status === 'ready';
  const factor = bandwidthUnit === 'Mbps' ? 8 / 1e6 : 1 / 1e6;
  for (const [id, key] of [['bandwidth-rx', 'rx_bytes_per_second'], ['bandwidth-tx', 'tx_bytes_per_second']]) {
    const value = bandwidthSample?.[key];
    $(id).textContent = ready && Number.isFinite(value) && value >= 0 ? (value * factor).toFixed(3) : '—';
  }
  for (const label of document.querySelectorAll('.bandwidth-unit')) label.textContent = bandwidthUnit;
  for (const button of document.querySelectorAll('[data-bandwidth-unit]'))
    button.setAttribute('aria-pressed', String(button.dataset.bandwidthUnit === bandwidthUnit));
  const messages = {ready:'服务器网卡实时收发速率', warming_up:'正在采样服务器流量…',
    unavailable:'服务器流量暂不可读', stale:'采样已过期，等待恢复', disconnected:'连接中断，等待刷新'};
  $('bandwidth-status').textContent = messages[bandwidthSample?.status] || messages.warming_up;
}
for (const button of document.querySelectorAll('[data-bandwidth-unit]')) button.onclick = () => {
  bandwidthUnit = button.dataset.bandwidthUnit;
  try { localStorage.setItem('bandwidth-unit', bandwidthUnit); } catch {}
  renderBandwidth();
};
renderBandwidth();
async function api(path, data) {
  const response = await fetch(path, {method:data === undefined ? 'GET' : 'POST',
    headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'X-Account-CSRF':accountCSRF},
    ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  const text = await response.text();
  let value;
  try { value = JSON.parse(text); } catch { value = {error:text}; }
  if (!response.ok) throw new Error(value.error || '请求失败，请稍后重试。');
  return value;
}
function feedback(id, error) { $(id).textContent = error.message || String(error); }
function timeLabel(seconds) {
  if (seconds >= 86400) return (seconds / 86400).toFixed(1) + ' 天';
  if (seconds >= 3600) return (seconds / 3600).toFixed(1) + ' 时';
  return Math.floor(seconds / 60) + ' 分';
}
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const s = await api('/api/status');
    bandwidthSample = s.bandwidth;
    renderBandwidth();
    document.title = s.name + ' · Buggcraft';
    $('node-name').textContent = s.name;
    $('node-name-heading').textContent = s.name;
    $('health').textContent = s.status === 'online' ? '节点在线 · 连接已就绪' : '节点维护中 · 暂停新房间';
    document.body.classList.remove('offline');
    for (const k of ['rooms','players']) $(k).textContent = s[k];
    $('game-players').textContent = s.game_counts_unknown ? s.game_players + '+' : s.game_players;
    $('game-coverage').textContent = s.game_counts_unknown ? s.game_counts_unknown + ' 个房间游戏人数暂不可读' : '房主上报，已排除启动器聊天角色';
    const c = s.capacity;
    $('capacity-bandwidth').textContent = c.bandwidth_mb_s ? c.bandwidth_mb_s.toFixed(3) : '未配置';
    $('capacity-visitors').textContent = c.recommended_visitors === null ? '待设置带宽' : c.admitted_visitors + ' / ' + c.recommended_visitors + ' 人';
    $('capacity-rate').textContent = c.payload_mb_s.toFixed(3);
    $('capacity-explanation').textContent = c.recommended_visitors === null ? '管理员可设置实际出口带宽，以启用访客接纳限制。' :
      '按每位访客 ' + c.per_player_mb_s + ' MB/s 预算，保留 ' + c.reserve_percent + '% 空闲，另计 15% 协议开销。首次加载峰值需持续观察。';
    $('uptime').textContent = timeLabel(s.uptime_seconds);
    $('room-limit').textContent = '房间容量 ' + s.max_rooms;
    $('network-count').textContent = s.network_nodes + ' 个在线节点';
    $('fingerprint').textContent = s.fingerprint;
    $('node-id').textContent = 'NODE ' + s.id;
    publicJoin = s.public_join;
    $('show-register').hidden = !s.registration_open;
    emailRequired = !!s.email_verification;
    $('email-registration-fields').hidden = !emailRequired;
    $('register-email').required = emailRequired;
    $('register-email-code').required = emailRequired;
    if (!s.registration_open && !$('account-register').hidden) accountEntry('login');
    $('network-mode').textContent = s.network_mode === 'federated' ? '公开联邦节点 · 签名心跳约每 2 秒同步，超时后尝试其他入口。' : '独立节点 · 未加入联邦，联机限于此节点。';
    $('access-label').hidden = publicJoin;
    $('network-list').replaceChildren(...s.nodes.map(n => {
      const card = document.createElement('article'); card.className = 'node-card';
      const symbol = document.createElement('span'); symbol.className = 'node-symbol'; symbol.textContent = '⌘';
      const content = document.createElement('div'), title = document.createElement('strong'), info = document.createElement('small');
      const states = {online:'直连正常',indirect:'其他节点见到心跳',suspect:'暂时不可达',offline:'离线或尚未连通',blocked:'已隔离'};
      title.textContent = n.name; info.textContent = n.local ? '当前节点' : (states[n.status] || n.status) + (n.heartbeat_age === null ? '' : ' · ' + n.heartbeat_age + ' 秒前');
      content.append(title, info);
      const dot = document.createElement('span'); dot.className = 'node-indicator';
      dot.classList.add(n.status);
      card.append(symbol, content, dot); return card;
    }));
  } catch {
    bandwidthSample = {status:'disconnected'};
    renderBandwidth();
    $('health').textContent = '状态暂不可用 · 等待恢复';
    document.body.classList.add('offline');
  } finally { refreshing = false; }
}
for (const button of document.querySelectorAll('[data-close]'))
  button.addEventListener('click', () => $(button.dataset.close).close());
$('open-connect').onclick = () => { $('connect-dialog').showModal(); };
$('connect-form').onsubmit = async event => {
  event.preventDefault();
  const button = event.submitter; button.disabled = true; $('connect-feedback').textContent = '';
  try {
    const result = await api('/api/profile', {password:$('access-password').value});
    $('access-password').value = '';
    $('player-code').value = result.code; $('connect-result').hidden = false;
  } catch (e) { feedback('connect-feedback', e); } finally { button.disabled = false; }
};
$('copy-code').onclick = async () => {
  try { await navigator.clipboard.writeText($('player-code').value); $('connect-feedback').textContent = '已复制。在启动器大厅的节点菜单中打开「添加与管理节点」，粘贴后验证添加。'; }
  catch { $('player-code').select(); $('connect-feedback').textContent = '请复制已选中的添加码。'; }
};
refresh(); setInterval(refresh, 5000);
