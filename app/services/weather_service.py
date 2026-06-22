import socket
import unicodedata
import urllib.parse
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError

from app.domain import (AppConfig, GeocodeError, GeocodeVilleInconnue,
                        WeatherSnapshot)
from app.infrastructure.database import DatabaseService
from app.infrastructure.http_client import read_json_http


class WeatherService:
    def __init__(self, db_service: DatabaseService, config: AppConfig, logger=None):
        self._db_service = db_service
        self._config = config
        self._logger = logger

    @staticmethod
    def normalize_city(city: str) -> str:
        texte = (city or '').strip().lower()
        texte = unicodedata.normalize('NFKD', texte)
        return ''.join(c for c in texte if not unicodedata.combining(c))

    @staticmethod
    def _libelle_meteo(code_meteo: int | None, pluie: float, vent: float) -> tuple[str, str]:
        if code_meteo is None:
            code_meteo = -1

        if code_meteo in (95, 96, 99):
            if code_meteo in (96, 99):
                return 'thunderstorms-fill', 'Orage avec grêle'
            return 'thunderstorms-fill', 'Orage prévu'

        if code_meteo in (71, 73, 75, 77, 85, 86):
            return 'snow-fill', 'Neige prévue'

        if code_meteo in (56, 57, 66, 67):
            return 'thunderstorms-fill', 'Pluie verglaçante'

        if code_meteo in (51, 53, 55):
            return 'rain-fill', 'Bruine'

        if code_meteo in (61, 63, 65, 80, 81, 82):
            if code_meteo in (65, 81, 82):
                return 'rain-fill', 'Pluie forte'
            return 'rain-fill', 'Pluie'

        if code_meteo in (45, 48):
            return 'not-available-fill', 'Brouillard'

        if code_meteo in (1, 2):
            return 'partly-cloudy-day-fill', 'Partiellement nuageux'
        if code_meteo in (3,):
            return 'overcast-day-fill', 'Nuageux'

        if code_meteo == 0:
            return 'clear-day-fill', 'Beau temps prévu'

        if pluie > 5.0 and vent > 50.0:
            return 'thunderstorms-fill', 'Orage et vent fort'
        if pluie > 5.0:
            return 'rain-fill', 'Pluie prévue'
        if vent > 50.0:
            return 'wind-alert-fill', 'Rafales de vent'
        return 'clear-day-fill', 'Beau temps prévu'

    def _to_weather_snapshot(self, donnees_journalieres: dict, index_date: int, date_texte: str) -> WeatherSnapshot:
        def _valeur_du_jour(liste):
            return liste[index_date] if isinstance(liste, list) and len(liste) > index_date else None

        pluie_brute = _valeur_du_jour(donnees_journalieres.get('precipitation_sum'))
        vent_brut = _valeur_du_jour(
            donnees_journalieres.get('wind_speed_10m_max') or donnees_journalieres.get('windspeed_10m_max')
        )
        code_meteo = _valeur_du_jour(donnees_journalieres.get('weather_code') or donnees_journalieres.get('weathercode'))

        if pluie_brute is None or vent_brut is None or code_meteo is None:
            raise ValueError(f'Données météo incomplètes pour {date_texte}')

        pluie = float(pluie_brute) or 0
        vent = float(vent_brut) or 0
        code = int(code_meteo)
        seuil_pluie = self._config.weather_rain_threshold_mm
        seuil_vent = self._config.weather_wind_threshold_kmph
        icone, icone_label = self._libelle_meteo(code, pluie, vent)
        alerte = (
            pluie > seuil_pluie
            or vent > seuil_vent
            or code in (95, 96, 99, 80, 81, 82, 85, 86)
        )
        return WeatherSnapshot(
            weathercode=code,
            pluie=pluie,
            vent=vent,
            icone=icone,
            icone_label=icone_label,
            alerte=alerte,
            cached=False,
        )

    def _cache_duration_hours(self, erreur: Exception | None = None) -> float:
        if isinstance(erreur, (URLError, HTTPError, socket.gaierror, TimeoutError)):
            return max(self._config.weather_network_cache_minutes / 60, 0.083)

        message = str(erreur).lower() if erreur else ''
        if any(
            fragment in message
            for fragment in (
                'name or service not known',
                'nodename nor servname',
                'temporary failure',
                'name resolution',
                'timed out',
                'connection timed out',
                'connection refused',
            )
        ):
            return max(self._config.weather_network_cache_minutes / 60, 0.083)

        return max(self._config.weather_error_cache_minutes / 60, 0.083)

    def _warn(self, message: str, *args):
        if self._logger:
            self._logger.warning(message, *args)

    def _error(self, message: str, *args):
        if self._logger:
            self._logger.error(message, *args)

    def geocode(self, city: str, *, strict: bool = False) -> tuple[float, float] | None:
        if not city:
            return None

        city_key = self.normalize_city(city)
        cached = self._db_service.get_city_cache(city_key)
        if cached:
            return cached

        aucun_resultat_open_meteo = False
        erreur_geocodage: Exception | None = None

        try:
            params = urllib.parse.urlencode({'name': city, 'count': 1, 'language': 'fr', 'format': 'json'})
            url = f'https://geocoding-api.open-meteo.com/v1/search?{params}'
            donnees = read_json_http(url, delai=8)
            resultats = donnees.get('results') if isinstance(donnees, dict) else None
            if resultats:
                coords = resultats[0]
                lat = float(coords['latitude'])
                lon = float(coords['longitude'])
                self._db_service.save_city_cache(city_key, lat, lon)
                return lat, lon
            else:
                aucun_resultat_open_meteo = True
        except Exception as exc:
            self._warn('Geocoder Open-Meteo indisponible pour %s : %s', city, exc)
            erreur_geocodage = exc

        try:
            params = urllib.parse.urlencode({'q': city, 'format': 'json', 'limit': 1})
            url = f'https://nominatim.openstreetmap.org/search?{params}'
            donnees = read_json_http(url, delai=5, entetes={'User-Agent': 'meteo-evenement/1.0 (contact: user@example.com)'})
            if donnees:
                lat = float(donnees[0]['lat'])
                lon = float(donnees[0]['lon'])
                self._db_service.save_city_cache(city_key, lat, lon)
                return lat, lon
            else:
                aucun_resultat_open_meteo = True
        except Exception as exc:
            self._warn('Echec geocode Nominatim pour %s : %s', city, exc)
            erreur_geocodage = exc

        if strict:
            if aucun_resultat_open_meteo:
                raise GeocodeVilleInconnue(f'Ville introuvable : {city}')
            if erreur_geocodage:
                raise GeocodeError(str(erreur_geocodage))

        return None

    def get_weather_range(self, city: str, date_debut: date, date_fin: date) -> dict[str, WeatherSnapshot]:
        if not city or date_debut > date_fin:
            return {}

        city_key = self.normalize_city(city)
        date_debut_texte = date_debut.strftime('%Y-%m-%d')
        date_fin_texte = date_fin.strftime('%Y-%m-%d')

        cache = self._db_service.get_cached_weather_range(city_key, date_debut_texte, date_fin_texte)
        cache_avec_expiration = self._db_service.get_cached_weather_range(
            city_key, date_debut_texte, date_fin_texte, include_expired=True
        )
        result: dict[str, WeatherSnapshot] = {date_texte: snapshot for date_texte, snapshot in cache.items()}
        dates_demandes: list[str] = []

        curseur = date_debut
        while curseur <= date_fin:
            dates_demandes.append(curseur.strftime('%Y-%m-%d'))
            curseur += timedelta(days=1)

        dates_manquantes = [date_texte for date_texte in dates_demandes if date_texte not in result]
        date_prevision_max = date.today() + timedelta(days=self._config.weather_max_forecast_days - 1)

        dates_indisponibles = [
            date_texte
            for date_texte in dates_manquantes
            if datetime.strptime(date_texte, '%Y-%m-%d').date() > date_prevision_max
        ]
        for date_texte in dates_indisponibles:
            snapshot = WeatherSnapshot.unavailable(
                label='Prévision météo pas encore disponible',
                icone='not-available-fill',
            )
            result[date_texte] = snapshot
            self._db_service.save_weather_cache(city_key, date_texte, snapshot, self._config.weather_network_cache_minutes / 60)

        dates_a_consulter = [
            date_texte for date_texte in dates_manquantes
            if date_texte not in dates_indisponibles
        ]

        if not dates_a_consulter:
            return result

        try:
            coords = self.geocode(city, strict=True)
        except GeocodeVilleInconnue:
            snapshot = WeatherSnapshot.unavailable(label='Ville non trouvée', icone='not-available-fill')
            for date_texte in dates_a_consulter:
                result[date_texte] = snapshot
                self._db_service.save_weather_cache(city_key, date_texte, snapshot, self._cache_duration_hours())
            return result
        except GeocodeError:
            snapshot = WeatherSnapshot.unavailable(label='Service météo indisponible pour le moment', icone='not-available-fill')
            for date_texte in dates_a_consulter:
                ancien = cache_avec_expiration.get(date_texte)
                if ancien:
                    result[date_texte] = ancien
                    continue
                result[date_texte] = snapshot
                self._db_service.save_weather_cache(city_key, date_texte, snapshot, self._cache_duration_hours())
            return result

        if not coords:
            snapshot = WeatherSnapshot.unavailable(label='Lieu non trouvé', icone='not-available-fill')
            for date_texte in dates_a_consulter:
                result[date_texte] = snapshot
                self._db_service.save_weather_cache(city_key, date_texte, snapshot, self._cache_duration_hours())
            return result

        lat, lon = coords
        date_min_api = min(datetime.strptime(d, '%Y-%m-%d').date() for d in dates_a_consulter)
        date_max_api = max(datetime.strptime(d, '%Y-%m-%d').date() for d in dates_a_consulter)

        params = urllib.parse.urlencode(
            {
                'latitude': lat,
                'longitude': lon,
                'daily': 'precipitation_sum,wind_speed_10m_max,weather_code',
                'start_date': date_min_api.strftime('%Y-%m-%d'),
                'end_date': date_max_api.strftime('%Y-%m-%d'),
                'timezone': 'Europe/Paris',
                'wind_speed_unit': 'kmh',
                'precipitation_unit': 'mm',
            }
        )
        url = f'https://api.open-meteo.com/v1/forecast?{params}'

        try:
            donnees = read_json_http(url, delai=8)
            if not isinstance(donnees, dict):
                raise ValueError('Réponse Open-Meteo invalide')
            if 'error' in donnees:
                raise RuntimeError(f"Open-Meteo error: {donnees['error']}")
            donnees_journalieres = donnees.get('daily')
            if not isinstance(donnees_journalieres, dict):
                raise ValueError('Réponse Open-Meteo: pas de données journalières')
            dates_api = donnees_journalieres.get('time')
            if not isinstance(dates_api, list) or len(dates_api) == 0:
                raise ValueError('Réponse Open-Meteo: pas de dates journalières')

            for index_date, date_texte in enumerate(dates_api):
                if date_texte not in dates_a_consulter:
                    continue
                meteo = self._to_weather_snapshot(donnees_journalieres, index_date, date_texte)
                result[date_texte] = meteo
                self._db_service.save_weather_cache(city_key, date_texte, meteo, self._config.weather_cache_ttl_hours)

            for date_texte in dates_a_consulter:
                if date_texte in result:
                    continue
                snapshot = cache_avec_expiration.get(date_texte) or WeatherSnapshot.unavailable(
                    label='Date météo indisponible',
                    icone='not-available-fill',
                )
                result[date_texte] = snapshot
                self._db_service.save_weather_cache(city_key, date_texte, snapshot, self._cache_duration_hours())

            return result

        except Exception as exc:
            self._error('Echec Open-Meteo pour %s (%s -> %s) : %s', city, date_min_api, date_max_api, exc)
            snapshot = WeatherSnapshot.unavailable(label='Service météo indisponible pour le moment', icone='not-available-fill')
            for date_texte in dates_a_consulter:
                ancien = cache_avec_expiration.get(date_texte)
                if ancien:
                    result[date_texte] = ancien
                    continue
                result[date_texte] = snapshot
                self._db_service.save_weather_cache(city_key, date_texte, snapshot, self._cache_duration_hours(exc))
            return result

    def get_weather(self, city: str, date_evenement: str) -> WeatherSnapshot:
        if not city:
            return WeatherSnapshot.unavailable(
                label='Ville non renseignée',
                icone='not-available-fill',
            )

        try:
            date_obj = datetime.strptime(date_evenement, '%Y-%m-%d').date()
        except ValueError:
            return WeatherSnapshot.unavailable(
                label='Date météo invalide',
                icone='not-available-fill',
            )

        return self.get_weather_range(city, date_obj, date_obj).get(
            date_evenement,
            WeatherSnapshot.unavailable(
                label='Date météo indisponible',
                icone='not-available-fill',
            ),
        )
