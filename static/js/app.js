/* Grist Service Accounts — app.js */

// ─── CSRF ─────────────────────────────────────────────────────────────────────

const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';

function csrfHeaders(extra = {}) {
  return { 'X-CSRFToken': CSRF_TOKEN, ...extra };
}

// ─── Config accordion ─────────────────────────────────────────────────────────

function setConfigFieldError(groupId, messagesId, inputId, message) {
  const group    = document.getElementById(groupId);
  const messages = document.getElementById(messagesId);
  const input    = document.getElementById(inputId);
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

document.getElementById('cfg-url').addEventListener('input', () => {
  setConfigFieldError('group-cfg-url', 'cfg-url-messages', 'cfg-url', null);
  document.getElementById('config-success').style.display = 'none';
});
document.getElementById('cfg-key').addEventListener('input', () => {
  setConfigFieldError('group-cfg-key', 'cfg-key-messages', 'cfg-key', null);
  document.getElementById('config-success').style.display = 'none';
});

document.getElementById('btn-save-config').addEventListener('click', async () => {
  const url = document.getElementById('cfg-url').value.trim();
  const key = document.getElementById('cfg-key').value.trim();
  let hasError = false;

  if (!url) {
    setConfigFieldError('group-cfg-url', 'cfg-url-messages', 'cfg-url', "L'URL de l'instance est obligatoire");
    hasError = true;
  }
  if (!key) {
    setConfigFieldError('group-cfg-key', 'cfg-key-messages', 'cfg-key', 'La clé API est obligatoire');
    hasError = true;
  }
  if (hasError) return;

  const btn = document.getElementById('btn-save-config');
  btn.disabled = true;
  btn.setAttribute('aria-busy', 'true');

  // Enregistre en session
  await fetch('/api/config', {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ url, key }),
  });

  // Vérifie la clé en tentant un appel réel
  try {
    const r    = await fetch('/api/service-accounts');
    const data = await r.json();

    if (r.status === 401 || data.error) {
      setConfigFieldError('group-cfg-key', 'cfg-key-messages', 'cfg-key', 'Clé API invalide ou accès refusé');
      return;
    }

    // Succes - affiche l'alerte, charge les comptes et referme l'accordion apres un court delai
    document.getElementById('config-success').style.display = 'block';
    loadAccounts();

    setTimeout(() => {
      const accordionBtn = document.querySelector('#config-accordion .fr-accordion__btn');
      if (accordionBtn && accordionBtn.getAttribute('aria-expanded') === 'true') {
        accordionBtn.click();
      }
    }, 1200);

  } catch (e) {
    setConfigFieldError('group-cfg-url', 'cfg-url-messages', 'cfg-url', 'Impossible de joindre l\'instance Grist');
  } finally {
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
  }
});

// ─── Create account ───────────────────────────────────────────────────────────

document.getElementById('btn-create').addEventListener('click', createAccount);

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

function clearFieldErrors() {
  setFieldError('group-label', 'new-label-messages', 'new-label', null);
  setFieldError('group-expires', 'new-expires-messages', 'new-expires', null);
}

// Empeche de choisir une date passee dans le selecteur natif du navigateur
(function setMinExpiryDate() {
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('new-expires').setAttribute('min', today);
})();

document.getElementById('new-label').addEventListener('input', () => {
  setFieldError('group-label', 'new-label-messages', 'new-label', null);
});

document.getElementById('new-expires').addEventListener('change', () => {
  setFieldError('group-expires', 'new-expires-messages', 'new-expires', null);
});

