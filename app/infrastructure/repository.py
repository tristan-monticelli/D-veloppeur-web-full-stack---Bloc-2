import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from app.domain import Event, User, WeatherSnapshot, normalize_weather_icon


class DatabaseService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS users (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    prenom     TEXT    NOT NULL,
                    email      TEXT    NOT NULL UNIQUE,
                    password   TEXT    NOT NULL,
                    created_at TEXT    NOT NULL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom        TEXT    NOT NULL,
                    date       TEXT    NOT NULL,
                    ville      TEXT    NOT NULL,
                    email      TEXT    NOT NULL,
                    statut     TEXT    NOT NULL DEFAULT 'prévu',
                    created_at TEXT    NOT NULL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS city_cache (
                    ville_key   TEXT PRIMARY KEY,
                    latitude    REAL    NOT NULL,
                    longitude   REAL    NOT NULL,
                    updated_at  TEXT    NOT NULL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS meteo_cache (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ville_key   TEXT    NOT NULL,
                    event_date  TEXT    NOT NULL,
                    weathercode INTEGER,
                    pluie       REAL    NOT NULL DEFAULT 0,
                    vent        REAL    NOT NULL DEFAULT 0,
                    icone       TEXT    NOT NULL,
                    icone_label TEXT    NOT NULL,
                    alerte      INTEGER NOT NULL DEFAULT 0,
                    fetched_at  TEXT    NOT NULL,
                    expires_at  TEXT    NOT NULL,
                    UNIQUE(ville_key, event_date)
                )
                '''
            )
            conn.execute('CREATE INDEX IF NOT EXISTS idx_meteo_cache_lookup ON meteo_cache(ville_key, event_date)')
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS event_notification_log (
                    event_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (event_id, kind)
                )
                '''
            )
            columns = {col[1] for col in conn.execute('PRAGMA table_info(events)').fetchall()}
            if 'user_id' not in columns:
                conn.execute('ALTER TABLE events ADD COLUMN user_id INTEGER')
            conn.commit()

    def _fetch_one(self, query: str, params: tuple = ()):  # noqa: ANN001
        with self.connection() as conn:
            return conn.execute(query, params).fetchone()

    def _fetch_all(self, query: str, params: tuple = ()):  # noqa: ANN001
        with self.connection() as conn:
            return conn.execute(query, params).fetchall()

    def _execute(self, query: str, params: tuple = ()) -> None:  # noqa: ANN001
        with self.connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def _execute_returning(self, query: str, params: tuple = ()) -> sqlite3.Cursor:  # noqa: ANN001
        with self.connection() as conn:
            curseur = conn.execute(query, params)
            conn.commit()
            return curseur

    def get_user_by_id(self, user_id: int) -> User | None:
        ligne = self._fetch_one('SELECT * FROM users WHERE id = ?', (user_id,))
        if not ligne:
            return None
        return User(
            id=ligne['id'],
            prenom=ligne['prenom'],
            email=ligne['email'],
            password=ligne['password'],
            created_at=ligne['created_at'],
        )

    def get_user_by_email(self, email: str) -> User | None:
        ligne = self._fetch_one('SELECT * FROM users WHERE email = ?', (email,))
        if not ligne:
            return None
        return User(
            id=ligne['id'],
            prenom=ligne['prenom'],
            email=ligne['email'],
            password=ligne['password'],
            created_at=ligne['created_at'],
        )

    def insert_user(self, prenom: str, email: str, password_hashed: str, created_at: str) -> User:
        with self.connection() as conn:
            curseur = conn.execute(
                'INSERT INTO users (prenom, email, password, created_at) VALUES (?, ?, ?, ?)',
                (prenom, email, password_hashed, created_at),
            )
            conn.commit()
            user_id = curseur.lastrowid
        return self.get_user_by_id(int(user_id))

    def get_event(self, event_id: int, user_id: int | None = None) -> Event | None:
        query = 'SELECT * FROM events WHERE id = ?'
        params = [event_id]
        if user_id is not None:
            query += ' AND user_id = ?'
            params.append(user_id)
        ligne = self._fetch_one(query, tuple(params))
        if not ligne:
            return None
        return Event(
            id=ligne['id'],
            nom=ligne['nom'],
            date=ligne['date'],
            ville=ligne['ville'],
            email=ligne['email'],
            statut=ligne['statut'],
            user_id=ligne['user_id'] if 'user_id' in ligne.keys() else None,
            created_at=ligne['created_at'],
        )

    def list_events_for_user(self, user_id: int) -> list[Event]:
        lignes = self._fetch_all('SELECT * FROM events WHERE user_id = ? ORDER BY date ASC', (user_id,))
        return [
            Event(
                id=ligne['id'],
                nom=ligne['nom'],
                date=ligne['date'],
                ville=ligne['ville'],
                email=ligne['email'],
                statut=ligne['statut'],
                user_id=ligne['user_id'],
                created_at=ligne['created_at'],
            )
            for ligne in lignes
        ]

    def get_events_by_dates(self, dates: set[str]) -> list[Event]:
        if not dates:
            return []
        placeholders = ','.join('?' for _ in dates)
        query = f'SELECT * FROM events WHERE date IN ({placeholders}) ORDER BY date ASC'
        lignes = self._fetch_all(query, tuple(sorted(dates)))
        return [
            Event(
                id=ligne['id'],
                nom=ligne['nom'],
                date=ligne['date'],
                ville=ligne['ville'],
                email=ligne['email'],
                statut=ligne['statut'],
                user_id=ligne['user_id'],
                created_at=ligne['created_at'],
            )
            for ligne in lignes
        ]

    def list_events_for_user_on_dates(self, user_id: int, dates: set[str]) -> list[Event]:
        if not dates:
            return []
        placeholders = ','.join('?' for _ in dates)
        query = f'SELECT * FROM events WHERE user_id = ? AND date IN ({placeholders}) ORDER BY date ASC'
        lignes = self._fetch_all(query, tuple([user_id, *sorted(dates)]))
        return [
            Event(
                id=ligne['id'],
                nom=ligne['nom'],
                date=ligne['date'],
                ville=ligne['ville'],
                email=ligne['email'],
                statut=ligne['statut'],
                user_id=ligne['user_id'],
                created_at=ligne['created_at'],
            )
            for ligne in lignes
        ]

    def has_notification_been_sent(self, event_id: int, kind: str) -> bool:
        ligne = self._fetch_one(
            'SELECT 1 FROM event_notification_log WHERE event_id = ? AND kind = ?',
            (event_id, kind),
        )
        return ligne is not None

    def mark_notification_sent(self, event_id: int, kind: str, sent_at: str) -> None:
        self._execute(
            '''
            INSERT INTO event_notification_log (event_id, kind, sent_at)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id, kind) DO UPDATE SET
                sent_at = excluded.sent_at
            ''',
            (event_id, kind, sent_at),
        )

    def insert_event(self, event: Event) -> Event:
        created_at = event.created_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self.connection() as conn:
            curseur = conn.execute(
                'INSERT INTO events (nom, date, ville, email, statut, user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (event.nom, event.date, event.ville, event.email, event.statut, event.user_id, created_at),
            )
            conn.commit()
            event_id = curseur.lastrowid
        saved = self.get_event(event_id)
        return saved

    def update_event(self, event: Event) -> int:
        with self.connection() as conn:
            curseur = conn.execute(
                'UPDATE events SET nom = ?, date = ?, ville = ?, email = ?, statut = ? WHERE id = ?',
                (event.nom, event.date, event.ville, event.email, event.statut, event.id),
            )
            conn.commit()
            return curseur.rowcount

    def update_event_for_user(self, event_id: int, user_id: int, fields: dict[str, str]) -> int:
        colonnes: list[str] = []
        params: list[str] = []
        for cle, valeur in fields.items():
            colonnes.append(f'{cle} = ?')
            params.append(valeur)
        if not colonnes:
            return 0
        params.extend([event_id, user_id])
        with self.connection() as conn:
            curseur = conn.execute(
                f'UPDATE events SET {", ".join(colonnes)} WHERE id = ? AND user_id = ?',
                tuple(params),
            )
            conn.commit()
            return curseur.rowcount

    def delete_event_for_user(self, event_id: int, user_id: int) -> int:
        with self.connection() as conn:
            curseur = conn.execute('DELETE FROM events WHERE id = ? AND user_id = ?', (event_id, user_id))
            conn.commit()
            return curseur.rowcount

    def get_city_cache(self, city_key: str) -> tuple[float, float] | None:
        ligne = self._fetch_one('SELECT latitude, longitude FROM city_cache WHERE ville_key = ?', (city_key,))
        if not ligne:
            return None
        return float(ligne['latitude']), float(ligne['longitude'])

    def save_city_cache(self, city_key: str, latitude: float, longitude: float) -> None:
        now = datetime.utcnow().isoformat()
        self._execute(
            '''
            INSERT INTO city_cache (ville_key, latitude, longitude, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ville_key) DO UPDATE SET
              latitude=excluded.latitude,
              longitude=excluded.longitude,
              updated_at=excluded.updated_at
            ''',
            (city_key, latitude, longitude, now),
        )

    def get_cached_weather(self, city_key: str, event_date: str) -> WeatherSnapshot | None:
        ligne = self._fetch_one(
            'SELECT weathercode, pluie, vent, icone, icone_label, alerte, fetched_at, expires_at '
            'FROM meteo_cache WHERE ville_key = ? AND event_date = ?',
            (city_key, event_date),
        )
        if not ligne:
            return None
        try:
            if datetime.fromisoformat(ligne['expires_at']) <= datetime.utcnow():
                return None
        except Exception:
            return None

        return WeatherSnapshot(
            weathercode=ligne['weathercode'],
            pluie=float(ligne['pluie'] or 0),
            vent=float(ligne['vent'] or 0),
            icone=normalize_weather_icon(ligne['icone']),
            icone_label=ligne['icone_label'],
            alerte=bool(ligne['alerte']),
            cached=True,
        )

    def get_cached_weather_range(
        self, city_key: str, date_debut: str, date_fin: str, *, include_expired: bool = False
    ) -> dict[str, WeatherSnapshot]:
        lignes = self._fetch_all(
            'SELECT event_date, weathercode, pluie, vent, icone, icone_label, alerte, fetched_at, expires_at '
            'FROM meteo_cache WHERE ville_key = ? AND event_date BETWEEN ? AND ?',
            (city_key, date_debut, date_fin),
        )
        result: dict[str, WeatherSnapshot] = {}
        maintenant = datetime.utcnow()

        try:
            for ligne in lignes:
                if not include_expired and datetime.fromisoformat(ligne['expires_at']) <= maintenant:
                    continue
                result[ligne['event_date']] = WeatherSnapshot(
                    weathercode=ligne['weathercode'],
                    pluie=float(ligne['pluie'] or 0),
                    vent=float(ligne['vent'] or 0),
                    icone=normalize_weather_icon(ligne['icone']),
                    icone_label=ligne['icone_label'],
                    alerte=bool(ligne['alerte']),
                    cached=True,
                )
        except Exception:
            return {}
        return result

    def save_weather_cache(self, city_key: str, event_date: str, meteo: WeatherSnapshot, duration_hours: float) -> None:
        icone = normalize_weather_icon(meteo.icone)
        maintenant = datetime.utcnow()
        expiration = maintenant + timedelta(hours=duration_hours)
        self._execute(
            '''
            INSERT INTO meteo_cache
            (ville_key, event_date, weathercode, pluie, vent, icone, icone_label, alerte, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ville_key, event_date) DO UPDATE SET
                weathercode = excluded.weathercode,
                pluie = excluded.pluie,
                vent = excluded.vent,
                icone = excluded.icone,
                icone_label = excluded.icone_label,
                alerte = excluded.alerte,
                fetched_at = excluded.fetched_at,
                expires_at = excluded.expires_at
            ''',
            (
                city_key,
                event_date,
                meteo.weathercode,
                meteo.pluie,
                meteo.vent,
                icone,
                meteo.icone_label,
                1 if meteo.alerte else 0,
                maintenant.isoformat(),
                expiration.isoformat(),
            ),
        )
