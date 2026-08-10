// ── State ──
const state = {
  page: 1,
  pageSize: 20,
  search: '',
  sortBy: 'crawl_time',
  order: 'desc',
  total: 0,
};

// ── Formatting ──
function fmtNum(n) {
  if (n == null) return '--';
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return n.toLocaleString();
}

function fmtTime(t) {
  if (!t) return '--';
  const d = new Date(t);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// ── Toast ──
let toastId = 0;
function toast(msg, type) {
  type = type || 'info';
  const container = document.querySelector('.toast-container');
  if (!container) {
    const div = document.createElement('div');
    div.className = 'toast-container';
    document.body.appendChild(div);
  }
  const id = ++toastId;
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.querySelector('.toast-container').appendChild(el);
  setTimeout(function () { el.remove(); }, 3000);
}

// ── API helpers ──
async function api(path, opts) {
  opts = opts || {};
  const headers = { 'Content-Type': 'application/json' };
  if (opts.body) opts.body = JSON.stringify(opts.body);
  const res = await fetch(path, Object.assign({}, opts, { headers: headers }));
  if (!res.ok) {
    const err = await res.json().catch(function () { return { detail: res.statusText }; });
    throw new Error(err.detail || '请求失败');
  }
  return res.json();
}

// ── Load Stats ──
async function loadStats() {
  try {
    const stats = await api('/api/stats');
    document.getElementById('stat-videos').textContent = fmtNum(stats.total_videos);
    document.getElementById('stat-authors').textContent = fmtNum(stats.total_authors);
    document.getElementById('stat-likes').textContent = fmtNum(stats.total_likes);
    document.getElementById('stat-comments').textContent = fmtNum(stats.total_comments);
    document.getElementById('stat-shares').textContent = fmtNum(stats.total_shares);
    document.getElementById('stat-plays').textContent = fmtNum(stats.total_plays);
    document.getElementById('queue-badge').textContent = '队列: ' + stats.queue_length;
  } catch (e) {
    console.error('加载统计失败', e);
  }
}

// ── Load Video List ──
async function loadVideos() {
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '<tr class="empty-row"><td colspan="9"><span class="spinner"></span> 加载中...</td></tr>';

  const params = new URLSearchParams({
    page: state.page,
    page_size: state.pageSize,
    search: state.search,
    sort_by: state.sortBy,
    order: state.order,
  });

  try {
    const data = await api('/api/videos?' + params.toString());
    state.total = data.total;
    renderTable(data.data);
    renderPagination(data.total, data.page, data.total_pages, data.page_size);
  } catch (e) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="9">加载失败: ' + e.message + '</td></tr>';
    toast('加载视频列表失败: ' + e.message, 'error');
  }
}

