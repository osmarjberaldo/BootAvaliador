import asyncio
import os
import threading
from datetime import datetime, timezone
from typing import Callable, List, Dict, Optional, Any
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, User
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError
)

SESSION_NAME = "boot_avaliador_session"

class TelegramService:
    def __init__(self, session_path: str = SESSION_NAME):
        self.session_path = session_path
        self.client: Optional[TelegramClient] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.is_monitoring = False
        self.monitored_chat_id: Optional[int] = None
        self.phone_code_hash: Optional[str] = None
        self.phone: Optional[str] = None
        
        # Callbacks para a GUI
        self.on_log: Optional[Callable[[str, str], None]] = None # (tipo, msg)
        self.on_message_received: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_status_change: Optional[Callable[[str], None]] = None

        # Inicia a thread assíncrona
        self.ensure_thread()

    def _start_loop(self, ready_event: threading.Event):
        """Inicia um event loop isolado em uma thread separada."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        ready_event.set()
        self.loop.run_forever()

    def ensure_thread(self):
        if self.thread is None or not self.thread.is_alive() or self.loop is None:
            ready_event = threading.Event()
            self.thread = threading.Thread(target=self._start_loop, args=(ready_event,), daemon=True)
            self.thread.start()
            ready_event.wait(timeout=10)

    def run_coroutine(self, coro):
        """Executa uma coroutine no loop assíncrono da thread."""
        self.ensure_thread()
        if not self.loop or not self.loop.is_running():
            raise RuntimeError("O loop de eventos assíncronos não está em execução.")
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=45)

    def log(self, level: str, message: str):
        if self.on_log:
            self.on_log(level, message)
        else:
            print(f"[{level.upper()}] {message}")

    async def _init_client(self, api_id: int, api_hash: str):
        if self.client is None or not self.client.is_connected():
            self.client = TelegramClient(self.session_path, api_id, api_hash)
            await self.client.connect()

    def check_connection(self, api_id: str, api_hash: str) -> Dict[str, Any]:
        """
        Verifica se o cliente já está autorizado.
        Retorna dicionário com status e dados do usuário se logado.
        """
        async def _check():
            try:
                await self._init_client(int(api_id), api_hash)
                is_auth = await self.client.is_user_authorized()
                if is_auth:
                    me = await self.client.get_me()
                    return {
                        "authorized": True,
                        "user": {
                            "id": me.id,
                            "first_name": me.first_name or "",
                            "last_name": me.last_name or "",
                            "username": me.username or "",
                            "phone": me.phone or ""
                        }
                    }
                else:
                    return {"authorized": False, "user": None}
            except Exception as e:
                return {"authorized": False, "error": str(e)}

        return self.run_coroutine(_check())

    def request_code(self, api_id: str, api_hash: str, phone: str) -> Dict[str, Any]:
        """
        Envia o código de confirmação para o Telegram/SMS do usuário.
        """
        async def _send_code():
            try:
                await self._init_client(int(api_id), api_hash)
                self.phone = phone
                sent = await self.client.send_code_request(phone)
                self.phone_code_hash = sent.phone_code_hash
                return {"success": True, "message": "Código enviado com sucesso!"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return self.run_coroutine(_send_code())

    def sign_in_with_code(self, code: str, password: Optional[str] = None) -> Dict[str, Any]:
        """
        Finaliza o login com o código digitado e senha 2FA se necessário.
        """
        async def _sign_in():
            try:
                if not self.client or not self.phone or not self.phone_code_hash:
                    return {"success": False, "error": "Requisição de código não encontrada."}

                try:
                    await self.client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash)
                except SessionPasswordNeededError:
                    if not password:
                        return {"success": False, "requires_2fa": True, "message": "Conta possui Verificação em Duas Etapas (2FA)."}
                    await self.client.sign_in(password=password)

                me = await self.client.get_me()
                return {
                    "success": True,
                    "user": {
                        "id": me.id,
                        "first_name": me.first_name or "",
                        "last_name": me.last_name or "",
                        "username": me.username or "",
                        "phone": me.phone or ""
                    }
                }
            except PhoneCodeInvalidError:
                return {"success": False, "error": "Código de verificação inválido."}
            except PhoneCodeExpiredError:
                return {"success": False, "error": "Código expirou. Solicite um novo."}
            except PasswordHashInvalidError:
                return {"success": False, "error": "Senha 2FA incorreta."}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return self.run_coroutine(_sign_in())

    def get_dialogs_list(self) -> List[Dict[str, Any]]:
        """
        Obtém lista de canais, grupos e contatos/conversas do usuário.
        """
        async def _get():
            try:
                if not self.client or not await self.client.is_user_authorized():
                    return []

                dialogs = []
                async for dialog in self.client.iter_dialogs(limit=100):
                    entity = dialog.entity
                    is_group_or_channel = isinstance(entity, (Chat, Channel))
                    is_user = isinstance(entity, User)
                    
                    dialog_type = "Privado"
                    if isinstance(entity, Channel):
                        dialog_type = "Canal" if entity.broadcast else "Supergrupo"
                    elif isinstance(entity, Chat):
                        dialog_type = "Grupo"
                    elif is_user:
                        dialog_type = "Contato"

                    dialogs.append({
                        "id": dialog.id,
                        "title": dialog.name or "Sem Nome",
                        "type": dialog_type,
                        "unread_count": dialog.unread_count,
                        "is_group": is_group_or_channel,
                        "is_user": is_user
                    })
                return dialogs
            except Exception as e:
                self.log("erro", f"Erro ao buscar diálogos: {e}")
                return []

        return self.run_coroutine(_get())

    def send_screenshot(self, target_chat_id: int, file_path: str, caption: str = "") -> Dict[str, Any]:
        """
        Envia a imagem de comprovante do print para um contato/chat do Telegram.
        """
        async def _send():
            try:
                if not self.client or not await self.client.is_user_authorized():
                    return {"success": False, "error": "Cliente Telegram não autenticado."}

                if not os.path.exists(file_path):
                    return {"success": False, "error": f"Arquivo de print não encontrado: {file_path}"}

                await self.client.send_file(
                    target_chat_id,
                    file_path,
                    caption=caption
                )
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return self.run_coroutine(_send())

    def start_monitoring(self, chat_id: int, process_today_history: bool = True):
        """
        Inicia o monitoramento de mensagens no chat especificado.
        """
        self.monitored_chat_id = chat_id
        self.is_monitoring = True

        async def _monitor():
            try:
                # Remove handlers anteriores para evitar duplicações
                self.client.remove_event_handler(self._on_new_message)
                
                # Registra o listener de novas mensagens
                self.client.add_event_handler(
                    self._on_new_message,
                    events.NewMessage(chats=chat_id)
                )

                self.log("info", f"Monitoramento iniciado para o grupo ID: {chat_id}")

                # Se solicitado, processa as mensagens já enviadas no dia de hoje
                if process_today_history:
                    await self._fetch_today_messages(chat_id)

            except Exception as e:
                self.log("erro", f"Erro ao configurar monitoramento: {e}")

        self.run_coroutine(_monitor())

    async def _fetch_today_messages(self, chat_id: int):
        """
        Busca mensagens enviadas hoje no grupo selecionado.
        """
        try:
            today_date = datetime.now().date()
            self.log("info", f"Buscando histórico do dia de hoje ({today_date.strftime('%d/%m/%Y')})...")
            
            count = 0
            # Itera do mais recente ao mais antigo até sair do dia de hoje
            async for message in self.client.iter_messages(chat_id, limit=200):
                if not message.date:
                    continue

                msg_local_date = message.date.astimezone().date()
                if msg_local_date < today_date:
                    # Como iter_messages vem do mais recente para o mais antigo, ao encontrar uma data anterior a hoje podemos parar
                    break

                if msg_local_date == today_date and message.text:
                    count += 1
                    self._handle_incoming_message(message, is_history=True)

            self.log("sucesso", f"Histórico de hoje processado: {count} mensagem(ns) encontrada(s).")
        except Exception as e:
            self.log("erro", f"Erro ao buscar histórico do dia: {e}")

    async def _on_new_message(self, event):
        """Handler assíncrono para novas mensagens recebidas em tempo real."""
        if not self.is_monitoring:
            return

        message = event.message
        if not message or not message.text:
            return

        # Verifica estritamente se a mensagem é do dia de hoje
        today_date = datetime.now().date()
        msg_date = message.date.astimezone().date() if message.date else today_date

        if msg_date != today_date:
            return

        self._handle_incoming_message(message, is_history=False)

    def _handle_incoming_message(self, message: Any, is_history: bool = False):
        """Processa a mensagem e encaminha para a interface via callback."""
        msg_time_str = message.date.astimezone().strftime("%H:%M:%S") if message.date else datetime.now().strftime("%H:%M:%S")
        
        sender_title = "Desconhecido"
        try:
            if message.sender:
                if hasattr(message.sender, 'first_name') and message.sender.first_name:
                    sender_title = message.sender.first_name
                    if hasattr(message.sender, 'last_name') and message.sender.last_name:
                        sender_title += f" {message.sender.last_name}"
                elif hasattr(message.sender, 'title') and message.sender.title:
                    sender_title = message.sender.title
        except Exception:
            pass

        # Extrai URLs de entidades nativas do Telegram se disponíveis
        entity_urls = []
        if getattr(message, 'entities', None):
            try:
                from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
                for ent in message.entities:
                    if isinstance(ent, MessageEntityTextUrl) and getattr(ent, 'url', None):
                        entity_urls.append(ent.url)
                    elif isinstance(ent, MessageEntityUrl):
                        try:
                            raw = message.raw_text or message.text or ""
                            raw_encoded = raw.encode('utf-16-le')
                            extracted_u = raw_encoded[ent.offset * 2 : (ent.offset + ent.length) * 2].decode('utf-16-le')
                            if extracted_u:
                                entity_urls.append(extracted_u)
                        except Exception:
                            pass
            except Exception:
                pass

        data = {
            "id": message.id,
            "date_str": msg_time_str,
            "sender": sender_title,
            "text": message.text or getattr(message, 'raw_text', '') or "",
            "entity_urls": entity_urls,
            "is_history": is_history
        }

        if self.on_message_received:
            self.on_message_received(data)

    def stop_monitoring(self):
        """Para o monitoramento de mensagens."""
        self.is_monitoring = False
        async def _stop():
            try:
                if self.client:
                    self.client.remove_event_handler(self._on_new_message)
                self.log("aviso", "Monitoramento pausado.")
            except Exception as e:
                self.log("erro", f"Erro ao pausar monitoramento: {e}")

        self.run_coroutine(_stop())

    def disconnect(self):
        """Desconecta a sessão e limpa os recursos."""
        self.stop_monitoring()
        async def _disc():
            if self.client:
                await self.client.disconnect()
        try:
            self.run_coroutine(_disc())
        except Exception:
            pass
