"""
Modeles de base de donnees.

Un seul modele pour l'instant : User.
Les mots de passe ne sont JAMAIS stockes en clair -- uniquement leur hash
(werkzeug.security utilise scrypt par defaut, robuste et sans dependance
supplementaire).
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw_password):
        """Hache le mot de passe -- jamais stocke en clair."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        """Verifie le mot de passe fourni contre le hash stocke."""
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self):
        return f"<User {self.email}>"


class ServiceAccountDocLink(db.Model):
    """
    Lien minimal entre un compte de service Grist (identifie par son login)
    et un document Grist auquel il a ete ajoute via Magpie.

    On ne stocke QUE l'identifiant du document -- le nom du document et le
    role actuel du compte sont toujours recuperes en direct depuis l'API
    Grist au moment de l'affichage, pour ne jamais etre desynchronises si
    le role est modifie depuis Grist directement.
    """
    __tablename__ = "service_account_doc_links"

    id = db.Column(db.Integer, primary_key=True)
    service_account_login = db.Column(db.String(255), nullable=False, index=True)
    doc_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("service_account_login", "doc_id", name="uq_login_doc"),
    )

    def __repr__(self):
        return f"<ServiceAccountDocLink {self.service_account_login} -> {self.doc_id}>"
