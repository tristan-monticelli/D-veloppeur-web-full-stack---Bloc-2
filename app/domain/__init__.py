import re
from dataclasses import dataclass


_FALLBACK_WEATHER_ICON = 'not-available-fill'
_VALID_WEATHER_ICONS = {
    'clear-day-fill',
    'hail-fill',
    'hurricane-fill',
    'not-available-fill',
    'overcast-day-fill',
    'partly-cloudy-day-fill',
    'rain-fill',
    'snow-fill',
    'thunderstorms-fill',
    'thunderstorms-snow-fill',
    'wind-alert-fill',
}
_WEATHER_EMOJI_MAP = {
    '☀️': 'clear-day-fill',
    '☀': 'clear-day-fill',
    '🌤️': 'partly-cloudy-day-fill',
    '🌤': 'partly-cloudy-day-fill',
    '☁️': 'overcast-day-fill',
    '☁': 'overcast-day-fill',
    '🌦️': 'rain-fill',
    '🌦': 'rain-fill',
    '🌧️': 'rain-fill',
    '🌧': 'rain-fill',
    '⛈️': 'thunderstorms-fill',
    '⛈': 'thunderstorms-fill',
    '⏳': 'not-available-fill',
}


def normalize_weather_icon(raw_icone: str | None) -> str:
    if not raw_icone:
        return _FALLBACK_WEATHER_ICON

    icon = str(raw_icone).strip()
    if not icon:
        return _FALLBACK_WEATHER_ICON

    normalized = icon.removesuffix('.svg')
    if normalized.startswith('icons/'):
        normalized = normalized.split('icons/', 1)[-1]
    normalized = normalized.replace('static/', '')
    if not normalized:
        return _FALLBACK_WEATHER_ICON

    if normalized in _WEATHER_EMOJI_MAP:
        return _WEATHER_EMOJI_MAP[normalized]
    if normalized in _VALID_WEATHER_ICONS:
        return normalized

    return _FALLBACK_WEATHER_ICON


class DomainError(RuntimeError):
    """Base error for application domain exceptions."""


class ValidationError(DomainError):
    """Raised when user input does not pass business validation."""


class NotFoundError(DomainError):
    """Raised when a requested entity is missing."""


class GeocodeError(DomainError):
    """Raised when geocoding service is not available."""


class GeocodeVilleInconnue(ValueError):
    """Raised when a city cannot be found by geocoding services."""


class EmailDeliveryError(RuntimeError):
    """Raised when an email cannot be sent."""


@dataclass(frozen=True)
class AppConfig:
    weather_rain_threshold_mm: float = 5.0
    weather_wind_threshold_kmph: float = 50.0
    weather_cache_ttl_hours: int = 4
    weather_error_cache_minutes: int = 60
    weather_network_cache_minutes: int = 5
    weather_max_forecast_days: int = 16
    suggestion_days_before: int = 14
    suggestion_days_after: int = 14


@dataclass
class WeatherSnapshot:
    weathercode: int | None
    pluie: float
    vent: float
    icone: str
    icone_label: str
    alerte: bool = False
    cached: bool = False

    @classmethod
    def unavailable(cls, *, label: str, icone: str = 'not-available-fill') -> 'WeatherSnapshot':
        return cls(None, 0.0, 0.0, icone, label, False, False)

    def to_dict(self) -> dict:
        return {
            'pluie': float(self.pluie),
            'vent': float(self.vent),
            'icone': self.icone,
            'icone_label': self.icone_label,
            'alerte': bool(self.alerte),
            'cached': bool(self.cached),
        }

    def __post_init__(self):
        self.icone = normalize_weather_icon(self.icone)



@dataclass
class Event:
    id: int | None
    nom: str
    date: str
    ville: str
    email: str
    statut: str
    user_id: int | None = None
    created_at: str | None = None


@dataclass
class User:
    id: int | None
    prenom: str
    email: str
    password: str
    created_at: str | None = None


@dataclass
class SuggestionOption:
    code: str
    date: str
    jour: str
    ecart: int
    jours: int
    meteo: WeatherSnapshot
    qualite: str
    classe: str
    classe_index: str

    @property
    def meteo_dict(self) -> dict:
        return self.meteo.to_dict()

    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'date': self.date,
            'jour': self.jour,
            'ecart': self.ecart,
            'jours': self.jours,
            'meteo': self.meteo_dict,
            'qualite': self.qualite,
            'classe': self.classe,
            'classe_index': self.classe_index,
        }


@dataclass
class SuggestionSet:
    avant_soleil: SuggestionOption | None = None
    avant_proche: SuggestionOption | None = None
    apres_proche: SuggestionOption | None = None
    apres_soleil: SuggestionOption | None = None

    def to_dict(self) -> dict:
        return {
            'avant_soleil': self.avant_soleil.to_dict() if self.avant_soleil else None,
            'avant_proche': self.avant_proche.to_dict() if self.avant_proche else None,
            'apres_proche': self.apres_proche.to_dict() if self.apres_proche else None,
            'apres_soleil': self.apres_soleil.to_dict() if self.apres_soleil else None,
        }


class EmailAddressList:
    _EMAIL_RX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

    @classmethod
    def parse(cls, raw_emails: str | None) -> list[str]:
        if not raw_emails:
            return []
        valeurs: list[str] = []
        for valeur in re.split(r'[,\n;]', str(raw_emails)):
            email = cls._normaliser(valeur)
            if not email:
                continue
            if not cls._EMAIL_RX.fullmatch(email):
                raise ValidationError(f'Adresse email invalide : {email}')
            if email not in valeurs:
                valeurs.append(email)
        return valeurs

    @staticmethod
    def _normaliser(valeur: str) -> str:
        return valeur.strip().lower()
