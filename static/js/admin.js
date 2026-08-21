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

    document.getElementById('user-success').style.display = 'block';
    setTimeout(() => window.location.reload(), 1000);
  } catch (e) {
    setFieldError('group-new-email', 'new-email-messages', 'new-email', 'Erreur réseau');
  } finally {
    btn.disabled = false;
  }
});

let _modalCallback = null;

function confirmDeleteUser(id, email) {
  document.getElementById('modal-title').textContent = 'Supprimer l\'utilisateur';
  document.getElementById('modal-text').textContent =
    `Supprimer définitivement le compte « ${email} » ? Cette action est irréversible.`;
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
