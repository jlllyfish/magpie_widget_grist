/* Magpie — admin.js */

const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';

function csrfHeaders(extra = {}) {
  return { 'X-CSRFToken': CSRF_TOKEN, ...extra };
}

function setFieldError(groupId, messagesId, inputId, message) {
  const group = document.getElementById(groupId);
  const messages = document.getElementById(messagesId);
  const input = document.getElementById(inputId);
  if (message) {
    group.classList.add('fr-input-group--error');
    input.classList.add('fr-input--error');
    messages.innerHTML = `<p class="fr-message fr-message--error">${message}</p>`;
  } else {
    group.classList.remove('fr-input-group--error');
    input.classList.remove('fr-input--error');
    messages.innerHTML = '';
  }
}

document.getElementById('new-email').addEventListener('input', () => {
  setFieldError('group-new-email', 'new-email-messages', 'new-email', null);
});
document.getElementById('new-password').addEventListener('input', () => {
  setFieldError('group-new-password', 'new-password-messages', 'new-password', null);
});

// ─── Generation de mot de passe ────────────────────────────────────────────────

document.getElementById('btn-generate-password').addEventListener('click', async () => {
  const btn = document.getElementById('btn-generate-password');
  btn.disabled = true;
  try {
    const r = await fetch('/api/admin/generate-password');
    const data = await r.json();
    document.getElementById('new-password').value = data.password;
    setFieldError('group-new-password', 'new-password-messages', 'new-password', null);
  } catch (e) {
    setFieldError('group-new-password', 'new-password-messages', 'new-password', 'Erreur lors de la génération');
  } finally {
    btn.disabled = false;
  }
});

// ─── Creation d'utilisateur ─────────────────────────────────────────────────────

document.getElementById('btn-create-user').addEventListener('click', async () => {
  const email = document.getElementById('new-email').value.trim();
  const password = document.getElementById('new-password').value;
  const isAdmin = document.getElementById('new-is-admin').value === 'true';

  let hasError = false;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    setFieldError('group-new-email', 'new-email-messages', 'new-email', 'Adresse email invalide');
    hasError = true;
  }
  if (password.length < 12) {
    setFieldError('group-new-password', 'new-password-messages', 'new-password', 'Le mot de passe doit faire au moins 12 caractères');
    hasError = true;
  }
  if (hasError) return;

  const btn = document.getElementById('btn-create-user');
  btn.disabled = true;

  try {
    const r = await fetch('/api/admin/users', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ email, password, is_admin: isAdmin }),
    });
    const data = await r.json();

    if (data.error) {
      setFieldError('group-new-email', 'new-email-messages', 'new-email', data.error);
      return;
    }

    document.getElementById('user-password-value').textContent = password;
    document.getElementById('user-success').style.display = 'block';

    document.getElementById('new-email').value = '';
    document.getElementById('new-password').value = '';
    document.getElementById('new-is-admin').value = 'false';

    // Ajoute la nouvelle carte utilisateur directement dans la liste,
    // sans recharger la page ni perdre l'affichage du mot de passe
    addUserCardToList(data);

  } catch (e) {
    setFieldError('group-new-email', 'new-email-messages', 'new-email', 'Erreur réseau');
  } finally {
    btn.disabled = false;
  }
});

