/* Magpie — guide.js
   Page de guidage vers la console API Grist.

   Ce script ne fait AUCUN appel réseau et ne stocke rien (ni cookie, ni
   localStorage). Il se contente de :
   - valider le formulaire et générer le JSON à coller dans la console ;
   - construire le lien vers la console de l'instance Grist ;
   - copier du texte dans le presse-papiers. */

const DEFAULT_INSTANCE = 'https://grist.numerique.gouv.fr';

const $ = (id) => document.getElementById(id);

// ─── Utilitaires ──────────────────────────────────────────────────────────────

function todayISO() {
  // Date locale (et non UTC) pour ne pas refuser "aujourd'hui" en soirée
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function setFieldError(groupId, messagesId, inputId, message) {
  const group = $(groupId);
  const messages = $(messagesId);
  const input = $(inputId);
  group.classList.toggle('fr-input-group--error', Boolean(message));
  input.classList.toggle('fr-input--error', Boolean(message));
  messages.textContent = '';
  if (message) {
    const p = document.createElement('p');
    p.className = 'fr-message fr-message--error';
    p.textContent = message;
    messages.appendChild(p);
  }
}

function showToast(msg, type) {
  const toast = document.createElement('div');
  toast.className = `fr-toast fr-toast--${type}`;
  toast.textContent = msg;
  $('toast-container').appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('is-visible'));
  setTimeout(() => {
    toast.classList.remove('is-visible');
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    // Repli si l'API Clipboard est indisponible (contexte non sécurisé, iframe…)
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    ta.remove();
    if (!ok) throw e;
  }
}

function bindCopy(buttonId, codeId) {
  $(buttonId).addEventListener('click', async () => {
    try {
      await copyText($(codeId).textContent);
      showToast('Copié dans le presse-papiers', 'success');
    } catch (e) {
      showToast('Copie impossible : sélectionnez le texte manuellement', 'error');
    }
  });
}

// ─── Étape 1 : requête de création ───────────────────────────────────────────

function validateExpiry(value) {
  if (!value) return "La date d'expiration est obligatoire";
  if (value < todayISO()) return "La date d'expiration ne peut pas être antérieure à aujourd'hui";
  return null;
}

function updateCreateJson(showErrors) {
  const label = $('new-label').value.trim();
  const desc = $('new-desc').value.trim();
  const expiresAt = $('new-expires').value;

  const labelError = label ? null : 'Le nom est obligatoire';
  const expiryError = validateExpiry(expiresAt);

  if (showErrors) {
    setFieldError('group-label', 'new-label-messages', 'new-label', labelError);
    setFieldError('group-expires', 'new-expires-messages', 'new-expires', expiryError);
  }

  const valid = !labelError && !expiryError;
  $('btn-copy-create').disabled = !valid;

  if (!valid) {
    $('create-json').textContent = "Renseignez le nom et la date d'expiration.";
    return;
  }

  const body = { label };
  if (desc) body.description = desc;
  body.expiresAt = expiresAt;
  $('create-json').textContent = JSON.stringify(body, null, 2);
}

['new-label', 'new-desc'].forEach((id) =>
  $(id).addEventListener('input', () => updateCreateJson(false)));
$('new-label').addEventListener('blur', () => updateCreateJson(true));
$('new-expires').addEventListener('change', () => updateCreateJson(true));
bindCopy('btn-copy-create', 'create-json');

// ─── Étape 2 : lien vers la console ──────────────────────────────────────────

function normalizeInstance(raw) {
  try {
    const url = new URL((raw || '').trim());
    if (url.protocol !== 'https:') return null;
    return url.origin;
  } catch (e) {
    return null;
  }
}

function detectInstance() {
  // Ouvert comme widget dans Grist : le referrer est l'origine de l'instance
  // (politique par défaut strict-origin-when-cross-origin).
  if (window.self !== window.top && document.referrer) {
    const origin = normalizeInstance(document.referrer);
    if (origin) return origin;
  }
  return DEFAULT_INSTANCE;
}

function updateConsoleLink() {
  const origin = normalizeInstance($('instance-url').value);
  const link = $('btn-open-console');
  setFieldError('group-instance', 'instance-url-messages', 'instance-url',
    origin ? null : 'Saisissez une adresse en https://');
  if (origin) {
    link.href = `${origin}/apiconsole`;
    link.removeAttribute('aria-disabled');
  } else {
    link.removeAttribute('href');
    link.setAttribute('aria-disabled', 'true');
  }
}

$('instance-url').value = detectInstance();
$('instance-url').addEventListener('input', updateConsoleLink);

// ─── Prolonger un compte ─────────────────────────────────────────────────────

$('extend-expires').addEventListener('change', () => {
  const value = $('extend-expires').value;
  const error = validateExpiry(value);
  setFieldError('group-extend', 'extend-expires-messages', 'extend-expires', error);
  $('btn-copy-extend').disabled = Boolean(error);
  $('extend-json').textContent = error
    ? 'Choisissez une date.'
    : JSON.stringify({ expiresAt: value }, null, 2);
});
bindCopy('btn-copy-extend', 'extend-json');

// ─── Init ─────────────────────────────────────────────────────────────────────

$('new-expires').setAttribute('min', todayISO());
$('extend-expires').setAttribute('min', todayISO());
updateConsoleLink();
