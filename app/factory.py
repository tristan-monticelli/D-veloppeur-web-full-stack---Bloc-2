import os
from typing import Mapping

from flask import Flask

from app.domain import AppConfig
from app.infrastructure.database import DatabaseService
from app.services import (
    EventService,
    ReminderService,
    SMTPEmailService,
    UserSessionService,
    WeatherService,
)
from app.routes import register_routes


DEFAULT_SECRET_KEY = '9f2c6a11-8b7c-4a9d-b8f9-3c2e1f7a5d9e-dev'
DEFAULT_SMTP_PORT = '587'


def _load_local_env(base_path: str) -> None:
    env_path = os.path.join(base_path, '.env')
    if not os.path.isfile(env_path):
        return

    with open(env_path, encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            os.environ[key] = value


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


def _create_email_service(app: Flask):
    smtp_host = os.environ.get('SMTP_HOST', '').strip()
    smtp_username = os.environ.get('SMTP_USERNAME', '').strip()
    smtp_password = os.environ.get('SMTP_PASSWORD', '').strip()
    smtp_from_email = os.environ.get('SMTP_FROM_EMAIL', '').strip()

    if not (smtp_host and smtp_username and smtp_password and smtp_from_email):
        raise RuntimeError(
            'Configuration SMTP manquante. Définissez SMTP_HOST, SMTP_USERNAME, '
            'SMTP_PASSWORD et SMTP_FROM_EMAIL.'
        )

    try:
        smtp_port = int(os.environ.get('SMTP_PORT', DEFAULT_SMTP_PORT))
    except ValueError:
        smtp_port = 587
    smtp_use_tls = os.environ.get('SMTP_USE_TLS', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
    return SMTPEmailService(
        host=smtp_host,
        port=smtp_port,
        username=smtp_username,
        password=smtp_password,
        from_email=smtp_from_email,
        use_tls=smtp_use_tls,
        logger=app.logger,
    )


def create_app(test_config: Mapping[str, object] | None = None) -> Flask:
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    _load_local_env(base_path)
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
    email_service = _create_email_service(app)
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