async function createAccount() {
  clearFieldErrors();

  const label = document.getElementById('new-label').value.trim();
  const exp   = document.getElementById('new-expires').value;
  let hasError = false;

  if (!label) {
    setFieldError('group-label', 'new-label-messages', 'new-label', 'Le nom est obligatoire');
    hasError = true;
  }
  if (!exp) {
    setFieldError('group-expires', 'new-expires-messages', 'new-expires', 'La date d\'expiration est obligatoire');
    hasError = true;
  } else {
    const today = new Date().toISOString().split('T')[0];
    if (exp < today) {
      setFieldError('group-expires', 'new-expires-messages', 'new-expires', 'La date d\'expiration ne peut pas être antérieure à aujourd\'hui');
      hasError = true;
    }
  }
  if (hasError) return;

  const body = { label, expiresAt: exp };
  const desc = document.getElementById('new-desc').value.trim();
  if (desc) body.description = desc;

  setLoading('btn-create', true);
  document.getElementById('key-reveal').classList.remove('is-visible');

  try {
    const r    = await fetch('/api/service-accounts', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (data.error) throw new Error(data.error);

    document.getElementById('key-value').textContent = data.key;
    document.getElementById('key-login').textContent = data.login;
    document.getElementById('key-reveal').classList.add('is-visible');
    resetDocAccessPanel('create');
    _createSectionLogin = data.login;
    if (!_createSectionInitialized) {
      initDocAccessSection('create', () => _createSectionLogin);
      _createSectionInitialized = true;
    }

    clearFieldErrors();
    document.getElementById('new-label').value   = '';
    document.getElementById('new-desc').value    = '';
    document.getElementById('new-expires').value = '';

    loadAccounts();
  } catch (e) {
    showToast('Erreur : ' + e.message, 'error');
  } finally {
    setLoading('btn-create', false);
  }
}

document.getElementById('btn-copy-key').addEventListener('click', () => {
  const key = document.getElementById('key-value').textContent;
  navigator.clipboard.writeText(key);
});

document.getElementById('btn-copy-login').addEventListener('click', () => {
  const login = document.getElementById('key-login').textContent;
  navigator.clipboard.writeText(login);
});

document.getElementById('btn-close-key-reveal').addEventListener('click', () => {
  document.getElementById('key-reveal').classList.remove('is-visible');
});

// ─── Ajout comme editeur/proprietaire d'un document (generique) ───────────────
// Reutilisable a la fois pour le compte fraichement cree et pour les comptes
// existants dans la liste -- chaque instance est identifiee par un prefixe
// d'id unique (ex: "create" ou "acc-42").

const _orgsCachePerPrefix = {};
let _createSectionLogin = null;
let _createSectionInitialized = false;

function resetDocAccessPanel(prefix) {
  const chk = document.getElementById(`chk-add-to-doc-${prefix}`);
  if (chk) chk.checked = false;
  document.getElementById(`doc-access-panel-${prefix}`).style.display = 'none';
  document.getElementById(`doc-access-success-${prefix}`).style.display = 'none';
  document.getElementById(`doc-access-error-${prefix}`).style.display = 'none';
  document.getElementById(`btn-grant-access-${prefix}`).disabled = true;
  document.getElementById(`sel-doc-${prefix}`).innerHTML = '<option value="">Choisir une organisation d\'abord</option>';
  document.getElementById(`sel-doc-${prefix}`).disabled = true;
  delete _orgsCachePerPrefix[prefix];
}

function initDocAccessSection(prefix, loginOrGetter) {
  const getLogin = typeof loginOrGetter === 'function' ? loginOrGetter : () => loginOrGetter;
  const chk = document.getElementById(`chk-add-to-doc-${prefix}`);
  const panel = document.getElementById(`doc-access-panel-${prefix}`);
  const selOrg = document.getElementById(`sel-org-${prefix}`);
  const selDoc = document.getElementById(`sel-doc-${prefix}`);
  const selRole = document.getElementById(`sel-role-${prefix}`);
  const btnGrant = document.getElementById(`btn-grant-access-${prefix}`);
  const successEl = document.getElementById(`doc-access-success-${prefix}`);
  const errorEl = document.getElementById(`doc-access-error-${prefix}`);

  chk.addEventListener('change', async (e) => {
    if (e.target.checked) {
      panel.style.display = 'block';
      if (!_orgsCachePerPrefix[prefix]) await loadOrgsIntoSelect(selOrg, prefix);
    } else {
      panel.style.display = 'none';
    }
  });

  selOrg.addEventListener('change', async (e) => {
    const orgId = e.target.value;
    btnGrant.disabled = true;

    if (!orgId) {
      selDoc.innerHTML = '<option value="">Choisir une organisation d\'abord</option>';
      selDoc.disabled = true;
      return;
    }

    selDoc.innerHTML = '<option value="">Chargement…</option>';
    selDoc.disabled = true;

    try {
      const r = await fetch(`/api/grist/orgs/${orgId}/workspaces`);
      const workspaces = await r.json();
      if (workspaces.error) throw new Error(workspaces.error);

      selDoc.innerHTML = '<option value="">Sélectionner…</option>';
      workspaces.forEach(ws => {
        (ws.docs || []).forEach(doc => {
          const opt = document.createElement('option');
          opt.value = doc.id;
          opt.textContent = `${ws.name} / ${doc.name}`;
          selDoc.appendChild(opt);
        });
      });
      selDoc.disabled = false;
    } catch (e) {
      selDoc.innerHTML = '<option value="">Erreur de chargement</option>';
      showToast('Erreur : ' + e.message, 'error');
    }
  });

  selDoc.addEventListener('change', (e) => {
    btnGrant.disabled = !e.target.value;
  });

  btnGrant.addEventListener('click', async () => {
    const docId = selDoc.value;
    const role = selRole.value;
    const login = getLogin();

    successEl.style.display = 'none';
    errorEl.style.display = 'none';

    if (!docId || !login) return;

    btnGrant.disabled = true;

    try {
      const r = await fetch(`/api/grist/docs/${docId}/access`, {
        method: 'PATCH',
        headers: csrfHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ login, role }),
      });
      const data = await r.json();
      if (data.error) throw new Error(data.error);

      successEl.style.display = 'block';
      // Rafraichit la liste des documents lies affichee sur la carte,
      // uniquement pertinent pour les cartes de comptes existants
      if (prefix.startsWith('acc-')) {
        loadDocLinksForCard(prefix, login);
      }
    } catch (e) {
      errorEl.querySelector('p').textContent = 'Erreur : ' + e.message;
      errorEl.style.display = 'block';
    } finally {
      btnGrant.disabled = false;
    }
  });
}

