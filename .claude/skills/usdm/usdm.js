/* USDM の要求表に、折りたたみ・絞り込み・検索を付ける。
 *
 * 手書きの 1 枚（docs/usdm/src/*.html）と要求一覧（docs/usdm/index.html）で
 * 共有する。どちらも「静的な表がまずあって、それを後から強化する」形なので、
 * このファイルが読めなくても表はそのまま読める（全部開いた状態になるだけ）。
 *
 * 表の意味は class が正。行の親子は次の規則で決める（HTML の入れ子ではない）:
 *   characteristic → interpretation / metrics / note
 *   req-group      → requirement 以下すべて
 *   requirement    → reason / note / spec-group / spec
 *   spec-group     → spec
 */
(function () {
  'use strict';

  var KINDS = {
    requirement: 1, reason: 1, note: 1, 'req-group': 1, 'spec-group': 1,
    spec: 1, characteristic: 1, interpretation: 1, metrics: 1
  };
  var FOLDABLE = { characteristic: 1, 'req-group': 1, requirement: 1, 'spec-group': 1 };
  var OPEN = '▾';
  var SHUT = '▸';

  var tables = [];
  var closed = {};
  var search = null;
  var filter = null;
  var counter = null;
  var empty = null;

  function kindOf(tr) {
    var list = (tr.className || '').split(/\s+/);
    for (var i = 0; i < list.length; i += 1) {
      if (KINDS[list[i]]) { return list[i]; }
    }
    return '';
  }

  function labelCell(tr) {
    var cells = tr.querySelectorAll('td.kind');
    for (var i = 0; i < cells.length; i += 1) {
      if ((cells[i].textContent || '').trim()) { return cells[i]; }
    }
    return null;
  }

  // 表 1 枚を、行の親子関係つきのモデルにする
  function indexTable(table) {
    var body = table.tBodies[0];
    var rows = body ? Array.prototype.slice.call(body.rows) : [];
    var model = [];
    var charAt = -1, groupAt = -1, reqAt = -1, specGroupAt = -1;

    rows.forEach(function (tr, i) {
      var kind = kindOf(tr);
      var owners = [];

      if (kind === 'characteristic') {
        charAt = i; groupAt = -1; reqAt = -1; specGroupAt = -1;
      } else if (kind === 'interpretation' || kind === 'metrics') {
        if (charAt >= 0) { owners.push(charAt); }
      } else if (kind === 'req-group') {
        groupAt = i; reqAt = -1; specGroupAt = -1;
      } else if (kind === 'requirement') {
        reqAt = i; specGroupAt = -1;
        if (groupAt >= 0) { owners.push(groupAt); }
      } else if (kind === 'spec-group') {
        specGroupAt = i;
        if (groupAt >= 0) { owners.push(groupAt); }
        if (reqAt >= 0) { owners.push(reqAt); }
      } else if (kind === 'spec') {
        if (groupAt >= 0) { owners.push(groupAt); }
        if (reqAt >= 0) { owners.push(reqAt); }
        if (specGroupAt >= 0) { owners.push(specGroupAt); }
      } else if (kind === 'reason') {
        if (groupAt >= 0) { owners.push(groupAt); }
        if (reqAt >= 0) { owners.push(reqAt); }
      } else if (kind === 'note') {
        if (reqAt >= 0) {
          if (groupAt >= 0) { owners.push(groupAt); }
          owners.push(reqAt);
        } else if (charAt >= 0) {
          owners.push(charAt);
        }
      }

      model.push({
        tr: tr, kind: kind, index: i, owners: owners,
        req: kind === 'requirement' ? i : (kind === 'req-group' ? -1 : reqAt),
        text: (tr.textContent || '').toLowerCase()
      });
    });

    // 要求の検索対象は「要求行 + その配下」をまとめた 1 つの塊
    var blockText = {};
    model.forEach(function (r) {
      if (r.req < 0) { return; }
      blockText[r.req] = (blockText[r.req] || '') + ' ' + r.text;
    });

    return {
      table: table, rows: model, blockText: blockText,
      scroll: table.closest ? (table.closest('.scroll') || table) : table,
      section: table.closest ? table.closest('.doc') : null
    };
  }

  function isChecked(tr) {
    var cell = tr.querySelector('td.check');
    return !!cell && (cell.textContent || '').indexOf('☑') !== -1;
  }

  function show(node, visible) {
    if (node) { node.style.display = visible ? '' : 'none'; }
  }

  function apply() {
    var q = search ? search.value.trim().toLowerCase() : '';
    var mode = filter ? filter.value : 'all';
    var shown = 0;

    tables.forEach(function (t, ti) {
      var base = {};
      var anyReq = false;

      // 1. 検索と絞り込みだけで決まる可視性（折りたたみは見ない）
      t.rows.forEach(function (r) {
        var visible = true;
        if (r.kind === 'characteristic' || r.kind === 'interpretation'
            || r.kind === 'metrics' || (r.kind === 'note' && r.req < 0)) {
          visible = true;
        } else if (r.kind === 'req-group' || r.kind === 'spec-group') {
          visible = false;   // 2 で members から決める
        } else if (r.req >= 0) {
          visible = !q || (t.blockText[r.req] || '').indexOf(q) !== -1;
          if (visible && r.kind === 'spec' && mode !== 'all') {
            visible = (mode === 'done') === isChecked(r.tr);
          }
        }
        base[r.index] = visible;
        if (visible && r.kind === 'requirement') { anyReq = true; }
      });

      // 2. グループ行は、配下に見えるものが 1 つでもあれば見せる
      t.rows.forEach(function (r) {
        if (r.kind !== 'req-group' && r.kind !== 'spec-group') { return; }
        base[r.index] = t.rows.some(function (m) {
          return m.owners.indexOf(r.index) !== -1 && base[m.index];
        });
      });

      // 3. 品質特性ブロックは、その表に見える要求があるときだけ出す
      if (!anyReq) {
        t.rows.forEach(function (r) { base[r.index] = false; });
      }

      // 4. 折りたたみを重ねる（検索中は畳んでいても開く）
      t.rows.forEach(function (r) {
        var visible = base[r.index];
        if (visible && !q) {
          visible = !r.owners.some(function (o) { return closed[ti + ':' + o]; });
        }
        show(r.tr, visible);
        if (visible && r.kind === 'requirement') { shown += 1; }
        if (FOLDABLE[r.kind]) {
          var caret = r.tr.querySelector('.caret');
          if (caret) { caret.textContent = (!q && closed[ti + ':' + r.index]) ? SHUT : OPEN; }
        }
      });

      // 5. 表そのものの開閉（文書レベル）
      var tableClosed = !q && closed['T:' + ti];
      show(t.scroll, anyReq && !tableClosed);
      if (t.section) { show(t.section, anyReq); }
      if (t.head) {
        var headCaret = t.head.querySelector('.caret');
        if (headCaret) { headCaret.textContent = tableClosed ? SHUT : OPEN; }
      }
    });

    if (counter) { counter.textContent = '該当する要求: ' + shown + ' 件'; }
    show(empty, shown === 0);

    // 節見出し（機能要求 / 品質要求）は、配下に見える文書があるときだけ出す
    Array.prototype.forEach.call(
      document.querySelectorAll('.section-title'),
      function (title) {
        var visible = false;
        var node = title.nextElementSibling;
        while (node && !node.classList.contains('section-title')) {
          if (node.classList.contains('doc') && node.style.display !== 'none') {
            visible = true;
            break;
          }
          node = node.nextElementSibling;
        }
        show(title, visible);
      }
    );
  }

  function toggle(key) {
    closed[key] = !closed[key];
    apply();
  }

  // caret は「ラベル欄」に差し込み、クリックは行（または見出し）全体で受ける
  function addCaret(host, clickTarget, key) {
    var caret = document.createElement('span');
    caret.className = 'caret';
    caret.textContent = OPEN;
    if (host.firstChild) { host.insertBefore(caret, host.firstChild); }
    else { host.appendChild(caret); }
    clickTarget.className += ' foldable';
    clickTarget.addEventListener('click', function () { toggle(key); });
  }

  function buildTools() {
    var tools = document.createElement('div');
    tools.className = 'tools';

    search = document.createElement('input');
    search.type = 'search';
    search.placeholder = '要求・理由・仕様・評価尺度を検索';
    search.autocomplete = 'off';
    tools.appendChild(search);

    var chips = document.createElement('div');
    chips.className = 'chips';

    filter = document.createElement('select');
    [['all', '仕様: すべて'], ['todo', '仕様: 未検証のみ'],
     ['done', '仕様: 検証済みのみ']].forEach(function (o) {
      var option = document.createElement('option');
      option.value = o[0];
      option.textContent = o[1];
      filter.appendChild(option);
    });
    chips.appendChild(filter);

    chips.appendChild(button('すべて開く', function () { closed = {}; apply(); }));
    chips.appendChild(button('すべて閉じる', closeAll));

    counter = document.createElement('p');
    counter.className = 'count';
    chips.appendChild(counter);

    tools.appendChild(chips);
    search.addEventListener('input', apply);
    filter.addEventListener('change', apply);
    return tools;
  }

  function button(label, onClick) {
    var node = document.createElement('button');
    node.type = 'button';
    node.textContent = label;
    node.addEventListener('click', onClick);
    return node;
  }

  // 「すべて閉じる」は要求の詳細だけを畳む。要求行・グループ行・表は残るので、
  // 下位要求まで含めた要求だけの一覧（アウトライン）として読める。
  function closeAll() {
    closed = {};
    tables.forEach(function (t, ti) {
      t.rows.forEach(function (r) {
        if (r.kind === 'requirement') { closed[ti + ':' + r.index] = true; }
      });
    });
    apply();
  }

  function init() {
    var found = document.querySelectorAll('table.usdm');
    if (!found.length) { return; }

    Array.prototype.forEach.call(found, function (table) {
      tables.push(indexTable(table));
    });

    tables.forEach(function (t, ti) {
      t.rows.forEach(function (r) {
        if (!FOLDABLE[r.kind]) { return; }
        var cell = labelCell(r.tr);
        if (cell) { addCaret(cell, r.tr, ti + ':' + r.index); }
      });
      var head = t.section ? t.section.querySelector('header') : document.querySelector('h1');
      if (head) {
        t.head = head;
        addCaret(head, head, 'T:' + ti);
      }
    });

    var wrap = document.querySelector('.wrap') || document.body;
    var anchor = null;
    Array.prototype.forEach.call(wrap.children, function (child) {
      if (!anchor && child.querySelector && child.querySelector('table.usdm')) {
        anchor = child;
      }
    });
    var tools = buildTools();
    if (anchor) { wrap.insertBefore(tools, anchor); } else { wrap.appendChild(tools); }

    empty = document.createElement('p');
    empty.className = 'empty';
    empty.textContent = '一致する要求がありません。';
    empty.style.display = 'none';
    wrap.appendChild(empty);

    apply();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
