import json
import subprocess
import urllib.request


def read_json_http(url: str, *, delai: int = 8, entetes: dict[str, str] | None = None):
    try:
        requete = urllib.request.Request(url, headers=entetes or {})
        with urllib.request.urlopen(requete, timeout=delai) as reponse:
            if getattr(reponse, 'status', 200) != 200:
                raise RuntimeError(f'HTTP {reponse.status}')
            return json.loads(reponse.read() or b'{}')
    except Exception as erreur_urllib:
        cmd = ['curl', '-fsSL', '--max-time', str(delai)]
        for cle, valeur in (entetes or {}).items():
            cmd.extend(['-H', f'{cle}: {valeur}'])
        cmd.append(url)
        try:
            resultat = subprocess.run(cmd, capture_output=True, text=True, timeout=delai + 2, check=True)
            return json.loads(resultat.stdout or '{}')
        except Exception as erreur_curl:
            raise RuntimeError(f'HTTP JSON indisponible (urllib={erreur_urllib}; curl={erreur_curl})') from erreur_curl
