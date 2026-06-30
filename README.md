# Météo Sentinelle

Application Flask de gestion d'événements avec prévisions météo, suggestions de dates, notifications e-mail et rappels.

Le projet sert à organiser des événements sensibles à la météo : l'utilisateur crée un événement, l'application récupère les prévisions, propose des dates alternatives si besoin et peut prévenir les destinataires par e-mail.

## Stack

- **Backend** : Flask, Python
- **Frontend** : HTML/Jinja2, CSS, JavaScript vanilla
- **Base de données** : SQLite (`events.db`)
- **Infrastructure HTTP** : `urllib.request`, avec fallback `curl` pour les appels JSON
- **Météo / géocodage** : Open-Meteo Forecast API et Open-Meteo Geocoding API
- **Notifications** : SMTP via `smtplib`
- **Templates e-mail** : Jinja2 (`template/emails/`)
- **Sessions** : sessions Flask par cookie signé

## Architecture

```text
app/
  domain/             modèles, erreurs métier, configuration domaine
  infrastructure/     SQLite, repository, client HTTP JSON
  interfaces/         présentation et helpers d'interface
  interfaces/web/     routes Flask
  services/           logique métier : événements, météo, rappels, e-mails, session
static/               CSS, JavaScript, icônes, images, polices
template/             pages Jinja2
template/emails/      templates HTML/CSS des e-mails
main.py               point d'entrée Flask
```

## Changements d'infrastructure

- L'envoi d'e-mails utilise un service SMTP dédié (`SMTPEmailService`).
- La configuration peut être chargée depuis un fichier `.env` local au démarrage.
- Les e-mails ont une version texte et une version HTML générée avec Jinja2.
- La couche infrastructure centralise SQLite, le cache météo, le cache de géocodage et les logs de notifications.
- Les appels API météo passent par un helper HTTP JSON avec fallback `curl`.
- Les rappels ont une route utilisateur (`/reminders/run`) et une route interne protégeable par token (`/internal/reminders/run`).

## Configuration

Créer un fichier `.env` à partir de `.env.example` :

```bash
cp .env.example .env
```

Variables principales :

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=votre_email@example.com
SMTP_PASSWORD=votre_mot_de_passe_application
SMTP_FROM_EMAIL=votre_email@example.com
SMTP_USE_TLS=1

# optionnel
SECRET_KEY=une-cle-secrete
REMINDER_RUN_TOKEN=token_interne
FLASK_DEBUG=1
PORT=5000
```

Sans configuration SMTP complète, l'application refuse de démarrer pour éviter de découvrir le problème seulement au moment d'envoyer un e-mail.

## Lancement

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask jinja2
python main.py
```

Accès local :

```text
http://127.0.0.1:5000
```

La base SQLite est initialisée automatiquement au lancement si les tables n'existent pas.

## Routes principales

- `GET /` : tableau de bord des événements.
- `POST /planifier` : création d'un événement.
- `GET/POST /events/<id_evenement>/edit` : édition complète d'un événement.
- `POST /events/<id_evenement>/date` : changement de date avec recalcul météo.
- `POST /events/<id_evenement>/notify` : notification e-mail aux destinataires.
- `POST /events/<id_evenement>/delete` : suppression d'un événement, avec notification optionnelle.
- `POST /reminders/run` : exécution manuelle des rappels.
- `POST /internal/reminders/run` : exécution interne des rappels, utilisable par cron ou batch.
- `GET /repondre/<id>/<action>` : réponse d'un destinataire.
- `GET/POST /register`, `GET/POST /login`, `GET /logout` : authentification.

## Données stockées

SQLite contient notamment :

- `users` : comptes utilisateurs.
- `events` : événements planifiés.
- `city_cache` : coordonnées des villes déjà géocodées.
- `meteo_cache` : prévisions météo mises en cache par ville/date.
- `event_notification_log` : trace des rappels déjà envoyés.

## Points à présenter à l'oral

- Séparation claire entre routes Flask, services métier et infrastructure.
- Choix de Flask et vanilla JS pour garder une application simple et légère.
- SQLite adapté au contexte local/démonstration, avec initialisation automatique.
- Open-Meteo évite une clé API pour la météo et le géocodage.
- SMTP permet un envoi d'e-mails maîtrisé avec configuration par variables d'environnement.
- Cache météo/géocodage pour éviter des appels API inutiles.
- Notifications et rappels séparés pour distinguer action utilisateur et traitement batch.