function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function addUserCardToList(user) {
  const list = document.querySelector('.account-list');
  if (!list) return;

  const card = document.createElement('div');
  card.className = 'account-card';
  card.innerHTML = `
    <div class="account-card__header">
      <div class="account-card__info">
        <div class="account-card__name-row">
          <span class="account-card__name">${esc(user.email)}</span>
          ${user.is_admin ? '<span class="fr-badge fr-badge--sm fr-badge--info">administrateur</span>' : ''}
        </div>
        <div class="account-card__login">Créé à l'instant · Jamais connecté</div>
      </div>
      <div class="account-card__actions">
        <button class="fr-btn fr-btn--secondary fr-btn--sm fr-btn--icon-left fr-icon-refresh-line"
                data-action="reset-password" data-user-id="${user.id}" data-user-email="${esc(user.email)}">Réinitialiser le mot de passe</button>
        <button class="fr-btn fr-btn--secondary fr-btn--sm fr-btn--icon-left fr-icon-delete-line"
                style="color: var(--text-default-error);"
                data-action="delete-user" data-user-id="${user.id}" data-user-email="${esc(user.email)}">Supprimer</button>
      </div>
    </div>
    <div id="reset-reveal-${user.id}" class="key-reveal" style="display:none;">
      <div class="fr-alert fr-alert--info fr-alert--sm fr-mb-2w">
        <p>Nouveau mot de passe généré — communiquez-le à l'utilisateur, il ne sera plus affiché.</p>
      </div>
      <div class="key-reveal__row">
        <code id="reset-value-${user.id}" class="key-reveal__value"></code>
        <button class="fr-btn fr-btn--secondary fr-btn--sm fr-btn--icon-left fr-icon-clipboard-line"
                onclick="copyResetPassword(${user.id})">Copier</button>
      </div>
    </div>
  `;
  list.insertBefore(card, list.firstChild);
}

document.getElementById('btn-copy-user-password').addEventListener('click', () => {
  const val = document.getElementById('user-password-value').textContent;
  navigator.clipboard.writeText(val);
});

// ─── Reinitialisation de mot de passe ──────────────────────────────────────────

let _modalCallback = null;

function confirmResetPassword(id, email) {
  document.getElementById('modal-title').textContent = 'Réinitialiser le mot de passe';
  document.getElementById('modal-text').textContent =
    `Générer un nouveau mot de passe pour « ${email} » ? L'ancien mot de passe ne fonctionnera plus.`;
  document.getElementById('modal-confirm-btn').textContent = 'Réinitialiser';
  _modalCallback = async () => {
    try {
      const r = await fetch(`/api/admin/users/${id}/reset-password`, {
        method: 'POST',
        headers: csrfHeaders(),
      });
      const d = await r.json();
      if (d.error) throw new Error(d.error);

      document.getElementById(`reset-value-${id}`).textContent = d.password;
      document.getElementById(`reset-reveal-${id}`).style.display = 'block';
    } catch (e) {
      alert('Erreur : ' + e.message);
    }
  };
  const modal = document.getElementById('confirm-modal');
  dsfr(modal).modal.disclose();
}

function copyResetPassword(id) {
  const val = document.getElementById(`reset-value-${id}`).textContent;
  navigator.clipboard.writeText(val);
}

// ─── Suppression d'utilisateur ─────────────────────────────────────────────────

function confirmDeleteUser(id, email) {
  document.getElementById('modal-title').textContent = 'Supprimer l\'utilisateur';
  document.getElementById('modal-text').textContent =
    `Supprimer définitivement le compte « ${email} » ? Cette action est irréversible.`;
  document.getElementById('modal-confirm-btn').textContent = 'Supprimer';
  _modalCallback = async () => {
    try {
      const r = await fetch(`/api/admin/users/${id}`, { method: 'DELETE', headers: csrfHeaders() });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      window.location.reload();
    } catch (e) {
      alert('Erreur : ' + e.message);
    }
  };
  const modal = document.getElementById('confirm-modal');
  dsfr(modal).modal.disclose();
}

document.getElementById('modal-confirm-btn').addEventListener('click', () => {
  if (_modalCallback) _modalCallback();
  _modalCallback = null;
  const modal = document.getElementById('confirm-modal');
  dsfr(modal).modal.conceal();
});

// ─── Delegation d'evenements pour les actions par utilisateur ─────────────────
// Evite d'injecter du JS inline via onclick="..." genere par Jinja, ce qui
// posait un vrai probleme d'echappement quand l'email contenait des
// guillemets (ex: filtre |tojson genere des " qui cassent l'attribut HTML
// lui-meme delimite par des "). Les data-attributes sont echappes par
// l'autoescape HTML de Jinja, donc surs dans tous les cas.
document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;

  const action = btn.dataset.action;
  const id = parseInt(btn.dataset.userId, 10);
  const email = btn.dataset.userEmail;

  if (action === 'reset-password') {
    confirmResetPassword(id, email);
  } else if (action === 'delete-user') {
    confirmDeleteUser(id, email);
  }
});
