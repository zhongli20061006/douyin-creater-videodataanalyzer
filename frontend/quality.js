// 数据质量页面逻辑
const MAX_SELECT = 200;
let currentIssues = [];

function fmtTime(t) {
  if (!t) return '--';
  const d = new Date(t);
  const pad = (n) => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

async function api(path, opts) {
  opts = opts || {};
  const headers = { 'Content-Type': 'application/json' };
  if (opts.body) opts.body = JSON.stringify(opts.body);
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '请求失败');
  }
  return res.json();
}

const LABELS = {
  empty: '疑似无效',
  placeholder: '占位页标题',
  stale: '陈旧未更新',
  missing_author: '作者缺失',
};

async function loadReport() {
  document.getElementById('table-body').innerHTML = '<tr class="empty-row"><td colspan="6">加载中...</td></tr>';
  try {
    const data = await api('/api/quality/report');
    currentIssues = data.issues;
    document.getElementById('stat-total').textContent = data.summary.total;
    document.getElementById('stat-authors').textContent = data.summary.authors;
    document.getElementById('stat-issues').textContent = data.issues.length;
    document.getElementById('stat-latest').textContent = fmtTime(data.summary.latest_update);
    renderTable(data.issues);
  } catch (e) {
    document.getElementById('table-body').innerHTML = '<tr class="empty-row"><td colspan="6">加载失败: ' + e.message + '</td></tr>';
  }
}

function renderTable(issues) {
  const tbody = document.getElementById('table-body');
  if (!issues || issues.length === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="6">暂无问题数据</td></tr>';
    return;
  }
  tbody.innerHTML = issues.map(function (r) {
    const tags = r.issue_types.map(function (t) { return LABELS[t] || t; }).join('、');
    return '<tr>' +
      '<td><input type="checkbox" class="row-check" value="' + r.video_id + '"></td>' +
      '<td>' + r.video_id + '</td>' +
      '<td>' + escHtml(r.video_title || '--') + '</td>' +
      '<td>' + escHtml(r.author_name || '--') + '</td>' +
      '<td>' + escHtml(tags) + '</td>' +
      '<td>' + fmtTime(r.update_time) + '</td>' +
    '</tr>';
  }).join('');
}

function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function selectedIds() {
  return Array.prototype.map.call(document.querySelectorAll('.row-check:checked'), function (c) { return c.value; });
}

document.getElementById('btn-refresh').addEventListener('click', loadReport);

document.getElementById('check-all').addEventListener('change', function () {
  const checked = this.checked;
  document.querySelectorAll('.row-check').forEach(function (c) { c.checked = checked; });
});

document.getElementById('btn-fix').addEventListener('click', async function () {
  if (!confirm('确认执行安全修正（标题去空白/换行）？')) return;
  try {
    const res = await api('/api/quality/fix', { method: 'POST', body: {} });
    alert('已修正 ' + res.fixed + ' 条');
    loadReport();
  } catch (e) {
    alert('修正失败: ' + e.message);
  }
});

document.getElementById('btn-delete').addEventListener('click', function () {
  const ids = selectedIds();
  if (ids.length === 0) {
    alert('请先勾选要删除的问题数据');
    return;
  }
  if (ids.length > MAX_SELECT) {
    alert('单次最多勾选 ' + MAX_SELECT + ' 条，请分批操作');
    return;
  }
  document.getElementById('modal-body').textContent = '确认删除 ' + ids.length + ' 条问题数据？此操作不可恢复。';
  document.getElementById('modal-overlay').style.display = 'flex';
  document.getElementById('btn-confirm-delete').onclick = async function () {
    try {
      const res = await api('/api/quality/delete', { method: 'POST', body: { video_ids: ids } });
      alert('已删除 ' + res.deleted + ' 条' + (res.rejected.length ? '，拒绝 ' + res.rejected.length + ' 条' : ''));
      document.getElementById('modal-overlay').style.display = 'none';
      loadReport();
    } catch (e) {
      alert('删除失败: ' + e.message);
    }
  };
});

document.getElementById('btn-export').addEventListener('click', function () {
  window.location.href = '/api/quality/export?scope=all';
});

document.getElementById('modal-close').addEventListener('click', function () {
  document.getElementById('modal-overlay').style.display = 'none';
});
document.getElementById('btn-cancel').addEventListener('click', function () {
  document.getElementById('modal-overlay').style.display = 'none';
});
document.getElementById('modal-overlay').addEventListener('click', function (e) {
  if (e.target === this) document.getElementById('modal-overlay').style.display = 'none';
});

document.addEventListener('DOMContentLoaded', loadReport);
