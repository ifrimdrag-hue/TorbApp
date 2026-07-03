/* Shared application error display.
 *
 * AppError.show(subtitle, message, title) presents a full, untruncated error
 * message in a Bootstrap modal with a copy button. Use this everywhere instead
 * of ad-hoc inline error text so error UX is consistent across the app.
 *
 * The modal markup is injected lazily into <body> on first use, so pages only
 * need to call AppError.show(...) — no per-page HTML required.
 *
 * Convention: any new error handler that surfaces a message to the user should
 * route it through AppError.show(). See docs/TECHNICAL.md (Frontend conventions).
 */
(function () {
  var MODAL_ID = 'appErrorModal';
  var _modal = null;

  function ensureModal() {
    if (document.getElementById(MODAL_ID)) return;
    var html =
      '<div class="modal fade" id="' + MODAL_ID + '" tabindex="-1" aria-hidden="true">' +
        '<div class="modal-dialog modal-lg modal-dialog-scrollable">' +
          '<div class="modal-content">' +
            '<div class="modal-header">' +
              '<h5 class="modal-title text-danger">' +
                '<i class="bi bi-exclamation-octagon-fill me-2"></i>' +
                '<span data-role="title">Eroare</span></h5>' +
              '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Închide"></button>' +
            '</div>' +
            '<div class="modal-body">' +
              '<div class="text-muted small mb-2" data-role="subtitle"></div>' +
              '<pre data-role="message" class="border rounded p-3 mb-0" ' +
                'style="white-space:pre-wrap;word-break:break-word;max-height:50vh;overflow:auto;font-size:.85rem"></pre>' +
            '</div>' +
            '<div class="modal-footer">' +
              '<button type="button" class="btn btn-sm btn-outline-secondary" data-role="copy">' +
                '<i class="bi bi-clipboard me-1"></i>Copiază mesajul</button>' +
              '<button type="button" class="btn btn-sm btn-secondary" data-bs-dismiss="modal">Închide</button>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>';
    var wrap = document.createElement('div');
    wrap.innerHTML = html;
    document.body.appendChild(wrap.firstChild);

    var el = document.getElementById(MODAL_ID);
    el.querySelector('[data-role="copy"]').addEventListener('click', function () {
      var msg = el.querySelector('[data-role="message"]').textContent;
      var btn = this;
      navigator.clipboard.writeText(msg).then(function () {
        var old = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check2 me-1"></i>Copiat';
        setTimeout(function () { btn.innerHTML = old; }, 1500);
      });
    });
  }

  window.AppError = {
    /**
     * Show a full error message in the shared modal.
     * @param {string} [subtitle] short context (file name, action, ...).
     * @param {string} message    full, untruncated error text.
     * @param {string} [title]    modal heading (default "Eroare").
     */
    show: function (subtitle, message, title) {
      ensureModal();
      var el = document.getElementById(MODAL_ID);
      el.querySelector('[data-role="title"]').textContent = title || 'Eroare';
      el.querySelector('[data-role="subtitle"]').textContent = subtitle || '';
      el.querySelector('[data-role="message"]').textContent = message || 'Eroare necunoscută';
      if (!_modal) _modal = new bootstrap.Modal(el);
      _modal.show();
    }
  };

  /* Convenience global alias. */
  window.showAppError = function (subtitle, message, title) {
    window.AppError.show(subtitle, message, title);
  };
})();
