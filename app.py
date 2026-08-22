import logging
import os
import re
from datetime import datetime, timezone
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf import CSRFProtect
from models import User, db
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

app = Flask(__name__)

# ─── Fait confiance aux headers X-Forwarded-* envoyes par le proxy Railway ────
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1)

# ─── Secret Flask : obligatoire, pas de valeur par defaut en dur ──────────────
FLASK_SECRET = os.environ.get("FLASK_SECRET")
if not FLASK_SECRET:
    raise RuntimeError(
        "FLASK_SECRET manquant. Generez-en un avec : "
        'python -c "import secrets; print(secrets.token_hex(32))"'
    )
app.secret_key = FLASK_SECRET

# ─── Base de donnees ────────────────────────────────────────────────────────────
# DATABASE_PATH pointe vers le volume persistant Railway (ex: /data/app.db)
# En local, retombe sur un fichier a la racine du projet.
DATABASE_PATH = os.environ.get("DATABASE_PATH", "app.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATABASE_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# ─── Cookies de session durcis ─────────────────────────────────────────────────
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"

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

# ─── Flask-Login ──────────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = None  # on gere nous-memes l'affichage


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({"error": "Acces reserve aux administrateurs"}), 403
        return f(*args, **kwargs)

    return wrapper


def api_login_required(f):
    """Variante API : renvoie 401 JSON plutot qu'une redirection HTML."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentification requise"}), 401
        return f(*args, **kwargs)

    return wrapper


# ─── Authentification ────────────────────────────────────────────────────────


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        # Comparaison constante meme si l'utilisateur n'existe pas,
        # pour ne pas laisser deviner par le temps de reponse si l'email existe
        if user and user.check_password(password):
            login_user(user, remember=False)
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            return redirect(url_for("index"))
        error = "Email ou mot de passe incorrect."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ─── Administration des comptes (reservee aux admins) ─────────────────────────


@app.route("/admin/users", methods=["GET"])
@login_required
def admin_users():
    if not current_user.is_admin:
        return redirect(url_for("index"))
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin_users.html", users=users)


@app.route("/api/admin/users", methods=["POST"])
@admin_required
@limiter.limit("20 per hour")
def create_user():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    is_admin = bool(data.get("is_admin", False))

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "Adresse email invalide"}), 400
    if len(password) < 12:
        return jsonify(
            {"error": "Le mot de passe doit faire au moins 12 caracteres"}
        ), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Un compte existe deja avec cet email"}), 409

    user = User(email=email, is_admin=is_admin)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    app.logger.info("Utilisateur cree par %s : %s", current_user.email, email)
    return jsonify({"ok": True, "id": user.id, "email": user.email})


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        return jsonify(
            {"error": "Vous ne pouvez pas supprimer votre propre compte"}
        ), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    db.session.delete(user)
    db.session.commit()
    app.logger.info("Utilisateur supprime par %s : %s", current_user.email, user.email)
    return jsonify({"ok": True})


# ─── Validation d'entrees (SSRF) ────────────────────────────────────────────────

URL_PATTERN = re.compile(r"^https://[a-zA-Z0-9.\-]+(\.[a-zA-Z]{2,})+(/.*)?$")


def is_valid_grist_url(url):
    if not url or not URL_PATTERN.match(url):
        return False
    lowered = url.lower()
    forbidden = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "169.254.",
        "10.",
        "192.168.",
        "172.16.",
    ]
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


# ─── Routes applicatives ────────────────────────────────────────────────────────


@app.route("/")
@login_required
def index():
    cfg = get_config()
    return render_template(
        "index.html",
        grist_url=cfg["url"],
        has_config=bool(cfg["url"] and cfg["key"]),
    )


@app.route("/api/config", methods=["POST"])
@api_login_required
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
        app.logger.info(
            "Cle API mise a jour en session par %s : %s",
            current_user.email,
            redact(key),
        )

    return jsonify({"ok": True})


@app.route("/api/service-accounts", methods=["GET"])
@api_login_required
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


@app.route("/api/service-accounts", methods=["POST"])
@api_login_required
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
        return jsonify(
            {"error": "La date d'expiration ne peut pas être antérieure à aujourd'hui"}
        ), 400
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
        app.logger.info(
            "Compte cree par %s : login=%s", current_user.email, data.get("login", "?")
        )
        return jsonify(data)
    except requests.exceptions.RequestException as e:
        app.logger.error("Erreur creation compte : %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/service-accounts/<int:account_id>", methods=["DELETE"])
@api_login_required
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
        app.logger.info("Compte supprime par %s : #%d", current_user.email, account_id)
        return jsonify({"ok": True})
    except requests.exceptions.RequestException as e:
        app.logger.error("Erreur suppression #%d : %s", account_id, e)
        return jsonify({"error": str(e)}), 500


# ─── Headers de securite ─────────────────────────────────────────────────────


@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


# ─── Initialisation de la base au premier lancement ───────────────────────────

with app.app_context():
    db.create_all()
    # Cree un premier compte admin si la table est vide (bootstrap)
    if User.query.count() == 0:
        bootstrap_email = os.environ.get("ADMIN_EMAIL")
        bootstrap_password = os.environ.get("ADMIN_PASSWORD")
        if bootstrap_email and bootstrap_password:
            admin = User(email=bootstrap_email.strip().lower(), is_admin=True)
            admin.set_password(bootstrap_password)
            db.session.add(admin)
            db.session.commit()
            app.logger.info("Compte administrateur initial cree : %s", bootstrap_email)
        else:
            app.logger.warning(
                "Aucun utilisateur en base et ADMIN_EMAIL/ADMIN_PASSWORD non definis. "
                "Definissez-les dans .env pour creer le premier compte admin au demarrage."
            )


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
