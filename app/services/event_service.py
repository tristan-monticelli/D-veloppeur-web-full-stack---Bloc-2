from datetime import date, datetime, timedelta

from app.domain import (
    AppConfig,
    Event,
    GeocodeError,
    GeocodeVilleInconnue,
    NotFoundError,
    SuggestionOption,
    SuggestionSet,
    User,
    ValidationError,
)
from app.interfaces.presentation import format_event_date_label
from app.infrastructure.database import DatabaseService
from app.services.email_service import EmailService
from app.services.weather_service import WeatherService


class EventService:
    def __init__(
        self,
        db_service: DatabaseService,
        weather_service: WeatherService,
        email_service: EmailService,
        config: AppConfig,
        logger=None,
    ):
        self._db_service = db_service
        self._weather_service = weather_service
        self._email_service = email_service
        self._config = config
        self._logger = logger

    def _warn(self, message: str, *args):
        if self._logger:
            self._logger.warning(message, *args)

    @staticmethod
    def parse_event_date(raw: str) -> date:
        try:
            return datetime.strptime(raw.strip(), '%Y-%m-%d').date()
        except ValueError:
            raise ValidationError('Format de date invalide.')

    @staticmethod
    def format_event_date_label(raw: str) -> str:
        return format_event_date_label(raw)

    def validate_event_payload(self, nom: str, date_texte: str, ville: str) -> tuple[str, str, str, date]:
        nom = (nom or '').strip()
        date_texte = (date_texte or '').strip()
        ville = (ville or '').strip()

        if not nom or not date_texte or not ville:
            raise ValidationError('Le nom, la date et la ville sont obligatoires.')

        date_obj = self.parse_event_date(date_texte)
        if date_obj < date.today():
            raise ValidationError('La date doit être dans le futur.')

        return nom, date_texte, ville, date_obj

    def validate_event_payload_for_edit(self, nom: str, date_texte: str, ville: str) -> tuple[str, str, str, date]:
        nom = (nom or '').strip()
        date_texte = (date_texte or '').strip()
        ville = (ville or '').strip()

        if not nom or not date_texte or not ville:
            raise ValidationError('Nom, date et ville sont obligatoires.')

        date_obj = self.parse_event_date(date_texte)
        if date_obj < date.today():
            raise ValidationError('La date doit être dans le futur.')

        return nom, date_texte, ville, date_obj

    # Backward-compatible aliases for internal reuse.
    _validate_common = validate_event_payload
    _validate_common_edit = validate_event_payload_for_edit

    def list_for_user(self, user_id: int) -> list[Event]:
        return self._db_service.list_events_for_user(user_id)

    def build_event_suggestions(self, event: Event) -> SuggestionSet:
        meteo_courante = self._weather_service.get_weather(event.ville, event.date)
        if self._weather_quality(meteo_courante) == 'soleil':
            return SuggestionSet()

        date_courante = datetime.strptime(event.date, '%Y-%m-%d').date()
        date_min = max(date.today(), date_courante - timedelta(days=self._config.suggestion_days_before))
        date_max = min(
            date.today() + timedelta(days=self._config.weather_max_forecast_days - 1),
            date_courante + timedelta(days=self._config.suggestion_days_after),
        )
        meteo_plage = self._weather_service.get_weather_range(event.ville, date_min, date_max)

        options = SuggestionSet()

        for ecart in range(1, self._config.suggestion_days_before + 1):
            date_option = date_courante - timedelta(days=ecart)
            if date_option < date_min:
                continue
            snapshot = meteo_plage.get(date_option.strftime('%Y-%m-%d'))
            if not snapshot:
                continue
            qualite = self._weather_quality(snapshot)
            if qualite in ('correct', 'soleil') and options.avant_proche is None:
                options.avant_proche = self._build_option(date_courante, date_option, snapshot, '-')
            if qualite == 'soleil' and options.avant_soleil is None:
                options.avant_soleil = self._build_option(date_courante, date_option, snapshot, '--')

        for ecart in range(1, self._config.suggestion_days_after + 1):
            date_option = date_courante + timedelta(days=ecart)
            if date_option > date_max:
                continue
            snapshot = meteo_plage.get(date_option.strftime('%Y-%m-%d'))
            if not snapshot:
                continue
            qualite = self._weather_quality(snapshot)
            if qualite in ('correct', 'soleil') and options.apres_proche is None:
                options.apres_proche = self._build_option(date_courante, date_option, snapshot, '+')
            if qualite == 'soleil' and options.apres_soleil is None:
                options.apres_soleil = self._build_option(date_courante, date_option, snapshot, '++')

        return options

    def _weather_quality(self, meteo) -> str:
        libelle = meteo.icone_label
        if 'Beau' in libelle:
            return 'soleil'
        if meteo.alerte or any(mot in libelle for mot in ('Pluie', 'Orage', 'Vent', 'Grêle', 'Neige', 'indisponible', 'trouvé')):
            return 'mauvais'
        return 'correct'

    def _build_option(self, date_courante: date, date_option: date, meteo, code: str) -> SuggestionOption:
        ecart = (date_option - date_courante).days
        qualite = self._weather_quality(meteo)
        return SuggestionOption(
            code=code,
            date=date_option.strftime('%Y-%m-%d'),
            jour=date_option.strftime('%d/%m'),
            ecart=ecart,
            jours=abs(ecart),
            meteo=meteo,
            qualite=qualite,
            classe='suggestion-date--soleil' if qualite == 'soleil' else 'suggestion-date--correct' if qualite == 'correct' else 'suggestion-date--mauvais',
            classe_index='suggestion-date--reculer' if ecart < 0 else 'suggestion-date--avancer',
        )

    def get_event_for_user(self, event_id: int, user_id: int) -> Event:
        evenement = self._db_service.get_event(event_id, user_id)
        if not evenement:
            raise NotFoundError('Événement introuvable.')
        return evenement

    def update_event_status(self, event_id: int, user_id: int, action: str) -> Event:
        evenement = self.get_event_for_user(event_id, user_id)

        if action == 'confirmer':
            nouveau_statut = 'confirmé'
        elif action == 'reporter':
            nouveau_statut = 'reporté'
        else:
            raise ValidationError('Action de statut invalide.')

        if evenement.statut == nouveau_statut:
            return evenement

        rows = self._db_service.update_event_for_user(event_id, user_id, {'statut': nouveau_statut})
        if not rows:
            raise NotFoundError('Événement introuvable.')

        return self.get_event_for_user(event_id, user_id)

    def create_event(self, user: User, nom: str, date_texte: str, ville: str, email: str, *, validate_city: bool = True) -> Event:
        nom, date_texte, ville, date_obj = self.validate_event_payload(nom, date_texte, ville)
        if not email:
            raise ValidationError('Ajoute au moins une adresse email valide.')

        if validate_city:
            try:
                self._weather_service.geocode(ville, strict=True)
            except GeocodeVilleInconnue:
                raise

        event = Event(
            id=None,
            nom=nom,
            date=date_obj.strftime('%Y-%m-%d'),
            ville=ville,
            email=email,
            statut='prévu',
            user_id=user.id,
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        return self._db_service.insert_event(event)

    def update_event(
        self,
        event_id: int,
        user_id: int,
        nom: str,
        date_texte: str,
        ville: str,
        email: str,
        *,
        validate_city: bool = True,
    ) -> tuple[Event, Event]:
        existing = self.get_event_for_user(event_id, user_id)
        nom, date_texte, ville, date_obj = self.validate_event_payload_for_edit(nom, date_texte, ville)

        if validate_city:
            self._weather_service.geocode(ville, strict=True)

        updated = Event(
            id=existing.id,
            nom=nom,
            date=date_obj.strftime('%Y-%m-%d'),
            ville=ville,
            email=email,
            statut=existing.statut,
            user_id=existing.user_id,
            created_at=existing.created_at,
        )

        self._db_service.update_event(updated)
        return existing, updated

    def change_date(self, event_id: int, user_id: int, nouvelle_date: str) -> Event:
        date_texte = (nouvelle_date or '').strip()
        if not date_texte:
            raise ValidationError('La date est obligatoire.')

        date_obj = self.parse_event_date(date_texte)
        if date_obj < date.today():
            raise ValidationError('Date hors de la fenêtre météo disponible.')
        date_prevision_max = date.today() + timedelta(days=self._config.weather_max_forecast_days - 1)
        if date_obj > date_prevision_max:
            raise ValidationError('Date hors de la fenêtre météo disponible.')

        evenement = self.get_event_for_user(event_id, user_id)
        self._db_service.update_event_for_user(event_id, user_id, {'date': date_texte})
        return Event(
            id=evenement.id,
            nom=evenement.nom,
            date=date_texte,
            ville=evenement.ville,
            email=evenement.email,
            statut=evenement.statut,
            user_id=evenement.user_id,
            created_at=evenement.created_at,
        )

    def delete_event(self, event_id: int, user_id: int) -> Event:
        evenement = self.get_event_for_user(event_id, user_id)
        deleted = self._db_service.delete_event_for_user(event_id, user_id)
        if not deleted:
            raise NotFoundError('Événement introuvable.')
        return evenement

    def finalize_pending_event(self, session_data: dict, user: User, base_url: str) -> bool:
        brouillon = session_data.pop('pending_event', None)
        if not brouillon:
            return False

        nom = str(brouillon.get('nom', '')).strip()
        date_texte = str(brouillon.get('date', '')).strip()
        ville = str(brouillon.get('ville', '')).strip()

        if not nom or not date_texte or not ville:
            session_data.pop('pending_event', None)
            return False

        try:
            date_obj = datetime.strptime(date_texte, '%Y-%m-%d')
            if date_obj.date() < date.today():
                session_data.pop('pending_event', None)
                return False
            self._weather_service.geocode(ville, strict=True)
        except GeocodeVilleInconnue:
            session_data['pending_event'] = {'nom': nom, 'date': date_texte, 'ville': ville}
            return True
        except ValidationError:
            session_data.pop('pending_event', None)
            return False
        except GeocodeError:
            pass
        except ValueError:
            session_data.pop('pending_event', None)
            return False

        event = Event(
            id=None,
            nom=nom,
            date=date_texte,
            ville=ville,
            email=user.email,
            statut='prévu',
            user_id=user.id,
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        saved = self._db_service.insert_event(event)

        meteo = self._weather_service.get_weather(ville, date_texte)
        if meteo.alerte:
            try:
                self._email_service.send_alert(saved, meteo, base_url)
            except Exception:
                self._warn('Envoi d\'alerte impossible pour l\'événement en attente: %s', saved.id)

        return False
