import re
import urllib.parse
import webbrowser
from typing import List, Set, Optional

# TLDs comuns e válidos na web
VALID_TLDS = {
    "com", "br", "gl", "app", "org", "net", "io", "me", "co", "link",
    "site", "info", "gov", "edu", "dev", "online", "store", "xyz", "cc",
    "tv", "ai", "pt", "es", "us", "uk", "fr", "de", "it", "to", "gg"
}

# Prefixos conhecidos diretos de mapas e mensageiros
KNOWN_HOST_PREFIXES = (
    "maps.app.goo.gl",
    "goo.gl",
    "maps.google.",
    "google.com/maps",
    "google.com.br/maps",
    "t.me",
    "telegram.me",
    "wa.me"
)

# Regex precisa para URLs explícitas (http/https/www) ou domínios conhecidos
EXPLICIT_URL_REGEX = re.compile(
    r'(?:https?:\/\/|www\.)[^\s<>"\'\(\)]+',
    re.IGNORECASE
)

# Regex para links diretos sem protocolo (ex: maps.app.goo.gl/xxx, t.me/xxx)
DIRECT_MAPS_REGEX = re.compile(
    r'\b(?:maps\.app\.goo\.gl|goo\.gl\/maps|maps\.google\.[a-z.]+|google\.com(?:\.[a-z]{2})?\/maps|t\.me)\/[^\s<>"\'\(\)]+',
    re.IGNORECASE
)

# Caracteres e pontuações a serem removidos das extremidades
GARBAGE_CHARS = ".,;:!?)'\"*~`_#<>[]{}|\\^ \t\n\r\u200b\ufeff\xa0"

def strip_emojis_and_symbols(text: str) -> str:
    """Remove emojis e símbolos especiais de pontuação de uma string."""
    if not text:
        return ""
    # Remove caracteres fora do range ASCII comum de URLs
    return re.sub(r'[^\x21-\x7E]', '', text)

class LinkHandler:
    def __init__(self):
        self.seen_links: Set[str] = set()

    def clean_single_url(self, raw_url: str) -> Optional[str]:
        """
        Limpa e valida estritamente uma URL.
        Rejeita números decimais (ex: 9.30h), pontuações de frases (ex: concluído.Por) e emojis.
        """
        if not raw_url:
            return None

        url = raw_url.strip()
        url = url.strip(GARBAGE_CHARS)
        
        # Remove emojis e caracteres não-ASCII
        url = strip_emojis_and_symbols(url)
        url = url.strip(GARBAGE_CHARS)

        if not url or len(url) < 4:
            return None

        # Rejeita números com ponto/vírgula ou horários (ex: 9.30h, 10.50, 10.000)
        if re.match(r'^\d+[\.\,]\d+[a-zA-Z]?$', url):
            return None

        # Garante o protocolo https/http
        has_protocol = url.startswith(("http://", "https://"))
        if not has_protocol:
            if url.startswith("www.") or any(url.lower().startswith(p) for p in KNOWN_HOST_PREFIXES):
                url = "https://" + url
            else:
                # Se não tem protocolo nem prefixo conhecido, exige TLD válido e barra de caminho
                if "/" in url:
                    host_part = url.split("/")[0].lower()
                    tld = host_part.split(".")[-1] if "." in host_part else ""
                    if tld in VALID_TLDS and not host_part.isdigit():
                        url = "https://" + url
                    else:
                        return None
                else:
                    return None

        # Validação do Hostname após normalização
        try:
            parsed = urllib.parse.urlparse(url)
            host = (parsed.hostname or "").lower()
            if not host or "." not in host:
                return None

            tld = host.split(".")[-1]
            if tld not in VALID_TLDS and not host.endswith((".google", ".gl", ".app")):
                return None

            # Rejeita hosts que são apenas números ou texto de frase
            if host.replace(".", "").isdigit():
                return None

        except Exception:
            return None

        return url

    def is_maps_link(self, url: str) -> bool:
        """Verifica se a URL é especificamente um link do Google Maps."""
        if not url:
            return False
        u = url.lower()
        return any(p in u for p in ("maps.app.goo.gl", "goo.gl/maps", "google.com/maps", "google.com.br/maps", "maps.google"))

    def extract_links(self, text: str, entity_urls: Optional[List[str]] = None) -> List[str]:
        """
        Extrai e limpa todos os links reais presentes em um texto e nas entidades do Telegram.
        Ignora falsos positivos de emojis, horários (9.30h) e pontuação de fim de frase.
        """
        cleaned_links: List[str] = []

        # 1. Adiciona links vindos de entidades nativas do Telegram se houver
        if entity_urls:
            for eu in entity_urls:
                cleaned = self.clean_single_url(eu)
                if cleaned and cleaned not in cleaned_links:
                    cleaned_links.append(cleaned)

        # 2. Extrai links por regex no texto da mensagem
        if text:
            # Captura URLs explícitas e links diretos do Maps
            matches = EXPLICIT_URL_REGEX.findall(text) + DIRECT_MAPS_REGEX.findall(text)
            for match in matches:
                cleaned = self.clean_single_url(match)
                if cleaned and cleaned not in cleaned_links:
                    cleaned_links.append(cleaned)

        return cleaned_links

    def open_link(self, url: str, check_duplicate: bool = False) -> bool:
        """
        Abre o link no navegador padrão.
        """
        cleaned = self.clean_single_url(url)
        if not cleaned:
            return False

        if check_duplicate and cleaned in self.seen_links:
            return False

        try:
            webbrowser.open(cleaned, new=2)
            self.seen_links.add(cleaned)
            return True
        except Exception as e:
            print(f"Erro ao abrir link {cleaned}: {e}")
            return False

