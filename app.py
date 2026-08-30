import os
import re
import logging

import requests
from flask import Flask, render_template, request, jsonify, session
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from datetime import datetime, timezone

from models import db, ServiceAccountDocLink

load_dotenv()

app = Flask(__name__)

# ─── Fait confiance aux headers X-Forwarded-* envoyes par le proxy Railway ────
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1)

# ─── Secret Flask : obligatoire, pas de valeur par defaut en dur ──────────────
FLASK_SECRET = os.environ.get("FLASK_SECRET")
if not FLASK_SECRET:
    raise RuntimeError(
        "FLASK_SECRET manquant. Generez-en un avec : "
        "python -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = FLASK_SECRET

# ─── Base de donnees ────────────────────────────────────────────────────────────
# DATABASE_PATH pointe vers le volume persistant Railway (ex: /data/app.db)
# En local, retombe sur un fichier a la racine du projet.
# Utilisee uniquement pour ServiceAccountDocLink (mapping login <-> doc).
DATABASE_PATH = os.environ.get("DATABASE_PATH", "app.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATABASE_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# ─── Cookies de session durcis ─────────────────────────────────────────────────
# Meme sans compte utilisateur, la session sert a stocker la config Grist
# (URL + cle API) le temps de l'usage du widget.
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
# SameSite=None + Secure : requis pour que le cookie de session fonctionne
# lorsque Magpie est charge en iframe cross-site dans un document Grist.
# Sans ca, la plupart des navigateurs modernes bloqueraient le cookie
# (protection anti-tracking sur les iframes tierces).
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True  # obligatoire avec SameSite=None

DEFAULT_GRIST_URL = os.environ.get("GRIST_URL", "")

log = logging.getLogger("werkzeug")
log.setLevel(logging.INFO)

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour"],
    storage_uri="memory://",
)


# ─── Validation d'entrees (SSRF) ────────────────────────────────────────────────

URL_PATTERN = re.compile(r"^https://[a-zA-Z0-9.\-]+(\.[a-zA-Z]{2,})+(/.*)?$")


def is_valid_grist_url(url):
    if not url or not URL_PATTERN.match(url):
        return False
    lowered = url.lower()
    forbidden = ["localhost", "127.0.0.1", "0.0.0.0", "169.254.", "10.", "192.168.", "172.16."]
    return not any(f in lowered for f in forbidden)


def get_config():
    return {
        "url": session.get("grist_url", DEFAULT_GRIST_URL).rstrip("/"),
        "key": session.get("api_key", ""),
    }


def api_headers(key):
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def redact(key):
    if not key:
        return "(vide)"
    return key[:4] + "****"


def verify_owner_on_doc(cfg, doc_id):
    """
    Verifie que la cle API configuree appartient a un utilisateur ayant le
    role Owner sur ce document precis.

    C'est le garde-fou anti-abus du widget : sans ce controle, quiconque
    saisit une cle API valide (meme celle d'un simple lecteur d'un AUTRE
    document, ou une cle recuperee/interceptee) pourrait s'accorder ou
    accorder a un tiers un role Proprietaire sur le document actuellement
    ouvert dans le widget -- independamment de ses droits reels sur celui-ci.

    Retourne (True, None) si autorise, (False, message_erreur) sinon.
    """
    try:
        # 1. Identifie l'utilisateur proprietaire de la cle API.
        # /api/profile/user ne renvoie PAS d'email (seulement id/name/picture),
        # on identifie donc l'utilisateur par son id, pas par email.
        r_profile = requests.get(
            f"{cfg['url']}/api/profile/user",
            headers=api_headers(cfg["key"]),
            timeout=10,
        )
        r_profile.raise_for_status()
        profile = r_profile.json()
        user_id = profile.get("id")
        if user_id is None:
            return False, "Impossible d'identifier l'utilisateur associé à cette clé API"

        # 2. Verifie le role de cet utilisateur sur le document courant,
        # en comparant par id (fiable) plutot que par email (absent de
        # la reponse profile/user).
        r_access = requests.get(
            f"{cfg['url']}/api/docs/{doc_id}/access",
            headers=api_headers(cfg["key"]),
            timeout=10,
        )
        r_access.raise_for_status()
        access_data = r_access.json()

        user_role = next(
            (u.get("access") for u in access_data.get("users", []) if u.get("id") == user_id),
            None,
        )

        if user_role != "owners":
            return False, (
                f"Action non autorisée : vous devez être Propriétaire de ce document "
                f"pour y ajouter un compte de service (rôle actuel : {user_role or 'aucun accès'})."
            )

        return True, None

    except requests.exceptions.RequestException as e:
        app.logger.error("Erreur verification autorisation Owner sur doc %s : %s", doc_id, e)
        return False, "Impossible de vérifier vos droits sur ce document"


# ─── Routes applicatives ────────────────────────────────────────────────────────
# Aucune authentification Magpie : la cle API Grist saisie par l'utilisateur
# EST l'autorisation. Elle n'est jamais stockee en base, uniquement en
# session serveur, jamais renvoyee au client.

@app.route("/")
def index():
    cfg = get_config()
    return render_template(
        "index.html",
        grist_url=cfg["url"],
        has_config=bool(cfg["url"] and cfg["key"]),
    )


@app.route("/api/config", methods=["POST"])
@limiter.limit("10 per minute")
def set_config():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    key = data.get("key", "").strip()

    if url:
        if not is_valid_grist_url(url):
            return jsonify({"error": "URL invalide ou non autorisee"}), 400
        session["grist_url"] = url

    if key:
        session["api_key"] = key
        app.logger.info("Cle API mise a jour en session : %s", redact(key))

    return jsonify({"ok": True})


@app.route("/api/service-accounts", methods=["GET"])
def list_accounts():
    cfg = get_config()
    if not cfg["key"]:
        return jsonify({"error": "Clé API non configurée"}), 401
    try:
        r = requests.get(
            f"{cfg['url']}/api/service-accounts",
            headers=api_headers(cfg["key"]),
            timeout=10,
        )
        r.raise_for_status()
        return jsonify(r.json())
    except requests.exceptions.RequestException as e:
        app.logger.error("Erreur liste comptes : %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/grist/docs/<doc_id>/access", methods=["PATCH"])
@limiter.limit("30 per hour")
def grant_doc_access(doc_id):
    """Donne acces a un document Grist pour un login (typiquement un compte de service)."""
    cfg = get_config()
    if not cfg["key"]:
        return jsonify({"error": "Clé API non configurée"}), 401

    body = request.get_json(silent=True) or {}
    login = (body.get("login") or "").strip()
    role = (body.get("role") or "editors").strip()

    if not login:
        return jsonify({"error": "Login manquant"}), 400
    if role not in ("editors", "owners"):
        return jsonify({"error": "Rôle invalide"}), 400

    # ── Verification d'autorisation ──────────────────────────────────────
    # On s'assure que la personne qui a saisi cette cle a bien le role
    # Owner sur CE document precis avant de lui permettre d'y ajouter un
    # compte de service. Sans ce controle, n'importe quelle cle API valide
    # (meme celle d'un simple lecteur d'un AUTRE document) pourrait etre
    # utilisee pour s'accorder des droits Proprietaire sur le document
    # actuellement ouvert dans le widget.
    is_authorized, auth_error = verify_owner_on_doc(cfg, doc_id)
    if not is_authorized:
        return jsonify({"error": auth_error}), 403

    payload = {"delta": {"users": {login: role}}}

    try:
        r = requests.patch(
            f"{cfg['url']}/api/docs/{doc_id}/access",
            headers=api_headers(cfg["key"]),
            json=payload,
            timeout=10,
        )
        r.raise_for_status()
        app.logger.info("Acces document accorde : login=%s doc=%s role=%s", login, doc_id, role)

        # Enregistre le lien (login <-> doc) s'il n'existe pas deja,
        # pour pouvoir l'afficher plus tard sans avoir a scanner tous
        # les documents accessibles.
        existing = ServiceAccountDocLink.query.filter_by(
            service_account_login=login, doc_id=doc_id
        ).first()
        if not existing:
            link = ServiceAccountDocLink(service_account_login=login, doc_id=doc_id)
            db.session.add(link)
            db.session.commit()

        return jsonify({"ok": True})
    except requests.exceptions.RequestException as e:
        app.logger.error("Erreur attribution acces document : %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/service-accounts/<login>/doc-links", methods=["GET"])
def get_service_account_doc_links(login):
    """
    Renvoie les documents auxquels ce compte de service a ete rattache via
    Magpie, avec leur nom et le role actuel du compte -- toujours recuperes
    en direct depuis Grist pour ne jamais etre desynchronises.
    """
    cfg = get_config()
    if not cfg["key"]:
        return jsonify({"error": "Clé API non configurée"}), 401

    links = ServiceAccountDocLink.query.filter_by(service_account_login=login).all()
    results = []

    for link in links:
        try:
            # Nom du document
            r_doc = requests.get(
                f"{cfg['url']}/api/docs/{link.doc_id}",
                headers=api_headers(cfg["key"]),
                timeout=10,
            )
            r_doc.raise_for_status()
            doc_data = r_doc.json()

            # Role actuel du compte sur ce document
            r_access = requests.get(
                f"{cfg['url']}/api/docs/{link.doc_id}/access",
                headers=api_headers(cfg["key"]),
                timeout=10,
            )
            r_access.raise_for_status()
            access_data = r_access.json()
            role = next(
                (u.get("access") for u in access_data.get("users", []) if u.get("email") == login),
                None,
            )

            results.append({
                "docId": link.doc_id,
                "docName": doc_data.get("name", link.doc_id),
                "role": role,
            })
        except requests.exceptions.RequestException as e:
            app.logger.warning("Impossible de recuperer le doc %s pour %s : %s", link.doc_id, login, e)
            # Le lien existe toujours mais le document est peut-etre
            # inaccessible/supprime -- on l'affiche quand meme avec un role nul
            results.append({
                "docId": link.doc_id,
                "docName": link.doc_id,
                "role": None,
            })

    return jsonify(results)


@app.route("/api/service-accounts", methods=["POST"])
@limiter.limit("20 per hour")
def create_account():
    cfg = get_config()
    if not cfg["key"]:
        return jsonify({"error": "Clé API non configurée"}), 401

    body = request.get_json(silent=True) or {}
    label = (body.get("label") or "").strip()
    if not label or len(label) > 200:
        return jsonify({"error": "Nom de compte invalide"}), 400

    payload = {"label": label}
    if body.get("description"):
        payload["description"] = str(body["description"])[:500]

    expires_at = body.get("expiresAt")
    if not expires_at:
        return jsonify({"error": "La date d'expiration est obligatoire"}), 400
    try:
        expires_date = datetime.strptime(expires_at, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return jsonify({"error": "Format de date invalide"}), 400
    if expires_date < datetime.now(timezone.utc).date():
        return jsonify({"error": "La date d'expiration ne peut pas être antérieure à aujourd'hui"}), 400
    payload["expiresAt"] = expires_at

    try:
        r = requests.post(
            f"{cfg['url']}/api/service-accounts",
            headers=api_headers(cfg["key"]),
            json=payload,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        app.logger.info("Compte cree : login=%s", data.get("login", "?"))
        return jsonify(data)
    except requests.exceptions.RequestException as e:
        app.logger.error("Erreur creation compte : %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/service-accounts/<int:account_id>", methods=["DELETE"])
@limiter.limit("30 per hour")
def delete_account(account_id):
    cfg = get_config()
    if not cfg["key"]:
        return jsonify({"error": "Clé API non configurée"}), 401
    try:
        r = requests.delete(
            f"{cfg['url']}/api/service-accounts/{account_id}",
            headers=api_headers(cfg["key"]),
            timeout=10,
        )
        r.raise_for_status()
        app.logger.info("Compte supprime : #%d", account_id)
        return jsonify({"ok": True})
    except requests.exceptions.RequestException as e:
        app.logger.error("Erreur suppression #%d : %s", account_id, e)
        return jsonify({"error": str(e)}), 500


# ─── Headers de securite ─────────────────────────────────────────────────────

@app.after_request
def set_security_headers(response):
    # PAS de X-Frame-Options: DENY ici -- Magpie doit pouvoir etre charge
    # en iframe par Grist pour fonctionner comme widget custom. A la place,
    # on utilise une Content-Security-Policy frame-ancestors qui restreint
    # precisement quels domaines ont le droit de nous embarquer.
    allowed_frame_ancestors = os.environ.get(
        "ALLOWED_FRAME_ANCESTORS",
        "https://grist.numerique.gouv.fr"
    )
    response.headers["Content-Security-Policy"] = f"frame-ancestors {allowed_frame_ancestors}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


# ─── Initialisation de la base au premier lancement ───────────────────────────

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
