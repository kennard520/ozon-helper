/* Ozon 卖家知识库交互脚本：移动端侧边栏 + 全站搜索（Ctrl+K / 顶部搜索框） */
(function () {
  var INDEX = null;

  // 移动端菜单
  var toggle = document.getElementById('menu-toggle');
  var sidebar = document.getElementById('sidebar');
  if (toggle && sidebar) {
    toggle.addEventListener('click', function () {
      sidebar.classList.toggle('open');
    });
    document.addEventListener('click', function (e) {
      if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== toggle) {
        sidebar.classList.remove('open');
      }
    });
  }

  // 搜索数据：优先用内联 search-index.js（file:// 下 script 可加载），兜底 fetch index.json
  function loadIndex() {
    if (window.__SEARCH_INDEX && window.__SEARCH_INDEX.length) {
      return Promise.resolve({ articles: window.__SEARCH_INDEX });
    }
    var rel = getRootRel();
    return fetch(rel + 'index.json')
      .then(function (r) { return r.json(); })
      .catch(function () { return null; });
  }

  function getRootRel() {
    if (window.__KB_ROOT !== undefined) return window.__KB_ROOT;
    var depth = (location.pathname.split('/').filter(Boolean).length) - 1;
    return depth > 0 ? '../'.repeat(depth) : './';
  }

  function buildSearchBox() {
    var rootRel = getRootRel();
    var box = document.createElement('input');
    box.type = 'search';
    box.placeholder = '搜索全部文章… (Ctrl+K)';
    box.className = 'search-box';
    var results = document.createElement('div');
    results.className = 'search-results';
    var container = document.querySelector('.sidebar-body');
    if (!container) return;
    container.insertBefore(box, container.firstChild);
    container.insertBefore(results, box.nextSibling);

    var timer = null;
    box.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(function () { doSearch(box.value, results); }, 180);
    });
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        box.focus();
      }
    });
  }

  function doSearch(q, resultsEl) {
    q = (q || '').trim().toLowerCase();
    if (!q || !INDEX) {
      resultsEl.innerHTML = '';
      return;
    }
    var hits = [];
    for (var i = 0; i < INDEX.articles.length; i++) {
      var a = INDEX.articles[i];
      var title = (a.title != null ? a.title : a.t || '').toString().toLowerCase();
      var path = (a.path != null ? a.path : a.p || '').toString().toLowerCase();
      if (title.indexOf(q) > -1 || path.indexOf(q) > -1) {
        hits.push(a);
        if (hits.length >= 30) break;
      }
    }
    if (!hits.length) {
      resultsEl.innerHTML = '<div style="padding:8px 10px;color:#646a73;font-size:13px">无匹配结果</div>';
      return;
    }
    var html = '';
    hits.forEach(function (a) {
      var rel = getRootRel();
      var ap = a.path != null ? a.path : a.p;
      var target = rel + ap.split('/').filter(Boolean).join('/') + '.html';
      var label = a.title != null ? a.title : a.t;
      html += '<a href="' + target + '"><div>' + escapeHtml(label || ap) +
        '</div><div class="sr-path">' + escapeHtml(ap) + '</div></a>';
    });
    resultsEl.innerHTML = html;
  }

  function escapeHtml(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  loadIndex().then(function (idx) {
    INDEX = idx;
    buildSearchBox();
  });
})();
