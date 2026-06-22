from app.domain import User
from app.infrastructure.database import DatabaseService


class UserSessionService:
    def current_user_id(self, session_data: dict) -> int | None:
        return session_data.get('user_id')

    def current_user(self, session_data: dict, db_service: DatabaseService) -> User | None:
        identifiant = self.current_user_id(session_data)
        if not identifiant:
            return None
        return db_service.get_user_by_id(int(identifiant))

    @staticmethod
    def safe_return_url(raw_url: str | None) -> str:
        if raw_url and raw_url.startswith('/') and not raw_url.startswith('//'):
            return raw_url
        return '/'

    @staticmethod
    def save_pending_event(session_data: dict, form_data: dict[str, str], next_url: str) -> None:
        session_data['pending_event'] = {
            'nom': form_data.get('nom', '').strip(),
            'date': form_data.get('date', '').strip(),
            'ville': form_data.get('ville', '').strip(),
        }
        session_data['pending_next'] = next_url

    @staticmethod
    def pop_pending_next(session_data: dict) -> str:
        return session_data.pop('pending_next', '')