async function loadOrgsIntoSelect(selOrg, prefix) {
  selOrg.innerHTML = '<option value="">Chargement…</option>';
  try {
    const r = await fetch('/api/grist/orgs');
    const orgs = await r.json();
    if (orgs.error) throw new Error(orgs.error);

    selOrg.innerHTML = '<option value="">Sélectionner…</option>';
    orgs.forEach(org => {
      const opt = document.createElement('option');
      opt.value = org.id;
      // Distingue les espaces "Personal" homonymes en ajoutant le nom
      // du proprietaire ou le domaine, quand disponibles
      let label = org.name;
      if (org.owner && org.owner.name && org.owner.name !== org.name) {
        label += ` (${org.owner.name})`;
      } else if (org.domain) {
        label += ` (${org.domain})`;
      }
      opt.textContent = label;
      selOrg.appendChild(opt);
    });
    _orgsCachePerPrefix[prefix] = orgs;
  } catch (e) {
    selOrg.innerHTML = '<option value="">Erreur de chargement</option>';
    showToast('Erreur : ' + e.message, 'error');
  }
}

function docAccessSectionHTML(prefix) {
  return `
    <div class="fr-mt-3w" style="border-top:1px solid var(--border-default-grey);padding-top:1rem;">
      <div class="fr-checkbox-group">
        <input type="checkbox" id="chk-add-to-doc-${prefix}" />
        <label class="fr-label" for="chk-add-to-doc-${prefix}">
          Ajouter ce compte à un document Grist
        </label>
      </div>

      <div id="doc-access-panel-${prefix}" style="display:none;" class="fr-mt-2w">
        <div class="grist-grid-3">
          <div class="fr-select-group">
            <label class="fr-label" for="sel-org-${prefix}">Organisation</label>
            <select class="fr-select" id="sel-org-${prefix}">
              <option value="">Chargement…</option>
            </select>
          </div>
          <div class="fr-select-group">
            <label class="fr-label" for="sel-doc-${prefix}">Document</label>
            <select class="fr-select" id="sel-doc-${prefix}" disabled>
              <option value="">Choisir une organisation d'abord</option>
            </select>
          </div>
          <div class="fr-select-group">
            <label class="fr-label" for="sel-role-${prefix}">Rôle</label>
            <select class="fr-select" id="sel-role-${prefix}">
              <option value="editors" selected>Éditeur</option>
              <option value="owners">Propriétaire</option>
            </select>
          </div>
        </div>

        <button id="btn-grant-access-${prefix}" class="fr-btn fr-btn--secondary fr-mt-2w" disabled>
          Ajouter au document
        </button>

        <div id="doc-access-success-${prefix}" class="fr-alert fr-alert--success fr-alert--sm fr-mt-2w" style="display:none;">
          <p>Compte ajouté au document avec succès.</p>
        </div>
        <div id="doc-access-error-${prefix}" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w" style="display:none;">
          <p></p>
        </div>
      </div>
    </div>
  `;
}

