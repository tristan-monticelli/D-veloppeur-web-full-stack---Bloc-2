import json
import urllib.parse
import urllib.request
import os

from app.domain import EmailAddressList, EmailDeliveryError, Event, ValidationError, WeatherSnapshot


DEFAULT_WEB3FORMS_ACCESS_KEY = 'aa012bd9-0238-41d7-8b7f-7343178f9f7f'
WEB3FORMS_URL = 'https://api.web3forms.com/submit'


def resolve_web3forms_access_key(raw_key: str | None = None) -> str:
    """Résout la clé Web3Forms.

    Stratégie explicite: variable d'environnement possible, sinon valeur de TP.
    """
    if raw_key and raw_key.strip():
        return raw_key.strip()
    return os.environ.get('WEB3FORMS_ACCESS_KEY', DEFAULT_WEB3FORMS_ACCESS_KEY).strip() or DEFAULT_WEB3FORMS_ACCESS_KEY


class EmailService:
    def send_alert(self, event: Event, meteo: WeatherSnapshot, base_url: str, message_perso: str = '') -> None:
        raise NotImplementedError

    def send_member_reminder(
        self,
        event: Event,
        meteo: WeatherSnapshot,
        reminder_offset: int,
        message_perso: str = '',
        base_url: str = '',
    ) -> None:
        raise NotImplementedError

    def send_manager_weather_warning(
        self,
        event: Event,
        meteo: WeatherSnapshot,
        base_url: str = '',
        message_perso: str = '',
    ) -> None:
        raise NotImplementedError

    def compose_member_reminder(
        self,
        event: Event,
        meteo: WeatherSnapshot,
        reminder_offset: int,
        message_perso: str = '',
        base_url: str = '',
    ) -> tuple[str, str]:
        raise NotImplementedError

    def compose_manager_weather_warning(
        self,
        event: Event,
        meteo: WeatherSnapshot,
        base_url: str = '',
        message_perso: str = '',
    ) -> tuple[str, str]:
        raise NotImplementedError

    def send_event_update_notification(
        self,
        initial: Event,
        updated: Event,
        event_type: str,
        recipients_raw: str | None = None,
        message_perso: str = '',
    ) -> None:
        raise NotImplementedError


