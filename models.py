"""
Modeles de base de donnees.

Pas de table utilisateur : ce fork widget n'a pas d'authentification
propre. La cle API Grist saisie par l'utilisateur (stockee uniquement en
session serveur, jamais en base) fait office d'autorisation.
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


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
