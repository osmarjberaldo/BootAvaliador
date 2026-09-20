import os
import json
from typing import Optional, Dict, Any

CONFIG_FILE = "config.json"
LEGACY_TXT_FILE = "credenciais.txt"

def load_credentials_from_txt(file_path: str = LEGACY_TXT_FILE) -> Dict[str, str]:
    """Lê as credenciais do formato legado .txt."""
    creds = {"api_id": "", "api_hash": "", "phone": ""}
    if not os.path.exists(file_path):
        return creds

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip().lower()
                    val = val.strip()
                    if key in creds:
                        creds[key] = val
    except Exception as e:
        print(f"Erro ao ler TXT legado: {e}")

    return creds

def load_credentials(json_path: str = CONFIG_FILE, txt_path: str = LEGACY_TXT_FILE) -> Dict[str, Any]:
    """
    Carrega as credenciais do arquivo .json.
    Se o .json não existir mas o .txt existir, migra automaticamente os dados para o novo .json.
    """
    default_config = {
        "api_id": "",
        "api_hash": "",
        "phone": "",
        "auto_open_links": False,
        "ignore_duplicates": True,
        "fetch_today_history": True,
        "last_selected_group_id": None,
        "target_recipient_id": None,
        "target_recipient_name": None,
        "auto_send_screenshot": True,
        "evaluated_links": {}
    }

    # 1. Se já existe config.json, lê diretamente
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_config.update(data)
                
            # Limpa links de dias anteriores automaticamente ao carregar
            cleanup_old_evaluated_links(json_path=json_path)
            
            # Recarrega o dict atualizado após limpeza
            with open(json_path, "r", encoding="utf-8") as f:
                data_cleaned = json.load(f)
                default_config.update(data_cleaned)
                
            return default_config
        except Exception as e:
            print(f"Erro ao ler {json_path}: {e}")

    # 2. Se não existe .json, mas existe o TXT legado, faz a migração
    if os.path.exists(txt_path):
        txt_creds = load_credentials_from_txt(txt_path)
        if any(txt_creds.values()):
            default_config.update(txt_creds)
            print(f"[MIGRACAO] Migrando dados de {txt_path} para {json_path}...")
            save_config(default_config, json_path=json_path)

    return default_config

def save_credentials(api_id: str, api_hash: str, phone: str, json_path: str = CONFIG_FILE) -> bool:
    """Salva apenas as credenciais de autenticação no JSON."""
    current_config = load_credentials(json_path=json_path)
    current_config["api_id"] = str(api_id).strip()
    current_config["api_hash"] = str(api_hash).strip()
    current_config["phone"] = str(phone).strip()
    return save_config(current_config, json_path=json_path)

def normalize_link_key(url: str) -> str:
    """Normaliza uma URL para ser usada como chave de busca sem variações triviais."""
    if not url:
        return ""
    u = url.strip().lower()
    u = u.rstrip("/")
    # Remove protocolos para comparação idêntica http/https
    if u.startswith("https://"):
        u = u[8:]
    elif u.startswith("http://"):
        u = u[7:]
    if u.startswith("www."):
        u = u[4:]
    return u

def is_link_evaluated(url: str, json_path: str = CONFIG_FILE) -> bool:
    """Verifica se um link já foi avaliado anteriormente."""
    key = normalize_link_key(url)
    if not key:
        return False
    
    cfg = load_credentials(json_path=json_path)
    evaluated = cfg.get("evaluated_links", {})
    
    # Se evaluated for dicionário ou lista
    if isinstance(evaluated, dict):
        if key in evaluated or url in evaluated:
            return True
        for k in evaluated.keys():
            if normalize_link_key(k) == key:
                return True
    elif isinstance(evaluated, list):
        for item in evaluated:
            item_url = item if isinstance(item, str) else item.get("url", "")
            if normalize_link_key(item_url) == key:
                return True
    return False

def get_evaluated_link_info(url: str, json_path: str = CONFIG_FILE) -> Optional[Dict[str, Any]]:
    """Retorna os dados salvos de uma avaliação já realizada (data, print, status)."""
    key = normalize_link_key(url)
    if not key:
        return None
    
    cfg = load_credentials(json_path=json_path)
    evaluated = cfg.get("evaluated_links", {})
    if isinstance(evaluated, dict):
        for k, v in evaluated.items():
            if normalize_link_key(k) == key:
                return v if isinstance(v, dict) else {"url": k}
    return None