class LegacyWeb3FormsEmailService(EmailService):
    def __init__(self, access_key: str, submit_url: str, logger=None):
        self._access_key = access_key
        self._url = submit_url
        self._logger = logger
        if self._logger and self._access_key == DEFAULT_WEB3FORMS_ACCESS_KEY:
            self._logger.warning(
                'Clé Web3Forms configurée avec la valeur par défaut (possiblement hors de votre compte). '
                'Définissez WEB3FORMS_ACCESS_KEY avec votre propre clé dans l’environnement.'
            )

    def _warn(self, message: str, *args):
        if self._logger:
            self._logger.warning(message, *args)

    def _error(self, message: str, *args):
        if self._logger:
            self._logger.error(message, *args)

    def _send(
        self,
        destinataire: str,
        sujet: str,
        message: str,
        nom_evenement: str = 'Événement',
        destinataires_suppl: list[str] | None = None,
    ) -> None:
        if not self._access_key:
            self._warn('Web3Forms non configuré — email non envoyé.')
            return

        destinataires = [destinataire]
        for extra in destinataires_suppl or []:
            if extra and extra not in destinataires:
                destinataires.append(extra)

        for email in destinataires:
            donnees = json.dumps(
                {
                    'access_key': self._access_key,
                    'subject': sujet,
                    'from_name': 'Météo Sentinelle',
                    'name': nom_evenement,
                    'email': email,
                    'message': message,
                }
            ).encode('utf-8')

            requete = urllib.request.Request(
                self._url,
                data=donnees,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                method='POST',
            )

            try:
                with urllib.request.urlopen(requete, timeout=10) as reponse:
                    corps = reponse.read()
                    try:
                        retour = json.loads(corps or b'{}')
                    except json.JSONDecodeError:
                        self._error('Réponse Web3Forms non JSON pour %s: %r', destinataire, corps)
                        raise EmailDeliveryError('Réponse Web3Forms invalide')

                    if not retour.get('success', False):
                        message_erreur = (
                            retour.get('message')
                            or (retour.get('body') or {}).get('message')
                            or str(retour)
                        )
                        self._error('Erreur Web3Forms pour %s: %s', destinataire, message_erreur)
                        raise EmailDeliveryError(str(message_erreur))
            except Exception as erreur:
                self._error('Erreur envoi Web3Forms : %s', erreur)
                raise EmailDeliveryError(str(erreur)) from erreur

    def _compose_alert(self, event: Event, meteo: WeatherSnapshot, base_url: str, message_perso: str = '') -> tuple[str, str]:
        corps_perso = f"\nMessage de l'organisateur :\n{message_perso}\n" if message_perso else ''
        sujet = f"Alerte météo — {event.nom} le {event.date}"
        message = f"""
Bonjour,

Une alerte météo a été déclenchée pour votre événement :

  • Événement : {event.nom}
  • Date      : {event.date}
  • Lieu      : {event.ville}

Conditions prévues :
  {meteo.icone_label}
  Pluie : {meteo.pluie} mm  |  Vent : {meteo.vent} km/h

{corps_perso}
Que souhaitez-vous faire ?

  Confirmer quand même : {base_url}/repondre/{event.id}/confirmer
  Voir les autres dates : {base_url}/events/{event.id}/edit
  Reporter l'événement : {base_url}/repondre/{event.id}/reporter

— Météo Sentinelle
""".strip()
        return sujet, message

    def compose_member_reminder(
        self,
        event: Event,
        meteo: WeatherSnapshot,
        reminder_offset: int,
        message_perso: str = '',
        base_url: str = '',
    ) -> tuple[str, str]:
        tag = 'J-7' if reminder_offset >= 7 else 'J-1'
        corps_perso = f"\nMessage de l'organisateur :\n{message_perso}\n" if message_perso else ''
        sujet = f"Rappel ({tag}) — {event.nom} le {event.date}"
        message = f"""
Bonjour,

Message de rappel pour votre événement :

  • Événement : {event.nom}
  • Date      : {event.date}
  • Lieu      : {event.ville}
  • Prévision : {meteo.icone_label}
               Pluie : {meteo.pluie} mm  |  Vent : {meteo.vent} km/h

{corps_perso}
Actions :
  [ Ouvrir l'événement ]

— Météo Sentinelle
""".strip()
        return sujet, message

    def compose_manager_weather_warning(
        self,
        event: Event,
        meteo: WeatherSnapshot,
        base_url: str = '',
        message_perso: str = '',
    ) -> tuple[str, str]:
        corps_perso = f"\nMessage de l'organisateur :\n{message_perso}\n" if message_perso else ''
        sujet = f"Alerte météo gestionnaire — {event.nom} le {event.date}"
        message = f"""
Bonjour,

Alerte météo à J-1 pour votre événement :

  • Événement : {event.nom}
  • Date      : {event.date}
  • Lieu      : {event.ville}
  • Prévision : {meteo.icone_label}
               Pluie : {meteo.pluie} mm  |  Vent : {meteo.vent} km/h

{corps_perso}
Action :
  [ Vérifier la préparation de l'événement ]

— Météo Sentinelle
""".strip()
        return sujet, message

    def _compose_update(
        self,
        initial: Event,
        updated: Event,
        event_type: str,
        message_perso: str = '',
    ) -> tuple[str, str]:
        corps_perso = f"\nMessage de l'organisateur :\n{message_perso}\n" if message_perso else ''
        if event_type == 'delete':
            sujet = f"Événement supprimé — {initial.nom}"
            message = f"""
Bonjour,

L'événement suivant a été supprimé :

  • Événement : {initial.nom}
  • Date      : {initial.date}
  • Lieu      : {initial.ville}

{corps_perso}
— Météo Sentinelle
""".strip()
            return sujet, message

        changements: list[str] = []
        if initial.nom != updated.nom:
            changements.append(f"Nom : {initial.nom} → {updated.nom}")
        if initial.date != updated.date:
            changements.append(f"Date : {initial.date} → {updated.date}")
        if initial.ville != updated.ville:
            changements.append(f"Lieu : {initial.ville} → {updated.ville}")
        if initial.email != updated.email:
            changements.append(f"Destinataires : {initial.email} → {updated.email}")

        sujet = f"Événement modifié — {updated.nom}"
        if changements:
            details = '\n'.join(f"  • {changement}" for changement in changements)
            message = f"""
Bonjour,

L'événement a été mis à jour :

{details}

{corps_perso}
— Météo Sentinelle
""".strip()
        else:
            message = f"""
Bonjour,

L'événement a été confirmé sans changement visible.

{corps_perso}
— Météo Sentinelle
""".strip()

        return sujet, message

    def send_alert(self, event: Event, meteo: WeatherSnapshot, base_url: str, message_perso: str = '') -> None:
        try:
            destinataires = EmailAddressList.parse(event.email)
        except ValidationError as erreur:
            raise EmailDeliveryError(str(erreur)) from erreur
        if not destinataires:
            self._warn("Aucun destinataire défini pour l'événement %s", event.id)
            return

        sujet, message = self._compose_alert(event, meteo, base_url, message_perso=message_perso)
        for destinataire in destinataires:
            self._send(destinataire, sujet, message, event.nom)

    def send_member_reminder(
        self,
        event: Event,
        meteo: WeatherSnapshot,
        reminder_offset: int,
        message_perso: str = '',
        base_url: str = '',
    ) -> None:
        try:
            destinataires = EmailAddressList.parse(event.email)
        except ValidationError as erreur:
            raise EmailDeliveryError(str(erreur)) from erreur
        if not destinataires:
            self._warn("Aucun destinataire défini pour l'événement %s", event.id)
            return

        sujet, message = self.compose_member_reminder(
            event,
            meteo,
            reminder_offset=reminder_offset,
            base_url=base_url,
            message_perso=message_perso,
        )
        for destinataire in destinataires:
            self._send(destinataire, sujet, message, event.nom)

    def send_manager_weather_warning(
        self,
        event: Event,
        meteo: WeatherSnapshot,
        base_url: str = '',
        message_perso: str = '',
    ) -> None:
        try:
            destinataires = EmailAddressList.parse(event.email)
        except ValidationError as erreur:
            raise EmailDeliveryError(str(erreur)) from erreur
        if not destinataires:
            self._warn("Aucun destinataire défini pour l'événement %s", event.id)
            return

        sujet, message = self.compose_manager_weather_warning(
            event,
            meteo,
            base_url=base_url,
            message_perso=message_perso,
        )
        for destinataire in destinataires:
            self._send(destinataire, sujet, message, event.nom)

    def send_event_update_notification(
        self,
        initial: Event,
        updated: Event,
        event_type: str,
        recipients_raw: str | None = None,
        message_perso: str = '',
    ) -> None:
        try:
            destinataires = EmailAddressList.parse(recipients_raw or initial.email)
        except ValidationError as erreur:
            raise EmailDeliveryError(str(erreur)) from erreur
        if not destinataires:
            self._warn("Aucun destinataire défini pour l'événement %s", initial.id)
            return

        sujet, message = self._compose_update(initial, updated, event_type, message_perso=message_perso)
        for destinataire in destinataires:
            self._send(destinataire, sujet, message, updated.nom)


__all__ = [
    'EmailService',
    'LegacyWeb3FormsEmailService',
    'DEFAULT_WEB3FORMS_ACCESS_KEY',
    'resolve_web3forms_access_key',
    'WEB3FORMS_URL',
]
