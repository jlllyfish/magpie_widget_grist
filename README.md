# Magpie — guide des comptes de service Grist

Page statique qui guide les agents dans la création et la gestion de leurs
comptes de service Grist **via la console API de Grist**.

## Principe

Magpie ne manipule aucune clé API et ne fait aucun appel réseau :

- il prépare la requête JSON (nom, description, date d'expiration) à coller dans la console ;
- il ouvre la console API de l'instance (`/apiconsole`), qui fonctionne avec la
  session Grist de l'agent, sans clé API personnelle ;
- il explique comment récupérer la clé, partager un document et gérer les comptes existants.

Aucun serveur applicatif, aucune base de données, aucun stockage navigateur.

> Cette branche remplace la version Flask, dans laquelle la clé API de l'agent
> transitait par le serveur Magpie. La CORS de Grist n'autorise l'en-tête
> `Authorization` que depuis les origines de même domaine de base que l'instance :
> un widget hébergé ailleurs devait donc relayer la clé par un serveur.

## Hébergement

N'importe quel hébergement statique convient (GitHub Pages, serveur web, etc.) :
il suffit de servir le dépôt tel quel. Le fichier `.nojekyll` évite le traitement
Jekyll sur GitHub Pages.

En local :

```bash
python -m http.server 8000
```

## Utilisation comme widget Grist

1. Dans un document : **Nouveau** > **Ajouter une vue à la page** > **Personnalisée**.
2. Saisir l'URL où Magpie est hébergé.
3. Niveau d'accès : **Aucun accès au document** (Magpie n'en a pas besoin).

L'instance Grist est alors détectée automatiquement pour le lien vers la console.

## Prérequis côté instance

Les comptes de service doivent être activés sur l'instance
(`GRIST_ENABLE_SERVICE_ACCOUNTS`).
