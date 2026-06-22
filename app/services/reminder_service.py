from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from app.domain import EmailAddressList, Event, WeatherSnapshot
from app.infrastructure.database import DatabaseService
from app.services.email_service import EmailService
from app.services.weather_service import WeatherService


@dataclass
class ReminderResult:
    as_of: str
    sent: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_sent(self, kind: str, event_id: int | None) -> None:
        self.sent.append(f'{kind}:{event_id}')

    def add_skipped(self, kind: str, event_id: int | None) -> None:
        self.skipped.append(f'{kind}:{event_id}')

    def add_error(self, kind: str, event_id: int | None, message: str) -> None:
        self.errors.append(f'{kind}:{event_id}:{message}')


class ReminderService:
    MEMBER_REMINDER_7D = 'member_reminder_7d'
    MEMBER_REMINDER_1D = 'member_reminder_1d'
    MANAGER_WARNING_1D = 'manager_warning_1d'

    def __init__(
        self,
        db_service: DatabaseService,
        weather_service: WeatherService,
        email_service: EmailService,
        logger=None,
    ):
        self._db_service = db_service
        self._weather_service = weather_service
        self._email_service = email_service
        self._logger = logger

    def _warn(self, message: str, *args) -> None:
        if self._logger:
            self._logger.warning(message, *args)

    @staticmethod
    def _to_event_date_list(dates: set[str]) -> set[str]:
        return {date_texte for date_texte in dates if date_texte}

    def _resolve_manager_email(self, event: Event) -> str | None:
        if event.user_id:
            gestionnaire = self._db_service.get_user_by_id(event.user_id)
            if gestionnaire and gestionnaire.email:
                return gestionnaire.email
        if event.email:
            return event.email
        return None

    def _send_member_reminder(
        self,
        event: Event,
        meteo: WeatherSnapshot,
        offset: int,
        kind: str,
        result: ReminderResult,
    ) -> None:
        if not event.id:
            result.add_skipped(kind, event.id)
            return
        if self._db_service.has_notification_been_sent(event.id, kind):
            result.add_skipped(kind, event.id)
            return

        try:
            self._email_service.send_member_reminder(
                event,
                meteo,
                reminder_offset=offset,
                message_perso='',
            )
            self._db_service.mark_notification_sent(event.id, kind, datetime.now(UTC).isoformat())
            result.add_sent(kind, event.id)
        except Exception as erreur:
            self._warn('Rappel membre non envoyé pour %s (%s): %s', event.id, kind, erreur)
            result.add_error(kind, event.id, str(erreur))

    def _send_manager_warning(self, event: Event, meteo: WeatherSnapshot, kind: str, result: ReminderResult) -> None:
        if not event.id:
            result.add_skipped(kind, event.id)
            return
        if self._db_service.has_notification_been_sent(event.id, kind):
            result.add_skipped(kind, event.id)
            return

        manager_email = self._resolve_manager_email(event)
        if not manager_email:
            result.add_skipped(kind, event.id)
            return

        destinataires = EmailAddressList.parse(manager_email)
        if not destinataires:
            result.add_skipped(kind, event.id)
            return
        manager_event = Event(
            id=event.id,
            nom=event.nom,
            date=event.date,
            ville=event.ville,
            email=', '.join(destinataires),
            statut=event.statut,
            user_id=event.user_id,
            created_at=event.created_at,
        )
        try:
            self._email_service.send_manager_weather_warning(manager_event, meteo)
            self._db_service.mark_notification_sent(event.id, kind, datetime.now(UTC).isoformat())
            result.add_sent(kind, event.id)
        except Exception as erreur:
            self._warn('Alerte gestionnaire non envoyée pour %s (%s): %s', event.id, kind, erreur)
            result.add_error(kind, event.id, str(erreur))

    def send_upcoming_notifications(self, as_of: date | None = None) -> ReminderResult:
        as_of = as_of or date.today()
        cible_dates = self._to_event_date_list(
            {
                (as_of + timedelta(days=7)).strftime('%Y-%m-%d'),
                (as_of + timedelta(days=1)).strftime('%Y-%m-%d'),
            }
        )
        resultat = ReminderResult(as_of=as_of.isoformat())
        evenements = self._db_service.get_events_by_dates(cible_dates)

        for evenement in evenements:
            meteo = self._weather_service.get_weather(evenement.ville, evenement.date)
            if evenement.date == (as_of + timedelta(days=7)).strftime('%Y-%m-%d'):
                self._send_member_reminder(evenement, meteo, 7, self.MEMBER_REMINDER_7D, resultat)
            if evenement.date == (as_of + timedelta(days=1)).strftime('%Y-%m-%d'):
                self._send_member_reminder(evenement, meteo, 1, self.MEMBER_REMINDER_1D, resultat)
                if meteo.alerte:
                    self._send_manager_warning(evenement, meteo, self.MANAGER_WARNING_1D, resultat)

        return resultat


__all__ = [
    'ReminderResult',
    'ReminderService',
]