function renderTable(rows) {
  const tbody = document.getElementById('table-body');
  if (!rows || rows.length === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="9">暂无数据</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(function (r) {
    return '<tr onclick="showDetail(\'' + r.video_id + '\')">' +
      '<td><span class="video-id">' + (r.video_id || '--') + '</span></td>' +
      '<td title="' + escHtml(r.video_title || '') + '">' + escHtml(truncate(r.video_title, 30)) + '</td>' +
      '<td><span class="author-name">' + escHtml(r.author_name || '--') + '</span></td>' +
      '<td class="num-cell">' + fmtNum(r.like_count) + '</td>' +
      '<td class="num-cell">' + fmtNum(r.comment_count) + '</td>' +
      '<td class="num-cell">' + fmtNum(r.share_count) + '</td>' +
      '<td class="num-cell">' + fmtNum(r.play_count) + '</td>' +
      '<td>' + fmtTime(r.crawl_time) + '</td>' +
      '<td onclick="event.stopPropagation()">' +
        '<button class="btn btn-danger btn-xs" onclick="deleteVideo(\'' + r.video_id + '\')">删除</button>' +
      '</td>' +
    '</tr>';
  }).join('');
}

function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function truncate(s, n) {
  if (!s) return '--';
  return s.length > n ? s.slice(0, n) + '...' : s;
}

// ── Pagination ──
function renderPagination(total, page, totalPages, pageSize) {
  document.getElementById('page-info').textContent =
    '共 ' + total + ' 条，第 ' + page + '/' + totalPages + ' 页';

  if (totalPages <= 1) {
    document.getElementById('page-btns').innerHTML = '';
    return;
  }

  var html = '';
  html += '<button class="page-btn" onclick="goPage(1)" ' + (page <= 1 ? 'disabled' : '') + '>«</button>';
  html += '<button class="page-btn" onclick="goPage(' + (page - 1) + ')" ' + (page <= 1 ? 'disabled' : '') + '>‹</button>';

  var start = Math.max(1, page - 2);
  var end = Math.min(totalPages, page + 2);
  if (start > 1) html += '<span class="page-btn" style="border:none;cursor:default">...</span>';
  for (var i = start; i <= end; i++) {
    html += '<button class="page-btn' + (i === page ? ' active' : '') + '" onclick="goPage(' + i + ')">' + i + '</button>';
  }
  if (end < totalPages) html += '<span class="page-btn" style="border:none;cursor:default">...</span>';

  html += '<button class="page-btn" onclick="goPage(' + (page + 1) + ')" ' + (page >= totalPages ? 'disabled' : '') + '>›</button>';
  html += '<button class="page-btn" onclick="goPage(' + totalPages + ')" ' + (page >= totalPages ? 'disabled' : '') + '>»</button>';

  document.getElementById('page-btns').innerHTML = html;
}

function goPage(p) {
  if (p < 1 || p > Math.ceil(state.total / state.pageSize)) return;
  state.page = p;
  loadVideos();
}

// ── Detail Modal ──
async function showDetail(videoId) {
  document.getElementById('modal-title').textContent = '视频详情 - ' + videoId;
  document.getElementById('modal-body').innerHTML = '<div style="text-align:center;padding:40px"><span class="spinner"></span> 加载中...</div>';
  document.getElementById('modal-overlay').style.display = 'flex';

  try {
    const v = await api('/api/videos/' + videoId);
    document.getElementById('modal-body').innerHTML =
      '<div class="detail-grid">' +
        '<span class="detail-label">视频ID</span><span class="detail-value"><span class="video-id">' + escHtml(v.video_id) + '</span></span>' +
        '<span class="detail-label">标题</span><span class="detail-value">' + escHtml(v.video_title || '--') + '</span>' +
        '<span class="detail-label">描述</span><span class="detail-value">' + escHtml(v.video_desc || '--') + '</span>' +
        '<span class="detail-label">作者</span><span class="detail-value"><span class="author-name">' + escHtml(v.author_name || '--') + '</span> (ID: ' + escHtml(v.author_id || '--') + ')</span>' +
        '<span class="detail-label">发布时间</span><span class="detail-value">' + fmtTime(v.publish_time) + '</span>' +
        '<span class="detail-label">点赞</span><span class="detail-value">' + fmtNum(v.like_count) + '</span>' +
        '<span class="detail-label">评论</span><span class="detail-value">' + fmtNum(v.comment_count) + '</span>' +
        '<span class="detail-label">分享</span><span class="detail-value">' + fmtNum(v.share_count) + '</span>' +
        '<span class="detail-label">播放</span><span class="detail-value">' + fmtNum(v.play_count) + '</span>' +
        '<span class="detail-label">视频链接</span><span class="detail-value">' + (v.video_url || '--') + '</span>' +
        '<span class="detail-label">封面</span><span class="detail-value">' + (v.cover_url || '--') + '</span>' +
        '<span class="detail-label">爬取时间</span><span class="detail-value">' + fmtTime(v.crawl_time) + '</span>' +
        '<span class="detail-label">更新时间</span><span class="detail-value">' + fmtTime(v.update_time) + '</span>' +
      '</div>';
  } catch (e) {
    document.getElementById('modal-body').innerHTML = '<div style="text-align:center;padding:40px;color:var(--danger)">加载失败: ' + e.message + '</div>';
  }
}

function closeModal() {
  document.getElementById('modal-overlay').style.display = 'none';
}

document.getElementById('modal-close').addEventListener('click', closeModal);
document.getElementById('modal-overlay').addEventListener('click', function (e) {
  if (e.target === this) closeModal();
});

// ── Delete ──
async function deleteVideo(videoId) {
  if (!confirm('确定删除视频 ' + videoId + ' 吗？')) return;
  try {
    await api('/api/videos/' + videoId, { method: 'DELETE' });
    toast('已删除: ' + videoId, 'success');
    loadVideos();
    loadStats();
  } catch (e) {
    toast('删除失败: ' + e.message, 'error');
  }
}

// ── Crawl Panel ──
var crawlVisible = false;
document.getElementById('btn-crawl-toggle').addEventListener('click', function () {
  crawlVisible = !crawlVisible;
  document.getElementById('crawl-panel').style.display = crawlVisible ? 'block' : 'none';
  this.textContent = crawlVisible ? '收起' : '+ 添加爬取任务';
});

document.getElementById('btn-crawl-cancel').addEventListener('click', function () {
  crawlVisible = false;
  document.getElementById('crawl-panel').style.display = 'none';
  document.getElementById('btn-crawl-toggle').textContent = '+ 添加爬取任务';
});

document.getElementById('crawl-file').addEventListener('change', function (e) {
  var file = e.target.files[0];
  if (!file) return;
  var reader = new FileReader();
  reader.onload = function (ev) {
    document.getElementById('crawl-ids').value = ev.target.result;
  };
  reader.readAsText(file);
});

document.getElementById('btn-crawl-submit').addEventListener('click', async function () {
  var raw = document.getElementById('crawl-ids').value.trim();
  if (!raw) {
    toast('请输入视频ID', 'error');
    return;
  }
  var ids = raw.split(/[\n,]+/).map(function (s) { return s.trim(); }).filter(Boolean);
  if (ids.length === 0) {
    toast('未提取到有效视频ID', 'error');
    return;
  }

  var btn = this;
  btn.disabled = true;
  btn.textContent = '推送中...';

  try {
    var result = await api('/api/crawl', {
      method: 'POST',
      body: { video_ids: ids, task_type: 'video' },
    });
    var el = document.getElementById('crawl-result');
    el.style.display = 'block';
    el.className = 'crawl-result success';
    el.textContent = '已推送 ' + result.pushed + ' 个任务，当前队列长度: ' + result.queue_length;
    document.getElementById('crawl-ids').value = '';
    loadStats();
    toast('推送成功: ' + result.pushed + ' 个任务', 'success');
  } catch (e) {
    var el = document.getElementById('crawl-result');
    el.style.display = 'block';
    el.className = 'crawl-result error';
    el.textContent = '推送失败: ' + e.message;
    toast('推送失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '推送到 Redis 队列';
  }
});

// ── Toolbar Events ──
document.getElementById('btn-search').addEventListener('click', function () {
  state.search = document.getElementById('search-input').value.trim();
  state.page = 1;
  loadVideos();
});

document.getElementById('btn-clear-search').addEventListener('click', function () {
  document.getElementById('search-input').value = '';
  state.search = '';
  state.page = 1;
  loadVideos();
});

document.getElementById('search-input').addEventListener('keydown', function (e) {
  if (e.key === 'Enter') {
    state.search = this.value.trim();
    state.page = 1;
    loadVideos();
  }
});

document.getElementById('sort-select').addEventListener('change', function () {
  state.sortBy = this.value;
  state.page = 1;
  loadVideos();
});

document.getElementById('order-select').addEventListener('change', function () {
  state.order = this.value;
  state.page = 1;
  loadVideos();
});

document.getElementById('btn-refresh').addEventListener('click', function () { loadVideos(); });
document.getElementById('btn-refresh-stats').addEventListener('click', function () { loadStats(); });

// ── Spider Control ──
function fmtDuration(startedAt) {
  if (!startedAt) return '';
  var diff = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
  if (diff < 60) return diff + '秒前';
  if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
  return Math.floor(diff / 3600) + '小时' + Math.floor((diff % 3600) / 60) + '分钟前';
}

async function loadSpiderStatus() {
  try {
    var s = await api('/api/spider/status');
    var indicator = document.getElementById('spider-indicator');
    var stateEl = document.getElementById('spider-state-text');
    var metaEl = document.getElementById('spider-meta');
    var startBtn = document.getElementById('btn-spider-start');
    var stopBtn = document.getElementById('btn-spider-stop');

    if (s.running) {
      indicator.className = 'spider-indicator running';
      stateEl.textContent = '运行中';
      metaEl.style.display = '';
      startBtn.style.display = 'none';
      stopBtn.style.display = '';
    } else {
      indicator.className = 'spider-indicator stopped';
      stateEl.textContent = '已停止';
      metaEl.style.display = 'none';
      startBtn.style.display = '';
      stopBtn.style.display = 'none';
    }
    document.getElementById('queue-badge').textContent = '队列: --';
    updateSpiderMeta(s);
  } catch (e) {
    console.error('获取爬虫状态失败', e);
  }
  loadStats();
}

function updateSpiderMeta(s) {
  var metaEl = document.getElementById('spider-meta');
  if (!s.running) return;
  var parts = [];
  if (s.pid) parts.push('PID: ' + s.pid);
  if (s.started_at) parts.push(fmtDuration(s.started_at));
  metaEl.textContent = parts.join(' | ');
}

document.getElementById('btn-spider-start').addEventListener('click', async function () {
  try {
    await api('/api/spider/start', { method: 'POST' });
    toast('爬虫已启动', 'success');
    loadSpiderStatus();
  } catch (e) {
    toast('启动失败: ' + e.message, 'error');
  }
});

document.getElementById('btn-spider-stop').addEventListener('click', async function () {
  if (!confirm('确定要停止爬虫吗？')) return;
  try {
    await api('/api/spider/stop', { method: 'POST' });
    toast('爬虫已停止', 'success');
    loadSpiderStatus();
  } catch (e) {
    toast('停止失败: ' + e.message, 'error');
  }
});

var spiderPollTimer = null;
function startSpiderPoll() {
  if (spiderPollTimer) clearInterval(spiderPollTimer);
  loadSpiderStatus();
  spiderPollTimer = setInterval(loadSpiderStatus, 5000);
}

// ── Init ──
document.addEventListener('DOMContentLoaded', function () {
  loadStats();
  loadVideos();
  startSpiderPoll();
});
