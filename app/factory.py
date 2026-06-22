import os
from typing import Mapping

from flask import Flask

from app.domain import AppConfig
from app.infrastructure.database import DatabaseService
from app.services import (
    EventService,
    LegacyWeb3FormsEmailService,
    ReminderService,
    UserSessionService,
    WeatherService,
    WEB3FORMS_URL,
    resolve_web3forms_access_key,
)
from app.routes import register_routes


# Stratégie explicite choisie: source principale = variables d'environnement,
# fallback documenté vers des valeurs de développement.
DEFAULT_SECRET_KEY = '9f2c6a11-8b7c-4a9d-b8f9-3c2e1f7a5d9e-dev'


def _resolve_debug() -> bool:
    valeur = os.environ.get('FLASK_DEBUG')
    if valeur is None:
        return True
    return valeur.strip().lower() in {'1', 'true', 'yes', 'on'}


def _resolve_database_path(test_config: Mapping[str, object] | None) -> str:
    if test_config is not None:
        valeur = test_config.get('DATABASE_PATH')
        if isinstance(valeur, str) and valeur.strip():
            return valeur
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, 'events.db'))


def _resolve_secret_key() -> str:
    valeur = os.environ.get('SECRET_KEY')
    if valeur and valeur.strip():
        return valeur.strip()
    return DEFAULT_SECRET_KEY


def create_app(test_config: Mapping[str, object] | None = None) -> Flask:
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_path, 'template'),
        static_folder=os.path.join(base_path, 'static'),
    )
    app.config.from_mapping(
        SECRET_KEY=_resolve_secret_key(),
        DEBUG=_resolve_debug(),
        TESTING=False,
    )
    if test_config:
        app.config.update(test_config)

    config = AppConfig()
    db_service = DatabaseService(_resolve_database_path(test_config))
    weather_service = WeatherService(db_service, config, logger=app.logger)
    email_service = LegacyWeb3FormsEmailService(
        resolve_web3forms_access_key(os.environ.get('WEB3FORMS_ACCESS_KEY')),
        WEB3FORMS_URL,
        logger=app.logger,
    )
    reminder_service = ReminderService(db_service, weather_service, email_service, logger=app.logger)
    event_service = EventService(db_service, weather_service, email_service, config, logger=app.logger)
    user_session_service = UserSessionService()
    reminder_run_token = os.environ.get('REMINDER_RUN_TOKEN', '').strip()

    db_service.initialize()
    register_routes(
        app,
        db_service,
        weather_service,
        event_service,
        user_session_service,
        reminder_service,
        email_service,
        reminder_run_token=reminder_run_token,
    )

    return app
