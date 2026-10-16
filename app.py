import os
import re
import logging
from urllib.parse import urlsplit

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
# La session ne sert plus qu'au jeton CSRF : la cle API n'y est jamais stockee.
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
# SameSite=None + Secure : requis pour que le cookie de session fonctionne
# lorsque Magpie est charge en iframe cross-site dans un document Grist.
# Sans ca, la plupart des navigateurs modernes bloqueraient le cookie
# (protection anti-tracking sur les iframes tierces).
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True  # obligatoire avec SameSite=None

DEFAULT_GRIST_URL = os.environ.get("GRIST_URL", "https://grist.numerique.gouv.fr").strip().rstrip("/")

# Liste blanche des instances Grist joignables (noms d'hote exacts, separes
# par des virgules). Toute autre URL est refusee : Magpie n'a pas
# d'authentification propre, une URL libre en ferait un relais SSRF vers le
# reseau interne de l'hebergeur.
ALLOWED_GRIST_HOSTS = {
    h.strip().lower()
    for h in os.environ.get(
        "ALLOWED_GRIST_HOSTS",
        urlsplit(DEFAULT_GRIST_URL).hostname or "grist.numerique.gouv.fr",
    ).split(",")
    if h.strip()
}

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

def normalize_grist_url(url):
    """
    Renvoie "https://<hote>" si l'URL vise une instance de la liste blanche,
    sinon None. Pas de port, d'identifiants ni de chemin : seul l'hote compte.
    """
    try:
        parts = urlsplit((url or "").strip())
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or parts.port or parts.username or parts.password:
            return None
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            return None
    except ValueError:
        return None
    if host not in ALLOWED_GRIST_HOSTS:
        return None
    return f"https://{host}"


def get_config():
    """
    Lit l'URL et la cle API Grist dans les en-tetes de la requete en cours.

    La cle n'est JAMAIS stockee cote serveur (ni session, ni base, ni cookie) :
    elle vit uniquement dans la memoire de la page du widget et accompagne
    chaque appel. Un cookie de session est lie au navigateur, pas a
    l'utilisateur Grist : le stocker la exposait les comptes de service du
    proprietaire a toute personne ouvrant le widget dans le meme navigateur.
    """
    raw_url = request.headers.get("X-Grist-Url") or DEFAULT_GRIST_URL
    key = (request.headers.get("X-Grist-Api-Key") or "").strip()
    # L'URL vient du client a chaque requete : on la revalide a chaque fois (SSRF)
    url = normalize_grist_url(raw_url) or ""
    return {"url": url, "key": key}


def config_error():
    """Renvoie une reponse 401 si la config est incomplete, sinon None."""
    cfg = get_config()
    if not cfg["key"]:
        return cfg, (jsonify({"error": "Clé API non configurée"}), 401)
    if not cfg["url"]:
        return cfg, (jsonify({"error": "Instance Grist non autorisée sur ce serveur Magpie"}), 400)
    return cfg, None


def grist_call(method, cfg, path, **kwargs):
    """
    Appel a l'API Grist de l'instance configuree. Les redirections ne sont
    jamais suivies (elles pourraient mener hors de la liste blanche).
    """
    r = requests.request(
        method,
        f"{cfg['url']}{path}",
        headers=api_headers(cfg["key"]),
        timeout=10,
        allow_redirects=False,
        **kwargs,
    )
    if 300 <= r.status_code < 400:
        raise requests.exceptions.HTTPError(f"Redirection refusee ({r.status_code})", response=r)
    r.raise_for_status()
    return r


def grist_error(exc, context):
    """
    Journalise le detail de l'erreur et renvoie au client un message generique :
    le detail (URL, hote, message reseau) servirait d'oracle a un attaquant.
    """
    app.logger.error("%s : %s", context, exc)
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return jsonify({"error": "Accès refusé par Grist : clé invalide ou droits insuffisants"}), 403
    if status == 404:
        return jsonify({"error": "Ressource introuvable sur Grist"}), 404
    return jsonify({"error": "Erreur de communication avec Grist"}), 502


def list_caller_service_accounts(cfg):
    """Comptes de service appartenant au detenteur de la cle API."""
    return grist_call("GET", cfg, "/api/service-accounts").json()


