import re
import webbrowser
from typing import List, Set, Optional

# Regex robusta para capturar URLs (http, https, links diretos e domínios comuns)
URL_REGEX = re.compile(
    r'(?:https?:\/\/|www\.)[^\s<>"\'\)]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:\/[^\s<>"\'\)]*)?',
    re.IGNORECASE
)

# Caracteres que nunca devem fazer parte do início ou fim de uma URL
TRAILING_GARBAGE = ".,;:!?)'\"*~`_#<>[]{}|\\^ \t\n\r"
LEADING_GARBAGE = "('\"*~`_#<>[]{}|\\^ \t\n\r"

class LinkHandler:
    def __init__(self):
        self.seen_links: Set[str] = set()

    def clean_single_url(self, raw_url: str) -> Optional[str]:
        """Limpa uma URL removendo formatações markdown (**, __, etc) e pontuações espúrias."""
        if not raw_url:
            return None

        url = raw_url.strip()
        
        # Remove markdown inicial e final como **, __, ```, etc repetidamente
        url = url.strip(LEADING_GARBAGE)
        url = url.rstrip(TRAILING_GARBAGE)

        # Remove asteriscos ou underscores residuais no final ou início
        url = re.sub(r'[\*\_~`]+$', '', url)
        url = re.sub(r'^[\*\_~`]+', '', url)
        url = url.rstrip(".,;:!?)'\"")

        if not url:
            return None

        # Garante o protocolo https/http
        if not url.startswith(("http://", "https://")):
            if url.startswith("www.") or ("." in url and not url.endswith(".")):
                url = "https://" + url
            else:
                return None

        return url

    def extract_links(self, text: str, entity_urls: Optional[List[str]] = None) -> List[str]:
        """
        Extrai e limpa todos os links presentes em um texto e nas entidades do Telegram.
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
            raw_matches = URL_REGEX.findall(text)
            for match in raw_matches:
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
            webbrowser.open(cleaned, new=2)  # new=2 abre em nova aba se possível
            self.seen_links.add(cleaned)
            return True
        except Exception as e:
            print(f"Erro ao abrir link {cleaned}: {e}")
            return False
