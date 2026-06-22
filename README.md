# Météo Sentinelle

Projet Flask pour gérer des événements avec météo, notifications par email et rappels.

## Stack (ultra rapide)

- **Backend**: Flask (Python)
- **DB**: SQLite (fichier local `events.db` via `sqlite3`)
- **Frontend**: HTML/Jinja2 + CSS + JS vanilla
- **HTTP interne**: `urllib.request` (API calls serveur)
- **Auth/session**: Flask sessions (cookies)

## Structure (vue rapide)

- `app/` : code applicatif
  - `domain/` : modèles de données (Event, User, WeatherSnapshot...)
  - `infrastructure/` : DB + couche HTTP/requêtes basses (repository, http_client)
  - `services/` : règles métier (email, weather, événements, rappels)
  - `interfaces/` : routes web Flask + templates helpers
- `template/` : templates Jinja2 (pages).
- `static/` : assets (`css/`, `js/`, icônes/images)
- `README.md` : documentation projet
- `main.py` : point d'entrée Flask

## API externes utilisées (et utilité)

- `GET https://open-meteo.com` (via `api.open-meteo.com/v1/forecast`) : météo prévisionnelle pour chaque événement.
- `GET https://geocoding-api.open-meteo.com/v1/search` : résolution ville -> coordonnées.
- `POST https://api.web3forms.com/submit` : envoi des emails de notification.

## API internes (routes Flask)

- `GET /` : dashboard des événements.
- `POST /planifier` : créer un événement.
- `POST /events/<id_evenement>/edit` : modifier/mettre à jour.
- `POST /events/<id_evenement>/date` : changer la date et recalcul météo.
- `POST /events/<id_evenement>/delete` : supprimer un événement.
- `POST /events/<id_evenement>/notify` : message simple membre.
- `POST /debug/rappels-meteo` : trigger manuel (utilisateur) des rappels.
- `POST /internal/reminders/run` : trigger batch (cron) des rappels.
- `GET /repondre/<id>/<action>` : action membre (confirmer/reporter).
- `GET/POST /register`, `GET/POST /login`, `GET /logout` : auth utilisateur.

## Configuration importante

```bash
export WEB3FORMS_ACCESS_KEY=votre_cle_web3forms
export FLASK_APP=main.py
export FLASK_ENV=development
```

Lancement :

```bash
flask run
```

Accès local : `http://127.0.0.1:5000`
