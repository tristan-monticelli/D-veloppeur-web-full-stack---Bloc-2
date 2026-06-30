import smtplib
import ssl
import re
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.domain import EmailAddressList, EmailDeliveryError, Event, ValidationError, WeatherSnapshot


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


class SMTPEmailService(EmailService):
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: str = 'Météo Sentinelle',
        use_tls: bool = True,
        logger=None,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._from_name = from_name
        self._use_tls = use_tls
        self._logger = logger
        self._email_template_dir = Path(__file__).resolve().parents[2] / 'template' / 'emails'
        self._jinja = Environment(
            loader=FileSystemLoader(str(self._email_template_dir)),
            autoescape=select_autoescape(['html', 'xml']),
        )

    def _warn(self, message: str, *args):
        if self._logger:
            self._logger.warning(message, *args)

    def _send(
        self,
        destinataire: str,
        sujet: str,
        message: str,
        nom_evenement: str = 'Événement',
        destinataires_suppl: list[str] | None = None,
    ) -> None:
        destinataires = [destinataire]
        for extra in destinataires_suppl or []:
            if extra and extra not in destinataires:
                destinataires.append(extra)

        for email in destinataires:
            courriel = EmailMessage()
            courriel['Subject'] = sujet
            courriel['From'] = f'{self._from_name} <{self._from_email}>'
            courriel['To'] = email
            courriel.set_content(message)
            courriel.add_alternative(self._html_template(sujet, message), subtype='html')

            try:
                if self._use_tls:
                    with smtplib.SMTP(self._host, self._port, timeout=15) as serveur:
                        serveur.starttls(context=ssl.create_default_context())
                        serveur.login(self._username, self._password)
                        serveur.send_message(courriel)
                else:
                    with smtplib.SMTP_SSL(self._host, self._port, context=ssl.create_default_context(), timeout=15) as serveur:
                        serveur.login(self._username, self._password)
                        serveur.send_message(courriel)
            except Exception as erreur:
                raise EmailDeliveryError(str(erreur)) from erreur

    def _html_template(self, sujet: str, message: str) -> str:
        template = self._jinja.get_template('base.html')
        css_content = (self._email_template_dir / 'email.css').read_text(encoding='utf-8')
        contexte = self._build_email_context(message)
        return template.render(
            css_content=css_content,
            sujet=sujet,
            intro=contexte['intro'],
            details=contexte['details'],
            actions=contexte['actions'],
            notes=contexte['notes'],
            app_name='Météo Sentinelle',
        )

    def _build_email_context(self, message: str) -> dict:
        details = []
        actions = []
        intro = []
        notes = []
        url_pattern = re.compile(r'(https?://\S+)')

        for raw_line in message.splitlines():
            ligne = raw_line.strip()
            if not ligne or ligne == '— Météo Sentinelle':
                continue

            if ligne.startswith('•'):
                contenu = ligne.lstrip('•').strip()
                if ':' in contenu:
                    libelle, valeur = contenu.split(':', 1)
                    details.append({'label': libelle.strip(), 'value': valeur.strip()})
                else:
                    notes.append(contenu)
                continue

            url_match = url_pattern.search(ligne)
            if url_match:
                url = url_match.group(1)
                label = ligne[:url_match.start()].strip(' :') or 'Ouvrir le lien'
                actions.append({'label': label, 'url': url})
                continue

            if ligne.endswith(':') or ligne in {'Actions :', 'Action :'}:
                continue

            if ligne == 'Bonjour,':
                continue

            if len(intro) < 2:
                intro.append(ligne)
            else:
                notes.append(ligne)

        return {
            'intro': intro,
            'details': details,
            'actions': actions,
            'notes': notes,
        }

    def _compose_alert(self, event: Event, meteo: WeatherSnapshot, base_url: str, message_perso: str = '') -> tuple[str, str]:
        corps_perso = f"\nMessage de l'organisateur :\n{message_perso}\n" if message_perso else ''
        sujet = f"Alerte météo — {event.nom} le {event.date}"
        message = f"""
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
L'événement a été mis à jour :

{details}

{corps_perso}
— Météo Sentinelle
""".strip()
        else:
            message = f"""
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
    'SMTPEmailService',
]