def api_headers(key):
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


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
        r_profile = grist_call("GET", cfg, "/api/profile/user")
        profile = r_profile.json()
        user_id = profile.get("id")
        if user_id is None:
            return False, "Impossible d'identifier l'utilisateur associé à cette clé API"

        # 2. Verifie le role de cet utilisateur sur le document courant,
        # en comparant par id (fiable) plutot que par email (absent de
        # la reponse profile/user).
        r_access = grist_call("GET", cfg, f"/api/docs/{doc_id}/access")
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
# EST l'autorisation. Elle n'est stockee nulle part cote serveur : le client
# l'envoie dans l'en-tete X-Grist-Api-Key a chaque requete.

@app.route("/")
def index():
    # Purge les cles/URL stockees en session par les anciennes versions
    session.pop("api_key", None)
    session.pop("grist_url", None)
    return render_template("index.html", grist_url=DEFAULT_GRIST_URL.rstrip("/"))


@app.route("/api/service-accounts", methods=["GET"])
def list_accounts():
    cfg, err = config_error()
    if err:
        return err
    try:
        return jsonify(list_caller_service_accounts(cfg))
    except requests.exceptions.RequestException as e:
        return grist_error(e, "Erreur liste comptes")


@app.route("/api/grist/docs/<doc_id>/access", methods=["PATCH"])
@limiter.limit("30 per hour")
def grant_doc_access(doc_id):
    """Donne acces a un document Grist pour un login (typiquement un compte de service)."""
    cfg, err = config_error()
    if err:
        return err

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
        grist_call("PATCH", cfg, f"/api/docs/{doc_id}/access", json=payload)
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
        return grist_error(e, "Erreur attribution acces document")


@app.route("/api/service-accounts/<login>/doc-links", methods=["GET"])
def get_service_account_doc_links(login):
    """
    Renvoie les documents auxquels ce compte de service a ete rattache via
    Magpie, avec leur nom et le role actuel du compte -- toujours recuperes
    en direct depuis Grist pour ne jamais etre desynchronises.
    """
    cfg, err = config_error()
    if err:
        return err

    # Le login doit appartenir au detenteur de la cle : sans ce controle,
    # n'importe qui (meme avec une cle bidon) obtenait les identifiants des
    # documents rattaches a un compte de service tiers.
    try:
        own_logins = {a.get("login") for a in list_caller_service_accounts(cfg)}
    except requests.exceptions.RequestException as e:
        return grist_error(e, "Erreur verification proprietaire compte de service")
    if login not in own_logins:
        return jsonify({"error": "Ce compte de service ne vous appartient pas"}), 403

    links = ServiceAccountDocLink.query.filter_by(service_account_login=login).all()
    results = []

    for link in links:
        try:
            # Nom du document
            r_doc = grist_call("GET", cfg, f"/api/docs/{link.doc_id}")
            doc_data = r_doc.json()

            # Role actuel du compte sur ce document
            r_access = grist_call("GET", cfg, f"/api/docs/{link.doc_id}/access")
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
    cfg, err = config_error()
    if err:
        return err

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
        data = grist_call("POST", cfg, "/api/service-accounts", json=payload).json()
        app.logger.info("Compte cree : login=%s", data.get("login", "?"))
        return jsonify(data)
    except requests.exceptions.RequestException as e:
        return grist_error(e, "Erreur creation compte")


@app.route("/api/service-accounts/<int:account_id>", methods=["DELETE"])
@limiter.limit("30 per hour")
def delete_account(account_id):
    cfg, err = config_error()
    if err:
        return err
    try:
        grist_call("DELETE", cfg, f"/api/service-accounts/{account_id}")
        app.logger.info("Compte supprime : #%d", account_id)
        return jsonify({"ok": True})
    except requests.exceptions.RequestException as e:
        return grist_error(e, f"Erreur suppression #{account_id}")


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
    # Aucune reponse API (liste de comptes, cles generees) ne doit etre
    # mise en cache par le navigateur ou un proxy intermediaire
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ─── Initialisation de la base au premier lancement ───────────────────────────

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