// ─── List accounts ────────────────────────────────────────────────────────────

document.getElementById('btn-refresh').addEventListener('click', () => {
  document.getElementById('key-reveal').classList.remove('is-visible');
  loadAccounts();
});

async function loadAccounts() {
  setLoading('btn-refresh', true);
  document.getElementById('accounts-error').style.display  = 'none';
  document.getElementById('accounts-empty').style.display  = 'none';
  document.getElementById('accounts-list').innerHTML = '';

  try {
    const r    = await fetch('/api/service-accounts');
    const data = await r.json();
    if (data.error) throw new Error(data.error);

    if (!data.length) {
      document.getElementById('accounts-empty').style.display = 'block';
      return;
    }
    renderAccounts(data);
  } catch (e) {
    const el      = document.getElementById('accounts-error');
    el.textContent = 'Erreur : ' + e.message;
    el.style.display = 'block';
  } finally {
    setLoading('btn-refresh', false);
  }
}

function renderAccounts(accounts) {
  const list = document.getElementById('accounts-list');
  list.innerHTML = '';

  accounts.forEach(acc => {
    const expired  = acc.expiresAt && new Date(acc.expiresAt) < new Date();
    const validKey = acc.hasValidKey;
    const prefix = `acc-${acc.id}`;

    const card = document.createElement('div');
    card.className = 'account-card' + (expired ? ' is-expired' : '');

    card.innerHTML = `
      <div class="account-card__header">
        <div class="account-card__info">
          <div class="account-card__name-row">
            <span class="account-card__name">${esc(acc.label)}</span>
            <span class="account-card__id">#${acc.id}</span>
            <span class="fr-badge fr-badge--sm ${validKey ? 'fr-badge--success' : 'fr-badge--error'}">
              ${validKey ? 'clé active' : 'clé révoquée'}
            </span>
            ${expired ? '<span class="fr-badge fr-badge--sm fr-badge--warning">expirée</span>' : ''}
          </div>
          ${acc.description
            ? `<div class="account-card__desc">${esc(acc.description)}</div>`
            : ''}
          <div class="account-card__login">${esc(acc.login)}</div>
          ${acc.expiresAt
            ? `<div class="account-card__expires">Expire : ${new Date(acc.expiresAt).toLocaleDateString('fr-FR')}</div>`
            : ''}
          <div id="doc-links-${prefix}" class="account-card__doc-links"></div>
        </div>
        <div class="account-card__actions">
          <button class="fr-btn fr-btn--secondary fr-btn--sm fr-btn--icon-left fr-icon-delete-line"
                  style="color: var(--text-default-error);"
                  onclick="confirmDelete(${acc.id}, '${esc(acc.label)}')">Supprimer</button>
        </div>
      </div>
      ${docAccessSectionHTML(prefix)}
    `;
    list.appendChild(card);

    initDocAccessSection(prefix, acc.login);
    loadDocLinksForCard(prefix, acc.login);
  });
}

