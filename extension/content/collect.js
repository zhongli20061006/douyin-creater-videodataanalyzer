/* 抖音个人视频数据分析器 —— content script
 * 主页模式：白名单校验 → 悬浮按钮 → 自动滚动采集播放量 → 分批上报
 * 详情页模式：白名单校验（作者是自己）→ 被动提取互动数据 → 防抖上报
 */
(function () {
  'use strict';
  const P = window.DouyinParse;
  const MAX_VIDEOS = 100;
  const BATCH_SIZE = 100;
  const DETAIL_DEBOUNCE_MS = 60 * 1000;
  const KEY_BACKEND = 'backendBaseUrl';
  const KEY_UID = 'myUid';
  const KEY_SEC_UID = 'mySecUid';
  const KEY_NICKNAME = 'myNickname';
  const DEFAULT_BACKEND = 'http://127.0.0.1:8001';
  const DETAIL_RETRY_TIMES = 4;

  let homeButtonAdded = false;
  let detailStarted = false;
  let lastPath = '';

  function normalizeBase(url) {
    let u = String(url || DEFAULT_BACKEND).trim().replace(/\/+$/, '');
    if (!/^https?:\/\//i.test(u)) u = 'http://' + u;
    return u;
  }

  function storageGet(keys) {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get(keys, resolve);
      } catch (e) {
        // 扩展重新加载后旧 content script 上下文失效，提示刷新页面并降级为空配置
        console.warn('[dy-analyzer] 扩展上下文已失效，请刷新页面', e);
        resolve({});
      }
    });
  }

  function storageSet(obj) {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.set(obj, () => resolve());
      } catch (e) {
        console.warn('[dy-analyzer] 扩展上下文已失效，请刷新页面', e);
        resolve();
      }
    });
  }

  async function getConfig() {
    const data = await storageGet([KEY_BACKEND, KEY_UID, KEY_SEC_UID, KEY_NICKNAME]);
    return {
      backendBaseUrl: normalizeBase(data[KEY_BACKEND]),
      myUid: data[KEY_UID] || '',
      mySecUid: data[KEY_SEC_UID] || '',
      myNickname: data[KEY_NICKNAME] || '',
    };
  }

  function readRenderData() {
    const el = document.querySelector('script#RENDER_DATA');
    if (!el) return null;
    try {
      return JSON.parse(decodeURIComponent(el.textContent || ''));
    } catch (e) {
      return null;
    }
  }

  /** 主页模式白名单：URL 是 /user/* 且主页主人 uid === 登录账号 uid。 */
  function isOwnProfile() {
    if (!/^\/user\//.test(location.pathname)) return false;
    const data = readRenderData();
    if (!data || !data.app || !data.app.user || !data.app.odin) return false;
    const user = data.app.user;
    const odin = data.app.odin;
    return (
      user.isLogin === true &&
      user.info &&
      odin.user_id &&
      String(user.info.uid) === String(odin.user_id)
    );
  }

  function showToast(message) {
    let box = document.getElementById('dy-analyzer-toast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'dy-analyzer-toast';
      box.style.cssText =
        'position:fixed;right:16px;bottom:72px;z-index:2147483647;background:#1d2128;color:#e5e7eb;' +
        'border:1px solid #2d323a;border-radius:8px;padding:10px 14px;font-size:13px;' +
        'box-shadow:0 2px 8px rgba(0,0,0,.35);max-width:320px;word-break:break-all;';
      document.body.appendChild(box);
    }
    box.textContent = message;
    clearTimeout(box._timer);
    box._timer = setTimeout(() => { if (box.parentNode) box.remove(); }, 6000);
  }

  async function report(videos, sourceUrl) {
    const cfg = await getConfig();
    const resp = await fetch(cfg.backendBaseUrl + '/api/extension/videos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_url: sourceUrl, videos: videos }),
    });
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const err = await resp.json();
        detail = err.detail || detail;
      } catch (e) { /* ignore */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function waitForGrowth(root, currentCount, timeoutMs) {
    return new Promise((resolve) => {
      const start = Date.now();
      const timer = setInterval(() => {
        if (
          root.querySelectorAll('li').length > currentCount ||
          Date.now() - start > (timeoutMs || 6000)
        ) {
          clearInterval(timer);
          resolve();
        }
      }, 300);
    });
  }

  /* ---------- 主页模式 ---------- */

  function createCollectButton() {
    const old = document.getElementById('dy-analyzer-btn');
    if (old) old.remove();
    const btn = document.createElement('div');
    btn.id = 'dy-analyzer-btn';
    btn.textContent = '开始采集';
    btn.style.cssText =
      'position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#409eff;color:#fff;' +
      'border-radius:20px;padding:10px 18px;font-size:14px;cursor:pointer;' +
      'box-shadow:0 2px 8px rgba(0,0,0,.35);user-select:none;font-family:system-ui,sans-serif;';
    btn.addEventListener('click', collectProfile);
    document.body.appendChild(btn);
    return btn;
  }

  async function collectProfile() {
    const btn = document.getElementById('dy-analyzer-btn');
    const root = document.querySelector('[data-e2e="user-post-list"]');
    if (!root) {
      showToast('未找到作品列表（user-post-list），请确认在「作品」tab');
      return;
    }
    const cfg = await getConfig();
    const author = { author_name: cfg.myNickname, author_id: cfg.myUid };
    btn.textContent = '采集中…';
    btn.style.pointerEvents = 'none';

    const seen = new Set();
    const collected = [];
    let roundsWithoutNew = 0;

    try {
      while (seen.size < MAX_VIDEOS && roundsWithoutNew < 3) {
        const cards = P.parseProfileCards(root, author);
        let added = 0;
        for (const card of cards) {
          // 防页面篡改：卡片链接里的 secUid 必须与当前登录账号一致
          if (card.sec_uid && card.sec_uid !== cfg.mySecUid) continue;
          if (!seen.has(card.video_id)) {
            seen.add(card.video_id);
            collected.push(card);
            added += 1;
          }
        }
        roundsWithoutNew = added === 0 ? roundsWithoutNew + 1 : 0;
        if (seen.size >= MAX_VIDEOS) break;
        window.scrollTo(0, document.documentElement.scrollHeight);
        await sleep(1500 + Math.random() * 1500);
        await waitForGrowth(root, seen.size);
      }

      const missingCount = collected.reduce(
        (sum, c) => sum + (c.missing_fields || []).length,
        0,
      );
      const rejected = [];
      for (let i = 0; i < collected.length; i += BATCH_SIZE) {
        const batch = collected.slice(i, i + BATCH_SIZE);
        try {
          const res = await report(batch, 'https://www.douyin.com/user/' + cfg.mySecUid);
          for (const r of res.rejected || []) rejected.push(r);
        } catch (e) {
          rejected.push({ video_id: 'batch' + i, reason: String(e.message || e) });
        }
      }
      const reason = seen.size >= MAX_VIDEOS ? '（已达 100 条上限）' : '';
      showToast(
        '采集完成' + reason + '：成功 ' + collected.length + ' 条，字段缺失 ' +
        missingCount + ' 处，被拒 ' + rejected.length + ' 条',
      );
    } catch (e) {
      showToast('采集出错：' + (e && e.message ? e.message : e));
    } finally {
      btn.textContent = '开始采集';
      btn.style.pointerEvents = 'auto';
    }
  }

  /* ---------- 详情页模式 ---------- */

  /** 页面是否包含指向「当前登录账号」的作者链接（详情页作者区必有一个）。 */
  function hasSelfAuthorLink(mySecUid) {
    if (!mySecUid) return false;
    return !!document.querySelector('a[href*="/user/' + mySecUid + '"]');
  }

  /** 当前页面是否包含详情数据容器（主页浮层或独立 /video/ 页均适用）。 */
  function isDetailView() {
    return !!document.querySelector('[data-e2e="feed-video"]');
  }

  /** 同步当前视频详情；manual=true 时所有失败都给出明确提示（用于手动排查）。 */
  async function maybeCollectDetail(manual) {
    if (!isDetailView()) {
      if (manual) showToast('当前页面没有详情数据（feed-video）');
      return false;
    }
    const cfg = await getConfig();
    if (!cfg.mySecUid) {
      showToast('请先在自己主页点一次「开始采集」，再浏览视频详情页');
      return false;
    }
    if (!hasSelfAuthorLink(cfg.mySecUid)) {
      console.log('[dy-analyzer] 非自己视频，跳过:', location.href);
      if (manual) showToast('当前视频作者不是自己，不采集');
      return false; // 别人的视频，忽略
    }
    const videoEl = document.querySelector('[data-e2e="feed-video"]');
    if (!videoEl) {
      console.log('[dy-analyzer] feed-video 未就绪，重试:', location.href);
      if (manual) showToast('详情数据（feed-video）尚未加载，请稍后重试');
      return false;
    }
    const detail = P.parseVideoDetail(document);
    if (!detail) {
      showToast('未解析到 video_id');
      return false;
    }
    const key = 'detail_last_' + detail.video_id;
    const stored = await storageGet(key);
    if (stored[key] && Date.now() - stored[key] < DETAIL_DEBOUNCE_MS) {
      showToast('该视频 60 秒内已同步过，请稍后再试');
      return false;
    }
    await storageSet({ [key]: Date.now() });
    try {
      const payload = Object.assign({}, detail, {
        author_name: cfg.myNickname,
        author_id: cfg.myUid,
      });
      const res = await report([payload], 'https://www.douyin.com/user/' + cfg.mySecUid);
      const missing = (detail.missing_fields || []).length;
      console.log('[dy-analyzer] 详情同步成功:', detail.video_id, 'missing:', detail.missing_fields);
      showToast(
        '已同步该视频详情（' + detail.video_id + '）' +
        (missing ? '，字段缺失 ' + missing + ' 处' : ''),
      );
      return true;
    } catch (e) {
      showToast('同步失败：' + (e && e.message ? e.message : e));
      return false;
    }
  }

  function createDetailButton() {
    const old = document.getElementById('dy-analyzer-detail-btn');
    if (old) old.remove();
    const btn = document.createElement('div');
    btn.id = 'dy-analyzer-detail-btn';
    btn.textContent = '同步本页';
    btn.style.cssText =
      'position:fixed;right:16px;bottom:64px;z-index:2147483647;background:#67c23a;color:#fff;' +
      'border-radius:20px;padding:8px 14px;font-size:13px;cursor:pointer;' +
      'box-shadow:0 2px 8px rgba(0,0,0,.35);user-select:none;font-family:system-ui,sans-serif;';
    btn.addEventListener('click', async () => {
      btn.textContent = '同步中…';
      await maybeCollectDetail(true);
      btn.textContent = '同步本页';
    });
    document.body.appendChild(btn);
    return btn;
  }

  function removeDetailButton() {
    const b = document.getElementById('dy-analyzer-detail-btn');
    if (b) b.remove();
  }

  /* ---------- 启动（主页模式） ---------- */

  function startDetailMode() {
    if (detailStarted) return;
    detailStarted = true;
    createDetailButton();
    const attempt = (n) => {
      setTimeout(async () => {
        if (!isDetailView()) return;
        if (isDetailView()) {
          await maybeCollectDetail();
        } else if (n < DETAIL_RETRY_TIMES) {
          attempt(n + 1);
        } else {
          console.log('[dy-analyzer] feed-video 多次未出现，放弃:', location.href);
        }
      }, 1200);
    };
    attempt(0);
  }

  function init() {
    homeButtonAdded = false;
    if (isOwnProfile()) {
      const data = readRenderData();
      const info = data && data.app && data.app.user && data.app.user.info;
      if (info) {
        // 始终以当前自己主页的身份为准，覆盖可能变化的缓存
        storageSet({
          [KEY_UID]: info.uid,
          [KEY_SEC_UID]: info.secUid,
          [KEY_NICKNAME]: info.nickname,
        });
      }
      const addButtonWhenReady = () => {
        if (document.querySelector('[data-e2e="user-post-list"]')) {
          createCollectButton();
          return true;
        }
        return false;
      };
      if (!addButtonWhenReady()) {
        new MutationObserver((_, obs) => {
          if (addButtonWhenReady()) obs.disconnect();
        }).observe(document.body, { childList: true, subtree: true });
      }
    }
  }

  /** 详情模式常驻监听：检测 feed-video 出现/消失/切换，管理按钮与自动同步。 */
  function watchDetail() {
    let lastVid = '';
    const check = () => {
      const vidEl = document.querySelector('[data-e2e="feed-video"]');
      const vid = vidEl ? (vidEl.getAttribute('data-e2e-vid') || '') : '';
      if (vid && vid !== lastVid) {
        lastVid = vid;
        detailStarted = false;
        startDetailMode();
      } else if (!vid && lastVid) {
        lastVid = '';
        detailStarted = false;
        removeDetailButton();
      }
    };
    new MutationObserver(check).observe(document.body, { childList: true, subtree: true });
    check();
  }

  /** SPA 路由监听：抖音页面切换可能不刷新页面，轮询 pathname 变化重新初始化。 */
  function watchRoute() {
    const now = location.pathname;
    if (now !== lastPath) {
      lastPath = now;
      init();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      init();
      watchDetail();
    });
  } else {
    init();
    watchDetail();
  }
  setInterval(watchRoute, 800);
})();
