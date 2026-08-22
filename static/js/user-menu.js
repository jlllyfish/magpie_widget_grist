/* Magpie — user-menu.js
   Menu deroulant "en-tete connectee" (inspire du composant DSFR beta).
   Partage entre index.html et admin_users.html. */

(function () {
  const btn = document.getElementById('user-menu-btn');
  const panel = document.getElementById('user-menu-panel');
  if (!btn || !panel) return;

  function openMenu() {
    panel.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    document.addEventListener('click', onOutsideClick);
    document.addEventListener('keydown', onKeydown);
  }

  function closeMenu() {
    panel.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', onOutsideClick);
    document.removeEventListener('keydown', onKeydown);
  }

  function onOutsideClick(e) {
    if (!panel.contains(e.target) && !btn.contains(e.target)) {
      closeMenu();
    }
  }

  function onKeydown(e) {
    if (e.key === 'Escape') {
      closeMenu();
      btn.focus();
    }
  }

  btn.addEventListener('click', () => {
    const isOpen = btn.getAttribute('aria-expanded') === 'true';
    if (isOpen) closeMenu();
    else openMenu();
  });
})();
