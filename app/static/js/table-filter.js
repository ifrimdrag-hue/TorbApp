/* Torb Logistic — generic per-column table filter + sort.
   Opt-in via data attributes, no per-table JS needed:
     <table data-filterable> ... <th data-filter="text|select|number"> ...
     <th data-sort> or <th data-sort="number">  (clickable header, asc/desc/none)
     <td data-v="raw value">  (numeric/select columns; optional for text)
     <button data-filter-toggle="tableId">  (shows/hides the filter row)
     <span data-filter-count="tableId">     (updated with visible row count) */
(function () {
  function cellValue(cell) {
    return cell.hasAttribute('data-v') ? cell.getAttribute('data-v') : cell.textContent.trim();
  }

  function buildFilterRow(table, headerCells) {
    var row = document.createElement('tr');
    row.className = 'table-filter-row d-none';

    var colValues = headerCells.map(function (th, idx) {
      if (th.getAttribute('data-filter') !== 'select') return null;
      var values = {};
      table.querySelectorAll('tbody tr').forEach(function (tr) {
        var cell = tr.children[idx];
        if (!cell) return;
        var v = cellValue(cell);
        if (v) values[v] = true;
      });
      return Object.keys(values).sort();
    });

    headerCells.forEach(function (th, idx) {
      var td = document.createElement('td');
      var type = th.getAttribute('data-filter');

      if (type === 'text') {
        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control form-control-sm';
        input.dataset.col = idx;
        input.dataset.type = 'text';
        td.appendChild(input);
      } else if (type === 'select') {
        var select = document.createElement('select');
        select.className = 'form-select form-select-sm';
        select.dataset.col = idx;
        select.dataset.type = 'select';
        select.appendChild(new Option('Toate', ''));
        colValues[idx].forEach(function (v) { select.appendChild(new Option(v, v)); });
        td.appendChild(select);
      } else if (type === 'number') {
        var wrap = document.createElement('div');
        wrap.className = 'd-flex gap-1';
        var min = document.createElement('input');
        min.type = 'number';
        min.placeholder = 'min';
        min.className = 'form-control form-control-sm';
        min.dataset.col = idx;
        min.dataset.type = 'min';
        var max = document.createElement('input');
        max.type = 'number';
        max.placeholder = 'max';
        max.className = 'form-control form-control-sm';
        max.dataset.col = idx;
        max.dataset.type = 'max';
        wrap.appendChild(min);
        wrap.appendChild(max);
        td.appendChild(wrap);
      }

      row.appendChild(td);
    });

    return row;
  }

  function applyFilters(table, filterRow) {
    var controls = filterRow.querySelectorAll('input, select');
    var rules = [];
    controls.forEach(function (c) {
      if (!c.value) return;
      rules.push({ col: parseInt(c.dataset.col, 10), type: c.dataset.type, value: c.value });
    });

    var bodyRows = Array.prototype.filter.call(
      table.querySelectorAll('tbody tr'),
      function (tr) { return !tr.classList.contains('table-filter-empty-row'); }
    );

    var visible = 0;
    bodyRows.forEach(function (tr) {
      var match = rules.every(function (rule) {
        var cell = tr.children[rule.col];
        if (!cell) return false;
        var raw = cellValue(cell);

        if (rule.type === 'text') {
          return raw.toLowerCase().indexOf(rule.value.toLowerCase()) !== -1;
        }
        if (rule.type === 'select') {
          return raw === rule.value;
        }
        var num = parseFloat(raw);
        if (isNaN(num)) return false;
        if (rule.type === 'min') return num >= parseFloat(rule.value);
        if (rule.type === 'max') return num <= parseFloat(rule.value);
        return true;
      });

      tr.classList.toggle('d-none', !match);
      if (match) visible++;
    });

    var countEl = document.querySelector('[data-filter-count="' + table.id + '"]');
    if (countEl) countEl.textContent = visible;

    var emptyRow = table.querySelector('.table-filter-empty-row');
    if (emptyRow) emptyRow.classList.toggle('d-none', visible > 0 || bodyRows.length === 0);
  }

  function bodyRowsOf(table) {
    return Array.prototype.filter.call(
      table.querySelectorAll('tbody tr'),
      function (tr) { return !tr.classList.contains('table-filter-empty-row'); }
    );
  }

  function compareRows(a, b, col, type) {
    var av = cellValue(a.children[col]);
    var bv = cellValue(b.children[col]);
    if (type === 'number') {
      var an = parseFloat(av); an = isNaN(an) ? -Infinity : an;
      var bn = parseFloat(bv); bn = isNaN(bn) ? -Infinity : bn;
      return an - bn;
    }
    return av.localeCompare(bv, 'ro', { numeric: true, sensitivity: 'base' });
  }

  function applySort(table, col, dir, type) {
    var tbody = table.querySelector('tbody');
    if (!tbody) return;
    var rows = bodyRowsOf(table);
    if (dir === 0) {
      rows.sort(function (a, b) {
        return (+a.dataset.origIndex) - (+b.dataset.origIndex);
      });
    } else {
      rows.sort(function (a, b) { return dir * compareRows(a, b, col, type); });
    }
    rows.forEach(function (tr) { tbody.appendChild(tr); });
    var emptyRow = tbody.querySelector('.table-filter-empty-row');
    if (emptyRow) tbody.appendChild(emptyRow);
  }

  function updateIndicator(th) {
    var ind = th.querySelector('.sort-indicator');
    if (!ind) return;
    var dir = th.dataset.sortDir ? parseInt(th.dataset.sortDir, 10) : 0;
    ind.textContent = dir === 1 ? '▲' : dir === -1 ? '▼' : '⇅';
    ind.classList.toggle('active', dir !== 0);
  }

  function initSort(table, headerCells) {
    bodyRowsOf(table).forEach(function (tr, i) { tr.dataset.origIndex = i; });

    headerCells.forEach(function (th, idx) {
      if (!th.hasAttribute('data-sort')) return;
      var type = th.getAttribute('data-sort') === 'number' ? 'number' : 'text';
      th.classList.add('sortable');
      var ind = document.createElement('span');
      ind.className = 'sort-indicator';
      th.appendChild(ind);
      updateIndicator(th);

      th.addEventListener('click', function () {
        var cur = th.dataset.sortDir ? parseInt(th.dataset.sortDir, 10) : 0;
        var next = cur === 0 ? 1 : cur === 1 ? -1 : 0;
        headerCells.forEach(function (other) {
          if (other !== th && other.hasAttribute('data-sort')) {
            delete other.dataset.sortDir;
            updateIndicator(other);
          }
        });
        if (next === 0) { delete th.dataset.sortDir; } else { th.dataset.sortDir = next; }
        updateIndicator(th);
        applySort(table, idx, next, type);
      });
    });
  }

  function initTable(table) {
    var thead = table.querySelector('thead tr');
    if (!thead || !table.id) return;
    var headerCells = Array.prototype.slice.call(thead.children);

    initSort(table, headerCells);

    var filterRow = buildFilterRow(table, headerCells);
    thead.parentNode.appendChild(filterRow);

    filterRow.addEventListener('input', function () { applyFilters(table, filterRow); });
    filterRow.addEventListener('change', function () { applyFilters(table, filterRow); });

    var toggleBtn = document.querySelector('[data-filter-toggle="' + table.id + '"]');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function () {
        var showing = !filterRow.classList.contains('d-none');
        if (showing) {
          filterRow.querySelectorAll('input, select').forEach(function (c) { c.value = ''; });
          applyFilters(table, filterRow);
          filterRow.classList.add('d-none');
        } else {
          filterRow.classList.remove('d-none');
        }
        toggleBtn.classList.toggle('active', !showing);
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('table[data-filterable]').forEach(initTable);
  });
})();
