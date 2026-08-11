/* 抖音个人视频数据分析器 —— 纯 DOM 解析函数
 * 浏览器 content script 与 Node(jsdom) 测试共用；
 * 解析以 data-e2e + 结构定位为主，哈希 class 只作候选兜底。
 */
(function (root) {
  'use strict';

  /** 解析互动数字：236 / 4.0万 / 1.2亿 / 4,000 → 整数；失败返回 null。 */
  function parseCount(text) {
    if (text === null || text === undefined) return null;
    const t = String(text).trim().replace(/,/g, '');
    const m = t.match(/^(\d+(?:\.\d+)?)(\u4e07|\u4ebf)?$/); // 万|亿
    if (!m) return null;
    const n = parseFloat(m[1]);
    const unit = m[2];
    let value = n;
    if (unit === '\u4ebf') value = n * 1e8;      // 亿
    else if (unit === '\u4e07') value = n * 1e4; // 万
    return Math.round(value);
  }

  /** 从链接提取 secUid：支持作者主页路径 /user/MS4wLj... 与主页卡片查询参数 secUid=MS4wLj... */
  function extractSecUidFromHref(href) {
    const s = String(href || '');
    const m = s.match(/\/user\/(MS4wLj[^/?#]*)/) || s.match(/[?&]secUid=(MS4wLj[^&#]*)/);
    return m ? m[1] : '';
  }

  /** 在容器内找第一个「纯数字/万/亿」文本元素并解析。 */
  function countIn(el) {
    if (!el) return null;
    const nodes = el.querySelectorAll('div, span');
    for (const node of nodes) {
      const t = (node.textContent || '').trim();
      if (t && /^[\d.,\u4e07\u4ebf]+$/.test(t)) {
        const v = parseCount(t);
        if (v !== null) return v;
      }
    }
    return null;
  }

  /**
   * 解析主页作品列表（div[data-e2e="user-post-list"] > ul > li）。
   * @param {Element} root 列表容器
   * @param {{author_name?: string, author_id?: string}} author 作者信息（来自 RENDER_DATA）
   * @returns {Array<object>} 每条含 video_id/video_title/play_count/cover_url/sec_uid/
   *                          author_name/author_id/missing_fields；图文与无 video_id 卡片跳过。
   */
  function parseProfileCards(root, author) {
    const results = [];
    if (!root) return results;
    for (const li of root.querySelectorAll('li')) {
      const videoLink = li.querySelector('a[href*="/video/"]');
      if (!videoLink) continue; // 图文 /note/ 或其它卡片 → 跳过
      const href = videoLink.getAttribute('href') || '';
      const m = href.match(/\/video\/(\d+)/);
      if (!m) continue; // 连 video_id 都取不到 → 跳过
      const video_id = m[1];
      const missing = [];

      const titleEl = li.querySelector('p.frUrWD64') || li.querySelector('p.EB3BkdQ8');
      const video_title = titleEl ? (titleEl.textContent || '').trim() : '';
      if (!video_title) missing.push('video_title');

      const playValue = countIn(li.querySelector('div.jXmtohcJ'));
      const play_count = playValue === null ? 0 : playValue;
      if (playValue === null) missing.push('play_count');

      const img = li.querySelector('img');
      const cover_url = img ? (img.getAttribute('src') || '') : '';
      if (!cover_url) missing.push('cover_url');

      results.push({
        video_id: video_id,
        video_title: video_title,
        play_count: play_count,
        cover_url: cover_url,
        sec_uid: extractSecUidFromHref(href),
        author_name: (author && author.author_name) || '',
        author_id: (author && author.author_id) || '',
        missing_fields: missing,
      });
    }
    return results;
  }

  /**
   * 解析视频详情页互动数据。
   * @param {Element} root document 或详情页容器
   * @returns {object|null} video_id/like_count/comment_count/share_count/video_desc/
   *                        video_url/cover_url/author_sec_uid/play_count(null)/publish_time(null)/
   *                        missing_fields；video_id 缺失返回 null。
   */
  function parseVideoDetail(root) {
    let video_id = '';
    const vidEl = root.querySelector('[data-e2e="feed-video"]');
    if (vidEl && vidEl.getAttribute('data-e2e-vid')) {
      video_id = vidEl.getAttribute('data-e2e-vid').trim();
    }
    if (!video_id) {
      const url = root.URL || (root.defaultView && root.defaultView.location.href) || '';
      const m = String(url).match(/\/video\/(\d+)/);
      if (m) video_id = m[1];
    }
    if (!video_id) {
      // 主页浮层场景：URL 为 /user/self?...&modal_id=<视频ID>
      const url = root.URL || (root.defaultView && root.defaultView.location.href) || '';
      const m = String(url).match(/[?&]modal_id=(\d+)/);
      if (m) video_id = m[1];
    }
    if (!video_id) return null;
    const missing = [];

    const likeValue = countIn(root.querySelector('[data-e2e="video-player-digg"]'));
    const like_count = likeValue === null ? 0 : likeValue;
    if (likeValue === null) missing.push('like_count');

    const commentValue = countIn(root.querySelector('[data-e2e="feed-comment-icon"]'));
    const comment_count = commentValue === null ? 0 : commentValue;
    if (commentValue === null) missing.push('comment_count');

    const shareValue = countIn(root.querySelector('[data-e2e="video-player-share"]'));
    const share_count = shareValue === null ? 0 : shareValue;
    if (shareValue === null) missing.push('share_count');

    const descEl = root.querySelector('[data-e2e="video-desc"]');
    const video_desc = descEl ? (descEl.textContent || '').trim() : '';
    if (!video_desc) missing.push('video_desc');
    const titleEl = descEl ? descEl.querySelector('span') : null;
    const video_title = titleEl ? (titleEl.textContent || '').trim() : '';

    const authorLink = root.querySelector('a[href*="/user/MS4wLj"]');
    const author_sec_uid = authorLink
      ? extractSecUidFromHref(authorLink.getAttribute('href'))
      : '';

    let cover_url = '';
    const posterEl = root.querySelector('video[poster]');
    if (posterEl) {
      cover_url = posterEl.getAttribute('poster') || '';
    } else {
      const imgEl = root.querySelector('[data-e2e="feed-video"] img');
      if (imgEl) cover_url = imgEl.getAttribute('src') || '';
    }
    if (!cover_url) missing.push('cover_url');

    return {
      video_id: video_id,
      video_title: video_title,
      video_desc: video_desc,
      like_count: like_count,
      comment_count: comment_count,
      share_count: share_count,
      play_count: null,
      publish_time: null,
      video_url: 'https://www.douyin.com/video/' + video_id,
      cover_url: cover_url,
      author_sec_uid: author_sec_uid,
      missing_fields: missing,
    };
  }

  const api = { parseCount, extractSecUidFromHref, parseProfileCards, parseVideoDetail };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root && !root.DouyinParse) root.DouyinParse = api;
})(typeof window !== 'undefined' ? window : globalThis);