async function loadDocLinksForCard(prefix, login) {
  const zone = document.getElementById(`doc-links-${prefix}`);
  if (!zone) return;

  zone.innerHTML = `<div class="account-card__doc-links-loading">Chargement des documents liés…</div>`;

  try {
    const r = await fetch(`/api/service-accounts/${encodeURIComponent(login)}/doc-links`);
    const links = await r.json();
    if (links.error) throw new Error(links.error);

    if (!links.length) {
      zone.innerHTML = '';
      return;
    }

    const roleLabel = (role) => {
      if (role === 'owners') return 'propriétaire';
      if (role === 'editors') return 'éditeur';
      return 'accès inconnu';
    };
    const roleBadgeClass = (role) => role === 'owners' ? 'fr-badge--info' : 'fr-badge--new';

    zone.innerHTML = links.map(link => `
      <div class="account-card__doc-link">
        <span class="fr-icon-file-text-line" aria-hidden="true"></span>
        <span class="account-card__doc-link-name">${esc(link.docName)}</span>
        <span class="fr-badge fr-badge--sm ${link.role ? roleBadgeClass(link.role) : 'fr-badge--error'}">
          ${link.role ? roleLabel(link.role) : 'inaccessible'}
        </span>
      </div>
    `).join('');
  } catch (e) {
    zone.innerHTML = `<div class="account-card__doc-links-error">Impossible de charger les documents liés.</div>`;
  }
}

// ─── Actions ──────────────────────────────────────────────────────────────────

function confirmDelete(id, label) {
  openModal(
    'Supprimer le compte',
    `Supprimer définitivement le compte « ${label} » (#${id}) ? Cette action est irréversible.`,
    async () => {
      try {
        const r = await fetch(`/api/service-accounts/${id}`, { method: 'DELETE', headers: csrfHeaders() });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        loadAccounts();
      } catch (e) { showToast('Erreur : ' + e.message, 'error'); }
    },
    'Supprimer'
  );
}

// ─── Modal DSFR ───────────────────────────────────────────────────────────────

let _modalCallback = null;

function openModal(title, text, cb, confirmLabel) {
  _modalCallback = cb;
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-text').textContent  = text;
  document.getElementById('modal-confirm-btn').textContent = confirmLabel || 'Confirmer';
  // API DSFR
  const modal = document.getElementById('confirm-modal');
  dsfr(modal).modal.disclose();
}

document.getElementById('modal-confirm-btn').addEventListener('click', () => {
  if (_modalCallback) _modalCallback();
  _modalCallback = null;
  const modal = document.getElementById('confirm-modal');
  dsfr(modal).modal.conceal();
});

// ─── Utilities ────────────────────────────────────────────────────────────────

function showToast(msg, type) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `fr-toast fr-toast--${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('is-visible'));
  setTimeout(() => {
    toast.classList.remove('is-visible');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function setLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  btn.disabled = loading;
  if (loading) btn.setAttribute('aria-busy', 'true');
  else         btn.removeAttribute('aria-busy');
}

function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ─── Init ─────────────────────────────────────────────────────────────────────
loadAccounts();

// Ouvrir l'accordion si pas de config, apres initialisation du DSFR
const hasConfig = document.body.dataset.hasConfig === 'true';
if (!hasConfig) {
  // Script charge en defer : le DOM est deja pret, on attend juste
  // que le DSFR ait fini d'attacher ses listeners
  setTimeout(() => {
    const btn = document.querySelector('#config-accordion .fr-accordion__btn');
    if (btn && btn.getAttribute('aria-expanded') === 'false') {
      btn.click();
    }
  }, 100);
}
