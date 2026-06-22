"""Presentation helpers for JSON payloads and HTML snippets."""

from datetime import datetime

from flask import render_template_string

from app.domain import Event, SuggestionSet, WeatherSnapshot


def format_event_date_label(raw: str) -> str:
    try:
        date_obj = datetime.strptime(raw, '%Y-%m-%d')
        jours_fr = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
        return f"{jours_fr[date_obj.weekday()]} {date_obj.strftime('%d/%m/%y')}"
    except (TypeError, ValueError):
        return raw


def render_suggestions_html(evenement: Event, suggestions: SuggestionSet, layout: str) -> str:
    return render_template_string(
        """{% from 'macros.html' import render_suggestions %}{{ render_suggestions(evenement, suggestions_date, layout=layout) }}""",
        evenement=dict(
            id=evenement.id,
            nom=evenement.nom,
            date=evenement.date,
            ville=evenement.ville,
            email=evenement.email,
            statut=evenement.statut,
        ),
        suggestions_date=suggestions.to_dict(),
        layout=layout,
    )


def render_icon_html(meteo_label: str, taille: int = 52, meteo_icone: str | None = None) -> str:
    return render_template_string(
        """{% from 'macros.html' import icone_meteo %}{{ icone_meteo(meteo_label, taille, meteo_icone=meteo_icone) }}""",
        meteo_label=meteo_label,
        taille=taille,
        meteo_icone=meteo_icone,
    )


def build_date_change_payload(event: Event, suggestions: SuggestionSet, meteo: WeatherSnapshot) -> dict:
    return {
        'success': True,
        'message': "Date de l'événement mise à jour avec succès.",
        'event': {
            'id': event.id,
            'date': event.date,
            'date_affichee': format_event_date_label(event.date),
            'meteo_icone_label': meteo.icone_label,
            'html_suggestions_index': render_suggestions_html(event, suggestions, 'index'),
            'html_suggestions_edit': render_suggestions_html(event, suggestions, 'edit'),
            'html_icone_index': render_icon_html(meteo.icone_label, meteo_icone=meteo.icone),
            'html_icone_edit': render_icon_html(meteo.icone_label, 82, meteo.icone),
        },
    }


def json_success(payload: dict):
    from flask import json as flask_json

    return flask_json.jsonify(payload), 200


def json_error(message: str, status: int = 400):
    from flask import json as flask_json

    return flask_json.jsonify({'success': False, 'message': message}), status