def save_evaluated_link(url: str, screenshot_path: str = "", status: str = "avaliado", json_path: str = CONFIG_FILE) -> bool:
    """Registra permanentemente um link como avaliado com seu comprovante de print."""
    if not url:
        return False
    
    cfg = load_credentials(json_path=json_path)
    if "evaluated_links" not in cfg or not isinstance(cfg["evaluated_links"], dict):
        cfg["evaluated_links"] = {}
    
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    key = normalize_link_key(url)

    cfg["evaluated_links"][key] = {
        "url": url,
        "date": now_str,
        "screenshot_path": screenshot_path,
        "status": status
    }
    return save_config(cfg, json_path=json_path)

def cleanup_prints_folder(prints_dir: str = "prints") -> int:
    """
    Remove todos os arquivos de imagem (.png, .jpg, .jpeg) da pasta de prints.
    Retorna o total de arquivos deletados.
    """
    if not os.path.exists(prints_dir):
        return 0

    deleted_count = 0
    valid_exts = {".png", ".jpg", ".jpeg"}
    try:
        for fname in os.listdir(prints_dir):
            ext = os.path.splitext(fname)[1].lower()
            if ext in valid_exts:
                fpath = os.path.join(prints_dir, fname)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                        deleted_count += 1
                except Exception:
                    pass
    except Exception as e:
        print(f"Erro ao limpar pasta de prints ({prints_dir}): {e}")

    return deleted_count

def cleanup_old_evaluated_links(json_path: str = CONFIG_FILE, reference_date: Optional[str] = None, prints_dir: str = "prints") -> int:
    """
    Remove do evaluated_links todos os links de dias anteriores ao dia atual (YYYY-MM-DD).
    Remove também os arquivos de print associados a esses links antigos.
    Retorna a quantidade de itens removidos.
    """
    if not os.path.exists(json_path):
        return 0

    import datetime
    today_prefix = reference_date or datetime.datetime.now().strftime("%Y-%m-%d")
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return 0

    evaluated = cfg.get("evaluated_links", {})
    if not isinstance(evaluated, dict) or not evaluated:
        return 0

    keys_to_remove = []
    for key, data in evaluated.items():
        if isinstance(data, dict):
            item_date = str(data.get("date", "")).strip()
            # Se a data não for do dia atual (ex: 2026-09-20 vs 2026-09-21)
            if not item_date.startswith(today_prefix):
                keys_to_remove.append(key)
                # Remove o print do disco se existir
                sp = data.get("screenshot_path", "")
                if sp and os.path.exists(sp):
                    try:
                        os.remove(sp)
                    except Exception:
                        pass
        else:
            keys_to_remove.append(key)

    if keys_to_remove:
        for k in keys_to_remove:
            evaluated.pop(k, None)
        cfg["evaluated_links"] = evaluated
        save_config(cfg, json_path=json_path)

    return len(keys_to_remove)

def clear_all_evaluated_links(json_path: str = CONFIG_FILE, delete_prints: bool = True, prints_dir: str = "prints") -> bool:
    """
    Limpa completamente todos os dados de links avaliados do config.json
    e remove todos os prints da pasta prints/ para não acumular arquivos no disco.
    """
    try:
        cfg = load_credentials(json_path=json_path)
        cfg["evaluated_links"] = {}
        saved = save_config(cfg, json_path=json_path)

        if delete_prints:
            cleanup_prints_folder(prints_dir=prints_dir)

        return saved
    except Exception as e:
        print(f"Erro ao limpar evaluated_links e prints: {e}")
        return False

def check_and_run_nightly_cleanup(json_path: str = CONFIG_FILE, prints_dir: str = "prints", target_hour: int = 21) -> Dict[str, Any]:
    """
    Verifica se o horário atual é igual ou posterior às 21:00.
    Se for, executa a limpeza geral de prints e histórico do dia caso ainda não tenha sido executada hoje.
    """
    import datetime
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # Apenas executa se for a partir das 21h (ex: 21:00 até 23:59)
    if now.hour < target_hour:
        return {"cleaned": False, "reason": "before_target_hour"}

    cfg = load_credentials(json_path=json_path)
    last_cleanup = cfg.get("last_nightly_cleanup", "")

    # Se já foi feita a limpeza das 21h hoje, não repete
    if last_cleanup == today_str:
        return {"cleaned": False, "reason": "already_cleaned_today"}

    # Executa a limpeza completa
    prints_deleted = cleanup_prints_folder(prints_dir=prints_dir)
    evaluated_count = len(cfg.get("evaluated_links", {}))
    cfg["evaluated_links"] = {}
    cfg["last_nightly_cleanup"] = today_str
    save_config(cfg, json_path=json_path)

    return {
        "cleaned": True,
        "prints_deleted": prints_deleted,
        "evaluated_links_cleared": evaluated_count,
        "date": today_str
    }

def save_config(config_data: Dict[str, Any], json_path: str = CONFIG_FILE) -> bool:
    """Salva todo o dicionário de configurações no arquivo JSON formatado."""
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erro ao salvar configurações em {json_path}: {e}")
        return False
