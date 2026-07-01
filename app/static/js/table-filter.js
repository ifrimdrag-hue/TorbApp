/* Torb Logistic — generic per-column table filter.
   Opt-in via data attributes, no per-table JS needed:
     <table data-filterable> ... <th data-filter="text|select|number"> ...
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

  function initTable(table) {
    var thead = table.querySelector('thead tr');
    if (!thead || !table.id) return;
    var headerCells = Array.prototype.slice.call(thead.children);

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
