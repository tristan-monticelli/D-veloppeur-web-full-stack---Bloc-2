from datetime import date, datetime, timedelta

import sqlite3
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from app.domain import (
    EmailAddressList,
    EmailDeliveryError,
    Event,
    GeocodeVilleInconnue,
    GeocodeError,
    NotFoundError,
    ValidationError,
)
from app.interfaces.presentation import (
    build_date_change_payload,
    format_event_date_label,
    json_error,
    json_success,
)
from app.infrastructure.database import DatabaseService
from app.services import EventService, ReminderService, UserSessionService, WeatherService


def register_routes(
    app,
    db_service: DatabaseService,
    weather_service: WeatherService,
    event_service: EventService,
    user_session_service: UserSessionService,
    reminder_service: ReminderService,
    email_service,
    reminder_run_token: str | None = None,
):
    routes = Blueprint('web', __name__)

    def _url_retour_sure(retour_brut: str | None) -> str:
        return user_session_service.safe_return_url(retour_brut)

    def _rediriger_vers_connexion(url_retour: str = '/'):
        flash('Connectez-vous pour continuer.', 'info')
        return redirect(url_for('web.connexion', next=_url_retour_sure(url_retour)))

    def _is_ajax_request() -> bool:
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    def _require_auth(url_retour: str = '/') -> tuple[int | None, tuple | None]:
        id_utilisateur = user_session_service.current_user_id(session)
        if id_utilisateur:
            return id_utilisateur, None
        if _is_ajax_request():
            return None, json_error('Connectez-vous pour continuer.', 401)
        return None, _rediriger_vers_connexion(url_retour)

    def _check_reminder_token() -> bool:
        token_recu = (
            request.headers.get('X-Reminder-Run-Token')
            or request.args.get('token')
            or request.form.get('token')
            or ''
        ).strip()
        return bool(reminder_run_token) and token_recu == reminder_run_token

    @routes.route('/')
    def index():
        id_utilisateur = user_session_service.current_user_id(session)
        evenements: list[dict] = []

        if id_utilisateur:
            for evenement in event_service.list_for_user(id_utilisateur):
                meteo = weather_service.get_weather(evenement.ville, evenement.date)
                suggestions = event_service.build_event_suggestions(evenement)
                evenements.append(
                    {
                        'id': evenement.id,
                        'nom': evenement.nom,
                        'date': evenement.date,
                        'date_affichee': event_service.format_event_date_label(evenement.date),
                        'ville': evenement.ville,
                        'meteo_icone_label': meteo.icone_label,
                        'meteo_icone': meteo.icone,
                        'suggestions_date': suggestions.to_dict(),
                        'email': evenement.email,
                    }
                )

        return render_template(
            'index.html',
            evenements=evenements,
            brouillon_evenement=session.get('pending_event') or {},
        )

    @routes.route('/planifier', methods=['POST'])
    def planifier():
        id_utilisateur, reponse_non_autorisee = _require_auth(url_for('web.index'))
        if reponse_non_autorisee:
            return reponse_non_autorisee

        utilisateur = user_session_service.current_user(session, db_service)
        if not utilisateur:
            flash('Session invalide. Reconnectez-vous.', 'error')
            return _rediriger_vers_connexion(url_for('web.index'))

        nom = request.form.get('nom', '').strip()
        date_texte = request.form.get('date', '').strip()
        ville = request.form.get('ville', '').strip()

        try:
            created = event_service.create_event(
                user=utilisateur,
                nom=nom,
                date_texte=date_texte,
                ville=ville,
                email=utilisateur.email,
                validate_city=True,
            )
        except ValidationError as erreur:
            flash(str(erreur), 'error')
            return redirect(url_for('web.index'))
        except GeocodeVilleInconnue:
            flash('Ville introuvable. Vérifiez l’orthographe de la ville.', 'error')
            return redirect(url_for('web.index'))
        except GeocodeError:
            app.logger.warning("Géocodage indisponible pour %s. L'événement est enregistré sans blocage.", ville)
            created = event_service.create_event(
                user=utilisateur,
                nom=nom,
                date_texte=date_texte,
                ville=ville,
                email=utilisateur.email,
                validate_city=False,
            )

        return redirect(url_for('web.modifier_evenement', id_evenement=created.id))

    @routes.route('/events/<int:id_evenement>/date', methods=['POST'])
    def changer_date_evenement(id_evenement: int):
        id_utilisateur, reponse_non_autorisee = _require_auth(url_for('web.index'))
        is_ajax = _is_ajax_request()
        if reponse_non_autorisee:
            return reponse_non_autorisee

        nouvelle_date = request.form.get('date', '').strip()
        if not nouvelle_date and request.is_json:
            nouvelle_date = (request.json or {}).get('date', '').strip()

        send_notification = request.form.get('send_notification') == '1'
        if not send_notification and request.is_json:
            send_notification = (request.json or {}).get('send_notification') == '1'

        message_perso = request.form.get('message', '').strip()
        if not message_perso and request.is_json:
            message_perso = (request.json or {}).get('message', '').strip()

        try:
            ancien_evenement = event_service.get_event_for_user(id_evenement, id_utilisateur)
            evenement = event_service.change_date(id_evenement, id_utilisateur, nouvelle_date)
        except NotFoundError as erreur:
            if is_ajax:
                return json_error(str(erreur), 404)
            flash(str(erreur), 'error')
            return redirect(url_for('web.index'))
        except ValidationError as erreur:
            if is_ajax:
                return json_error(str(erreur), 400)
            flash(str(erreur), 'error')
            return redirect(request.referrer or url_for('web.index'))

        notification_envoyee = False
        alerte_notification = None
        if send_notification:
            try:
                email_service.send_event_update_notification(
                    ancien_evenement,
                    evenement,
                    'update',
                    recipients_raw=evenement.email,
                    message_perso=message_perso,
                )
                notification_envoyee = True
            except EmailDeliveryError:
                alerte_notification = "La date est mise à jour, mais l'email n'a pas pu être envoyé."

        if is_ajax:
            suggestions = event_service.build_event_suggestions(evenement)
            meteo = weather_service.get_weather(evenement.ville, nouvelle_date)
            payload = build_date_change_payload(evenement, suggestions, meteo)
            if notification_envoyee:
                payload['message'] = "Date mise à jour et email envoyé aux destinataires."
            elif alerte_notification:
                payload['message'] = alerte_notification
            return json_success(payload)

        if notification_envoyee:
            flash("Date mise à jour et email envoyé aux destinataires.", 'success')
        elif alerte_notification:
            flash(alerte_notification, 'error')

        return redirect(request.referrer or url_for('web.index'))

    @routes.route('/events/<int:id_evenement>/edit', methods=['GET', 'POST'])
    def modifier_evenement(id_evenement: int):
        id_utilisateur, reponse_non_autorisee = _require_auth(url_for('web.index'))
        if reponse_non_autorisee:
            return reponse_non_autorisee

        try:
            evenement = event_service.get_event_for_user(id_evenement, id_utilisateur)
        except NotFoundError:
            flash('Événement introuvable.', 'error')
            return redirect(url_for('web.index'))

        if request.method == 'POST':
            nom = request.form.get('nom', '').strip()
            date_texte = request.form.get('date', '').strip()
            ville = request.form.get('ville', '').strip()
            destinataires_raw = request.form.get('destinataires', '').strip()

            try:
                destinataires = EmailAddressList.parse(destinataires_raw)
                if not destinataires:
                    raise ValidationError('Ajoute au moins une adresse email valide.')
                destinataires_texte = ', '.join(destinataires)
                ancien, _ = event_service.update_event(
                    event_id=id_evenement,
                    user_id=id_utilisateur,
                    nom=nom,
                    date_texte=date_texte,
                    ville=ville,
                    email=destinataires_texte,
                    validate_city=True,
                )
            except GeocodeVilleInconnue:
                flash('Ville introuvable. Vérifiez l’orthographe de la ville.', 'error')
                return redirect(url_for('web.modifier_evenement', id_evenement=id_evenement))
            except GeocodeError:
                app.logger.warning("Géocodage indisponible pour %s. La modification est conservée.", ville)
                ancien, _ = event_service.update_event(
                    event_id=id_evenement,
                    user_id=id_utilisateur,
                    nom=nom,
                    date_texte=date_texte,
                    ville=ville,
                    email=destinataires_texte,
                    validate_city=False,
                )
            except ValidationError as erreur:
                flash(str(erreur), 'error')
                return redirect(url_for('web.modifier_evenement', id_evenement=id_evenement))

            if request.form.get('send_notification') == '1':
                updated = Event(
                    id=ancien.id,
                    nom=nom,
                    date=date_texte,
                    ville=ville,
                    email=destinataires_texte,
                    statut=ancien.statut,
                    user_id=ancien.user_id,
                    created_at=ancien.created_at,
                )
                try:
                    email_service.send_event_update_notification(
                        ancien,
                        updated,
                        'update',
                        recipients_raw=destinataires_texte,
                        message_perso=request.form.get('message', '').strip(),
                    )
                    flash('Événement mis à jour et notification envoyée.', 'success')
                except EmailDeliveryError:
                    flash("Événement mis à jour, mais l'email n'a pas pu être envoyé.", 'error')
            else:
                flash('Événement mis à jour.', 'success')

            return redirect(url_for('web.index'))

        suggestions = event_service.build_event_suggestions(evenement)
        meteo = weather_service.get_weather(evenement.ville, evenement.date)
        return render_template(
            'edit_event.html',
            evenement=evenement,
            suggestions_date=suggestions.to_dict(),
            meteo_evenement=meteo.to_dict(),
            date_affichee=format_event_date_label(evenement.date),
        )

    @routes.route('/events/<int:id_evenement>/notify', methods=['POST'])
    def envoyer_mail_notification(id_evenement: int):
        id_utilisateur, reponse_non_autorisee = _require_auth(url_for('web.index'))
        is_ajax = _is_ajax_request()
        if reponse_non_autorisee:
            return reponse_non_autorisee

        try:
            evenement = event_service.get_event_for_user(id_evenement, id_utilisateur)
        except NotFoundError:
            if is_ajax:
                return json_error("Événement introuvable.", 404)
            flash("Événement introuvable.", 'error')
            return redirect(url_for('web.index'))

        meteo = weather_service.get_weather(evenement.ville, evenement.date)
        message_perso = request.form.get('message', '').strip()
        if not message_perso and request.is_json:
            message_perso = (request.json or {}).get('message', '').strip()

        try:
            email_service.send_member_reminder(
                evenement,
                meteo,
                reminder_offset=0,
                message_perso=message_perso,
                base_url=request.url_root.rstrip('/'),
            )
        except EmailDeliveryError:
            if is_ajax:
                return json_error("Erreur d'envoi réseau de l'email.", 500)
            flash("Erreur d'envoi réseau de l'email.", 'error')
            return redirect(request.referrer or url_for('web.index'))

        if is_ajax:
            return json_success({'success': True, 'message': "Email envoyé aux destinataires."})

        flash('Email envoyé aux destinataires.', 'success')
        return redirect(request.referrer or url_for('web.index'))

    @routes.route('/reminders/run', methods=['POST'])
    def envoyer_rappels_manuels():
        id_utilisateur, reponse_non_autorisee = _require_auth(url_for('web.index'))
        if reponse_non_autorisee:
            return reponse_non_autorisee

        resultats = reminder_service.send_upcoming_notifications(date.today())
        flash(
            'Rappels traités : '
            f'{len(resultats.sent)} envoyés, {len(resultats.skipped)} déjà envoyés, {len(resultats.errors)} erreurs.',
            'success' if not resultats.errors else 'warning',
        )
        return redirect(url_for('web.index'))

    @routes.route('/internal/reminders/run', methods=['POST'])
    def run_rappels_auto():
        if not _check_reminder_token():
            return json_error('Token invalide.', 401)

        resultats = reminder_service.send_upcoming_notifications(date.today())
        return json_success(
            {
                'success': True,
                'as_of': resultats.as_of,
                'sent': resultats.sent,
                'skipped': resultats.skipped,
                'errors': resultats.errors,
            }
        )

    @routes.route('/events/<int:id_evenement>/delete', methods=['POST'])
    def supprimer_evenement(id_evenement: int):
        id_utilisateur, reponse_non_autorisee = _require_auth(url_for('web.index'))
        is_ajax = _is_ajax_request()
        if reponse_non_autorisee:
            return reponse_non_autorisee

        try:
            evenement = event_service.get_event_for_user(id_evenement, id_utilisateur)
        except NotFoundError as erreur:
            if is_ajax:
                return json_error(str(erreur), 404)
            flash(str(erreur), 'error')
            return redirect(url_for('web.index'))

        send_notification = request.form.get('send_notification') == '1'
        if not send_notification and request.is_json:
            send_notification = (request.json or {}).get('send_notification') == '1'

        alerte_notification = None
        if send_notification:
            message_perso = request.form.get('message', '').strip()
            if not message_perso and request.is_json:
                message_perso = (request.json or {}).get('message', '').strip()
            try:
                email_service.send_event_update_notification(
                    evenement,
                    evenement,
                    'delete',
                    recipients_raw=request.form.get('destinataires') or evenement.email,
                    message_perso=message_perso,
                )
            except EmailDeliveryError:
                alerte_notification = "La suppression a été appliquée, mais l'email de notification n'a pas pu être envoyé."

        try:
            event_service.delete_event(id_evenement, id_utilisateur)
        except NotFoundError as erreur:
            if is_ajax:
                return json_error(str(erreur), 404)
            flash(str(erreur), 'error')
            return redirect(url_for('web.index'))

        message = "L'événement a été supprimé avec succès."
        if alerte_notification:
            message = f'{message} {alerte_notification}'
            if not is_ajax:
                flash(message, 'warning')

        if is_ajax:
            return json_success({'success': True, 'message': message})

        return redirect(url_for('web.index'))

    @routes.route('/repondre/<int:id_evenement>/<action>')
    def repondre(id_evenement: int, action: str):
        id_utilisateur, reponse_non_autorisee = _require_auth(url_for('web.index'))
        is_ajax = _is_ajax_request()
        if reponse_non_autorisee:
            return reponse_non_autorisee

        try:
            event_service.update_event_status(id_evenement, id_utilisateur, action)
        except ValidationError as erreur:
            if is_ajax:
                return json_error(str(erreur), 400)
            flash(str(erreur), 'error')
            return redirect(url_for('web.index'))
        except NotFoundError as erreur:
            if is_ajax:
                return json_error(str(erreur), 404)
            flash(str(erreur), 'error')
            return redirect(url_for('web.index'))

        if is_ajax:
            return json_success({'success': True, 'message': "Réponse enregistrée pour l'événement."})

        flash("Réponse enregistrée pour l'événement.", 'success')
        return redirect(url_for('web.index'))

    @routes.route('/register', methods=['GET', 'POST'])
    def inscription():
        if request.method == 'POST':
            prenom = request.form.get('prenom', '').strip()
            email = request.form.get('email', '').strip().lower()
            mot_de_passe = request.form.get('password', '')
            confirmation_mot_de_passe = request.form.get('password_confirm', '')
            url_retour = request.form.get('next', '').strip()

            if not prenom or not email or not mot_de_passe:
                flash('Tous les champs sont obligatoires.', 'error')
                return render_template('register.html', next=_url_retour_sure(url_retour), form=request.form)

            if len(mot_de_passe) < 8:
                flash('Le mot de passe doit faire au moins 8 caractères.', 'error')
                return render_template('register.html', next=_url_retour_sure(url_retour), form=request.form)

            if mot_de_passe != confirmation_mot_de_passe:
                flash('Les mots de passe ne correspondent pas.', 'error')
                return render_template('register.html', next=_url_retour_sure(url_retour), form=request.form)

            mot_de_passe_hash = generate_password_hash(mot_de_passe)
            date_creation = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            try:
                utilisateur = db_service.insert_user(prenom, email, mot_de_passe_hash, date_creation)
            except sqlite3.IntegrityError:
                flash('Cet email est déjà utilisé.', 'error')
                return render_template('register.html', next=_url_retour_sure(url_retour), form=request.form)

            session['user_id'] = utilisateur.id
            if event_service.finalize_pending_event(session, utilisateur, request.url_root.rstrip('/')):
                flash('Ville introuvable. Vérifiez l’orthographe de la ville.', 'error')
            cible = _url_retour_sure(
                url_retour or request.form.get('next', '') or user_session_service.pop_pending_next(session)
            )
            return redirect(cible)

        return render_template('register.html', next=_url_retour_sure(request.args.get('next', '')))

    @routes.route('/login', methods=['GET', 'POST'])
    def connexion():
        url_retour = _url_retour_sure(request.args.get('next', ''))
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            mot_de_passe = request.form.get('password', '')
            retour_poste = _url_retour_sure(request.form.get('next', ''))
            if not retour_poste:
                retour_poste = _url_retour_sure(user_session_service.pop_pending_next(session))

            utilisateur = db_service.get_user_by_email(email)
            if not utilisateur or not check_password_hash(utilisateur.password, mot_de_passe):
                flash('Identifiants invalides.', 'error')
                return render_template('login.html', next=retour_poste)

            session['user_id'] = utilisateur.id
            event_service.finalize_pending_event(session, utilisateur, request.url_root.rstrip('/'))
            return redirect(retour_poste)

        return render_template('login.html', next=url_retour)

    @routes.route('/logout')
    def deconnexion():
        session.clear()
        return redirect(url_for('web.index'))

    app.register_blueprint(routes)
