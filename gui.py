import os
import sys
import threading
import queue
import time
from datetime import datetime
from typing import Optional, Dict, List, Any
import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageTk

from config_manager import (
    load_credentials, 
    save_credentials, 
    save_config, 
    CONFIG_FILE,
    is_link_evaluated,
    save_evaluated_link,
    get_evaluated_link_info,
    clear_all_evaluated_links,
    cleanup_old_evaluated_links,
    cleanup_prints_folder,
    check_and_run_nightly_cleanup
)
from telegram_service import TelegramService
from link_handler import LinkHandler
from splash import SplashScreen
from maps_evaluator import GoogleMapsEvaluator

import ctypes

# Registra o AppUserModelID para o Windows exibir o ícone customizado na barra de tarefas em vez do ícone do Python
try:
    myappid = "bootavaliador.telegram.monitor.1.0"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def set_app_icon(window):
    """Aplica o logo.ico e logo.png como ícone da janela e barra de tarefas do Windows."""
    try:
        ico_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "logo.ico"))
        png_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "logo.png"))
        
        if os.path.exists(ico_path):
            window.iconbitmap(ico_path)
            # Também define iconphoto para máxima compatibilidade com a barra de tarefas
            if os.path.exists(png_path):
                img = Image.open(png_path)
                photo = ImageTk.PhotoImage(img)
                window.iconphoto(False, photo)
                window._icon_photo_ref = photo  # Mantém referência para evitar coleta de lixo
        elif os.path.exists(png_path):
            img = Image.open(png_path)
            photo = ImageTk.PhotoImage(img)
            window.iconphoto(False, photo)
            window._icon_photo_ref = photo
    except Exception as e:
        pass

def center_window(window, width: int, height: int, parent=None):
    """Centraliza a janela ou modal na tela do usuário dinamicamente."""
    window.update_idletasks()
    
    # Se fornecido parent e estiver visível, centraliza relativo à janela pai, senão no monitor
    if parent is not None and parent.winfo_exists() and parent.winfo_viewable():
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = max(0, parent_x + (parent_w - width) // 2)
        y = max(0, parent_y + (parent_h - height) // 2)
    else:
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)

    window.geometry(f"{width}x{height}+{x}+{y}")

class BootAvaliadorApp(ctk.CTk):
    def __init__(self, show_splash: bool = True):
        super().__init__()

        self.title("Boot Avaliador - Telegram Link Monitor")
        center_window(self, 1100, 720)
        self.minsize(950, 600)
        set_app_icon(self)

        # Serviços
        self.telegram = TelegramService()
        self.link_handler = LinkHandler()
        self.evaluator = GoogleMapsEvaluator()
        self.dialogs_cache: List[Dict[str, Any]] = []
        self.links_captured: List[Dict[str, str]] = []

        # Fila de Avaliação Sequencial (Processa 1 por vez para não sobrecarregar)
        self.eval_queue = queue.Queue()
        self.eval_worker_thread = threading.Thread(target=self._eval_queue_worker, daemon=True)
        self.eval_worker_thread.start()

        # Estado
        self.is_connected = False
        self.user_data: Optional[Dict[str, Any]] = None

        # Callbacks do serviço Telegram
        self.telegram.on_log = self._on_telegram_log
        self.telegram.on_message_received = self._on_telegram_message

        # Layout Principal
        self._create_widgets()

        # Fluxo de inicialização com SplashScreen
        if show_splash:
            self.withdraw()
            self.splash = SplashScreen(master=self, on_complete=self._on_splash_done)
        else:
            self.after(300, self._auto_connect)

    def _on_splash_done(self):
        """Chamado quando a Splash Screen conclui o carregamento."""
        self.deiconify()
        self.lift()
        self.focus_force()
        self.after(200, self._auto_connect)

    def _create_widgets(self):
        # Grid Principal: 1 linha com sidebar à esquerda e conteúdo à direita
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # SIDEBAR ESQUERDA (ROLÁVEL E COMPACTA)
        # ==========================================
        self.sidebar_frame = ctk.CTkScrollableFrame(
            self, 
            width=330, 
            corner_radius=0,
            scrollbar_button_color="#3a7ebf",
            scrollbar_button_hover_color="#2b5f91"
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # Logo do App
        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path)
                self.sidebar_logo_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(75, 75))
                self.lbl_sidebar_logo = ctk.CTkLabel(self.sidebar_frame, image=self.sidebar_logo_img, text="")
                self.lbl_sidebar_logo.pack(padx=15, pady=(10, 2))
            except Exception:
                pass

        # Título do App
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Boot Avaliador", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.logo_label.pack(padx=15, pady=(2, 2))

        self.subtitle_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Monitoramento de Links do Telegram",
            font=ctk.CTkFont(size=11),
            text_color="gray70"
        )
        self.subtitle_label.pack(padx=15, pady=(0, 8))

        # Card de Status da Conta
        self.account_card = ctk.CTkFrame(self.sidebar_frame, fg_color=("gray85", "gray17"), corner_radius=8)
        self.account_card.pack(fill="x", padx=10, pady=3)

        self.status_badge = ctk.CTkLabel(
            self.account_card,
            text="🔴 Desconectado",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ff5555"
        )
        self.status_badge.pack(padx=8, pady=(6, 2))

        self.user_info_label = ctk.CTkLabel(
            self.account_card,
            text="Nenhuma conta conectada",
            font=ctk.CTkFont(size=11),
            text_color="gray70"
        )
        self.user_info_label.pack(padx=8, pady=(0, 6))

        self.btn_manage_auth = ctk.CTkButton(
            self.sidebar_frame,
            text="🔑 Configurar / Conectar Conta",
            command=self._open_credentials_modal,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#3a7ebf",
            hover_color="#2b5f91"
        )
        self.btn_manage_auth.pack(fill="x", padx=10, pady=(6, 8))

        # Divisor
        self.sep = ctk.CTkFrame(self.sidebar_frame, height=2, fg_color="gray25")
        self.sep.pack(fill="x", padx=10, pady=6)

        # Seção de Grupo
        self.lbl_group = ctk.CTkLabel(
            self.sidebar_frame,
            text="Selecionar Grupo / Canal:",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        self.lbl_group.pack(fill="x", padx=10, pady=(2, 2))

        # Campo de busca em tempo real
        self.entry_search_group = ctk.CTkEntry(
            self.sidebar_frame,
            placeholder_text="🔍 Filtrar grupo por nome...",
            height=26,
            font=ctk.CTkFont(size=11)
        )
        self.entry_search_group.pack(fill="x", padx=10, pady=(2, 3))
        self.entry_search_group.bind("<KeyRelease>", self._filter_dialogs)

        # Card que mostra o grupo atualmente selecionado
        self.card_selected_group = ctk.CTkFrame(self.sidebar_frame, fg_color=("gray80", "gray22"), corner_radius=6)
        self.card_selected_group.pack(fill="x", padx=10, pady=(0, 3))

        self.lbl_selected_group = ctk.CTkLabel(
            self.card_selected_group,
            text="Nenhum grupo selecionado",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#4da6ff",
            wraplength=270,
            justify="center"
        )
        self.lbl_selected_group.pack(padx=6, pady=4)

        # Lista rolável compacta de grupos
        self.scroll_groups = ctk.CTkScrollableFrame(
            self.sidebar_frame, 
            height=110, 
            fg_color=("gray90", "gray14"),
            scrollbar_button_color="#3a7ebf",
            scrollbar_button_hover_color="#2b5f91"
        )
        self.scroll_groups.pack(fill="x", padx=10, pady=(0, 4))

        self.selected_chat_id: Optional[int] = None
        self.group_buttons: List[ctk.CTkButton] = []

        self.btn_refresh_groups = ctk.CTkButton(
            self.sidebar_frame,
            text="🔄 Atualizar Lista de Grupos/Contatos",
            command=self._refresh_dialogs,
            height=24,
            fg_color="transparent",
            border_width=1,
            font=ctk.CTkFont(size=11),
            text_color=("gray10", "gray90")
        )
        self.btn_refresh_groups.pack(fill="x", padx=10, pady=(0, 6))

        # Divisor Destinatário
        self.sep_recip = ctk.CTkFrame(self.sidebar_frame, height=2, fg_color="gray25")
        self.sep_recip.pack(fill="x", padx=10, pady=4)

        # Seção de Destinatário para Envio de Print
        self.lbl_recipient = ctk.CTkLabel(
            self.sidebar_frame,
            text="📤 Enviar Print para (Contato/Chat):",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        self.lbl_recipient.pack(fill="x", padx=10, pady=(2, 2))

        # Campo de busca de contato
        self.entry_search_recipient = ctk.CTkEntry(
            self.sidebar_frame,
            placeholder_text="🔍 Filtrar contato/chat...",
            height=26,
            font=ctk.CTkFont(size=11)
        )
        self.entry_search_recipient.pack(fill="x", padx=10, pady=(2, 3))
        self.entry_search_recipient.bind("<KeyRelease>", self._filter_recipients)

        # Card que mostra o contato selecionado para envio
        self.card_selected_recipient = ctk.CTkFrame(self.sidebar_frame, fg_color=("gray80", "gray22"), corner_radius=6)
        self.card_selected_recipient.pack(fill="x", padx=10, pady=(0, 3))

        self.lbl_selected_recipient = ctk.CTkLabel(
            self.card_selected_recipient,
            text="Nenhum contato selecionado",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray60",
            wraplength=270,
            justify="center"
        )
        self.lbl_selected_recipient.pack(padx=6, pady=4)

        # Lista rolável compacta de contatos/conversas
        self.scroll_recipients = ctk.CTkScrollableFrame(
            self.sidebar_frame, 
            height=95, 
            fg_color=("gray90", "gray14"),
            scrollbar_button_color="#3a7ebf",
            scrollbar_button_hover_color="#2b5f91"
        )
        self.scroll_recipients.pack(fill="x", padx=10, pady=(0, 6))

        self.selected_recipient_id: Optional[int] = None
        self.selected_recipient_name: Optional[str] = None
        self.recipient_buttons: List[ctk.CTkButton] = []

        # Divisor
        self.sep2 = ctk.CTkFrame(self.sidebar_frame, height=2, fg_color="gray25")
        self.sep2.pack(fill="x", padx=10, pady=4)

        # Opções de Operação
        self.lbl_options = ctk.CTkLabel(
            self.sidebar_frame,
            text="Configurações de Monitoramento:",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        self.lbl_options.pack(fill="x", padx=10, pady=(2, 2))

        self.switch_auto_evaluate = ctk.CTkSwitch(
            self.sidebar_frame,
            text="🤖 Modo IA: Avaliar 5★ e Print Auto",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#4da6ff"
        )
        self.switch_auto_evaluate.select()
        self.switch_auto_evaluate.pack(fill="x", padx=10, pady=2)

        self.switch_send_telegram = ctk.CTkSwitch(
            self.sidebar_frame,
            text="📤 Enviar print no Telegram",
            font=ctk.CTkFont(size=11)
        )
        self.switch_send_telegram.select()
        self.switch_send_telegram.pack(fill="x", padx=10, pady=2)

        self.switch_auto_open = ctk.CTkSwitch(
            self.sidebar_frame,
            text="🌐 Abrir no Navegador Padrão (Sem IA)",
            font=ctk.CTkFont(size=11)
        )
        self.switch_auto_open.deselect()  # Desmarcado por padrão para não atrapalhar o Modo IA
        self.switch_auto_open.pack(fill="x", padx=10, pady=2)

        self.switch_ignore_dup = ctk.CTkSwitch(
            self.sidebar_frame,
            text="Ignorar links repetidos",
            font=ctk.CTkFont(size=11)
        )
        self.switch_ignore_dup.select()
        self.switch_ignore_dup.pack(fill="x", padx=10, pady=2)

        self.switch_fetch_today = ctk.CTkSwitch(
            self.sidebar_frame,
            text="Carregar histórico de hoje",
            font=ctk.CTkFont(size=11)
        )
        self.switch_fetch_today.select()
        self.switch_fetch_today.pack(fill="x", padx=10, pady=2)

        # Botões de Atalho Google e Prints
        self.btn_open_chrome = ctk.CTkButton(
            self.sidebar_frame,
            text="🌐 Abrir Chrome (Login Google)",
            command=self._open_chrome_login,
            height=24,
            fg_color="transparent",
            border_width=1,
            font=ctk.CTkFont(size=10),
            text_color=("gray10", "gray90")
        )
        self.btn_open_chrome.pack(fill="x", padx=10, pady=(4, 2))

        self.btn_open_prints = ctk.CTkButton(
            self.sidebar_frame,
            text="📂 Abrir Pasta de Prints",
            command=self._open_prints_folder,
            height=24,
            fg_color="transparent",
            border_width=1,
            font=ctk.CTkFont(size=10),
            text_color=("gray10", "gray90")
        )
        self.btn_open_prints.pack(fill="x", padx=10, pady=(2, 6))

        # Botão Principal Iniciar / Pausar
        self.btn_toggle_monitor = ctk.CTkButton(
            self.sidebar_frame,
            text="▶️ Iniciar Monitoramento",
            command=self._toggle_monitoring,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#28a745",
            hover_color="#218838"
        )
        self.btn_toggle_monitor.pack(fill="x", padx=10, pady=(10, 15))

        # ==========================================
        # ÁREA PRINCIPAL DIREITA (TABS)
        # ==========================================
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.grid(row=0, column=0, sticky="nsew")

        self.tab_links = self.tabview.add("🔗 Links Detectados Hoje")
        self.tab_logs = self.tabview.add("📜 Log de Mensagens em Tempo Real")

        self._setup_tab_links()
        self._setup_tab_logs()

    def _setup_tab_links(self):
        # Frame de topo com contador e botão de limpar
        top_bar = ctk.CTkFrame(self.tab_links, fg_color="transparent")
        top_bar.pack(fill="x", padx=10, pady=(5, 10))

        self.lbl_link_counter = ctk.CTkLabel(
            top_bar,
            text="Total de links encontrados hoje: 0",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.lbl_link_counter.pack(side="left")

        btn_clear_links = ctk.CTkButton(
            top_bar,
            text="🗑️ Limpar Lista",
            command=self._clear_links,
            width=100,
            height=26,
            fg_color="transparent",
            border_width=1
        )
        btn_clear_links.pack(side="right")

        # Scrollable Frame para os cards de links com barra de rolagem destacada
        self.scroll_links = ctk.CTkScrollableFrame(
            self.tab_links, 
            fg_color=("gray90", "gray14"),
            scrollbar_button_color="#3a7ebf",
            scrollbar_button_hover_color="#2b5f91"
        )
        self.scroll_links.pack(fill="both", expand=True, padx=10, pady=5)

    def _setup_tab_logs(self):
        top_bar = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        top_bar.pack(fill="x", padx=10, pady=(5, 10))

        lbl_log_title = ctk.CTkLabel(
            top_bar,
            text="Atividades e Mensagens Recebidas:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        lbl_log_title.pack(side="left")

        btn_clear_logs = ctk.CTkButton(
            top_bar,
            text="🗑️ Limpar Logs",
            command=self._clear_logs,
            width=100,
            height=26,
            fg_color="transparent",
            border_width=1
        )
        btn_clear_logs.pack(side="right")

        self.txt_logs = ctk.CTkTextbox(self.tab_logs, font=ctk.CTkFont(family="Consolas", size=12))
        self.txt_logs.pack(fill="both", expand=True, padx=10, pady=5)

    def _append_log(self, level: str, message: str):
        time_str = datetime.now().strftime("%H:%M:%S")
        prefix = {
            "info": "[INFO]",
            "sucesso": "[SUCESSO]",
            "aviso": "[AVISO]",
            "erro": "[ERRO]",
            "link": "[LINK]"
        }.get(level.lower(), "[LOG]")

        line = f"[{time_str}] {prefix} {message}\n"
        self.txt_logs.insert("end", line)
        self.txt_logs.see("end")

    def _on_telegram_log(self, level: str, msg: str):
        self.after(0, lambda: self._append_log(level, msg))

    def _on_telegram_message(self, data: Dict[str, Any]):
        """Executado quando uma mensagem do dia é recebida."""
        self.after(0, lambda: self._process_received_message(data))

    def _process_received_message(self, data: Dict[str, Any]):
        text = data.get("text", "")
        sender = data.get("sender", "Desconhecido")
        time_str = data.get("date_str", "")
        is_history = data.get("is_history", False)

        tag = "(Histórico)" if is_history else "(Ao Vivo)"
        self._append_log("info", f"{tag} Mensagem de {sender} [{time_str}]: {text[:80]}...")

        # Extrai os links do texto e de entidades
        entity_urls = data.get("entity_urls", [])
        links = self.link_handler.extract_links(text, entity_urls=entity_urls)
        if not links:
            return

        for link in links:
            already_done = is_link_evaluated(link)

            # Se já foi avaliado anteriormente: NÃO abre e NÃO avalia de novo
            if already_done:
                self._append_log("info", f"📌 Link ignorado: Já foi avaliado anteriormente: {link}")
                self._add_link_card(
                    time_str=time_str,
                    sender=sender,
                    url=link,
                    auto_opened=False,
                    is_already_evaluated=True
                )
                continue

            # Se ainda NÃO foi avaliado:
            opened = False
            is_ai_mode = bool(self.switch_auto_evaluate.get())

            # Se o Modo IA estiver desativado e o usuário marcou para abrir no navegador padrão:
            if not is_ai_mode and self.switch_auto_open.get():
                opened = self.link_handler.open_link(
                    link, 
                    check_duplicate=bool(self.switch_ignore_dup.get())
                )
                if opened:
                    self._append_log("link", f"🌐 Link aberto no navegador padrão: {link}")
                else:
                    self._append_log("aviso", f"Link repetido ou já aberto: {link}")

            # Adiciona o card na interface
            card_data = self._add_link_card(
                time_str=time_str,
                sender=sender,
                url=link,
                auto_opened=opened,
                is_already_evaluated=False
            )

            # Se a opção Modo IA estiver ativa, enfileira direto no robô automatizado
            if is_ai_mode:
                self._enqueue_evaluation(link, card_data)

    def _add_link_card(self, time_str: str, sender: str, url: str, auto_opened: bool, is_already_evaluated: bool = False) -> Dict[str, Any]:
        card = ctk.CTkFrame(self.scroll_links, fg_color=("gray85", "gray20"), corner_radius=6)
        card.pack(fill="x", padx=5, pady=4)

        # Header do Card
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(6, 2))

        lbl_sender = ctk.CTkLabel(
            header_frame, 
            text=f"👤 {sender}  •  🕒 {time_str}", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray70"
        )
        lbl_sender.pack(side="left")

        if is_already_evaluated:
            status_text = "📌 Já Avaliado"
            status_color = "#28a745"
        elif auto_opened:
            status_text = "🟢 Aberto Auto"
            status_color = "#28a745"
        else:
            status_text = "⚪ Detectado"
            status_color = "gray60"

        lbl_st = ctk.CTkLabel(header_frame, text=status_text, font=ctk.CTkFont(size=11), text_color=status_color)
        lbl_st.pack(side="right")

        # Corpo com URL e Botões
        body_frame = ctk.CTkFrame(card, fg_color="transparent")
        body_frame.pack(fill="x", padx=10, pady=(2, 6))

        lbl_url = ctk.CTkLabel(
            body_frame, 
            text=url, 
            font=ctk.CTkFont(size=12, underline=True),
            text_color="#4da6ff",
            anchor="w",
            cursor="hand2"
        )
        lbl_url.pack(side="left", fill="x", expand=True, padx=(0, 10))
        lbl_url.bind("<Button-1>", lambda e, u=url: self.link_handler.open_link(u))

        buttons_frame = ctk.CTkFrame(body_frame, fg_color="transparent")
        buttons_frame.pack(side="right")

        card_info = {
            "card": card,
            "lbl_st": lbl_st,
            "btn_frame": buttons_frame,
            "url": url,
            "time": time_str
        }

        # Botão para disparar avaliação
        if is_already_evaluated:
            btn_eval = ctk.CTkButton(
                buttons_frame,
                text="✓ Avaliado",
                width=80,
                height=24,
                state="disabled",
                fg_color="gray40",
                font=ctk.CTkFont(size=11)
            )
            btn_eval.pack(side="left", padx=(0, 4))
            card_info["btn_eval"] = btn_eval

            # Se houver print salvo no histórico, exibe o botão
            eval_info = get_evaluated_link_info(url)
            if eval_info and eval_info.get("screenshot_path"):
                p = eval_info.get("screenshot_path")
                if os.path.exists(p):
                    btn_print = ctk.CTkButton(
                        buttons_frame,
                        text="📸 Ver Print",
                        width=75,
                        height=24,
                        fg_color="#27ae60",
                        hover_color="#219955",
                        font=ctk.CTkFont(size=11),
                        command=lambda path=p: self._open_file(path)
                    )
                    btn_print.pack(side="left", padx=(0, 4))
        else:
            btn_eval = ctk.CTkButton(
                buttons_frame,
                text="⭐ Avaliar 5★",
                width=80,
                height=24,
                command=lambda u=url, cd=card_info: self._enqueue_evaluation(u, cd, manual=True),
                fg_color="#f39c12",
                hover_color="#d68910",
                font=ctk.CTkFont(size=11)
            )
            btn_eval.pack(side="left", padx=(0, 4))
            card_info["btn_eval"] = btn_eval

        btn_open = ctk.CTkButton(
            buttons_frame,
            text="Abrir ↗",
            width=65,
            height=24,
            command=lambda u=url: self.link_handler.open_link(u),
            fg_color="#3a7ebf",
            hover_color="#2b5f91",
            font=ctk.CTkFont(size=11)
        )
        btn_open.pack(side="left")

        self.links_captured.append({"time": time_str, "sender": sender, "url": url})
        self.lbl_link_counter.configure(text=f"Total de links encontrados hoje: {len(self.links_captured)}")
        return card_info

    def _enqueue_evaluation(self, url: str, card_data: Dict[str, Any], manual: bool = False):
        """Enfileira um link para avaliação sequencial (1 por 1) pelo robô."""
        if is_link_evaluated(url):
            self._append_log("aviso", f"📌 O link {url} já foi avaliado anteriormente. Não precisa abrir de novo.")
            self._update_card_as_evaluated(url, card_data)
            return

        lbl_st = card_data.get("lbl_st")
        if lbl_st and lbl_st.winfo_exists():
            lbl_st.configure(text="⏳ Na fila (1 por 1)...", text_color="#f39c12")

        self.eval_queue.put((url, card_data))
        q_pos = self.eval_queue.qsize()
        origem = "Manual" if manual else "Automático"
        self._append_log("info", f"⏳ [{origem}] Link na fila de avaliação (posição {q_pos}): {url}")

    def _update_card_as_evaluated(self, url: str, card_data: Dict[str, Any], screenshot_path: str = ""):
        """Atualiza o card para o estado de já avaliado."""
        lbl_st = card_data.get("lbl_st")
        btn_eval = card_data.get("btn_eval")
        btn_frame = card_data.get("btn_frame")

        if lbl_st and lbl_st.winfo_exists():
            lbl_st.configure(text="📌 Já Avaliado", text_color="#28a745")

        if btn_eval and btn_eval.winfo_exists():
            btn_eval.configure(text="✓ Avaliado", state="disabled", fg_color="gray40")

        if not screenshot_path:
            info = get_evaluated_link_info(url)
            if info:
                screenshot_path = info.get("screenshot_path", "")

        if btn_frame and btn_frame.winfo_exists() and screenshot_path and os.path.exists(screenshot_path):
            btn_print = ctk.CTkButton(
                btn_frame,
                text="📸 Ver Print",
                width=75,
                height=24,
                fg_color="#27ae60",
                hover_color="#219955",
                font=ctk.CTkFont(size=11),
                command=lambda p=screenshot_path: self._open_file(p)
            )
            btn_print.pack(side="left", padx=(0, 4))

    def _eval_queue_worker(self):
        """Worker em segundo plano que executa as avaliações UMA POR VEZ em sequência."""
        while True:
            try:
                item = self.eval_queue.get()
                if item is None:
                    break

                url, card_data = item

                # Verifica novamente se o link foi avaliado enquanto aguardava na fila
                if is_link_evaluated(url):
                    self.after(0, lambda u=url, cd=card_data: self._update_card_as_evaluated(u, cd))
                    self.eval_queue.task_done()
                    continue

                lbl_st = card_data.get("lbl_st")
                btn_frame = card_data.get("btn_frame")
                btn_eval = card_data.get("btn_eval")

                if lbl_st and lbl_st.winfo_exists():
                    self.after(0, lambda: lbl_st.configure(text="⏳ Avaliando 5★ no Chrome...", text_color="#f39c12"))

                self._append_log("info", f"⭐ Iniciando avaliação sequencial (1 por 1): {url}")
                res = self.evaluator.evaluate_place(url, on_status=lambda msg: self._append_log("info", msg))

                if res.get("success"):
                    screenshot_path = res.get("screenshot_path", "")
                    is_already = res.get("already_evaluated", False)
                    status_type = "ja_avaliado" if is_already else "avaliado"
                    
                    # Salva no histórico permanente do config.json
                    save_evaluated_link(url, screenshot_path=screenshot_path, status=status_type)

                    if is_already:
                        self._append_log("sucesso", f"📌 Local já avaliado ('Editar avaliação' detectado). Print: {os.path.basename(screenshot_path)}")
                        self._append_log("info", f"📌 Print NÃO reenviado para contato pois o local já havia sido avaliado.")
                        status_label = "📌 Já Avaliado Anteriormente"
                        status_color = "#17a2b8"
                    else:
                        self._append_log("sucesso", f"🎉 Avaliação 5★ postada com sucesso! Print: {os.path.basename(screenshot_path)}")
                        status_label = "⭐⭐⭐⭐⭐ Avaliado com Sucesso"
                        status_color = "#28a745"

                        # Envia print para o contato selecionado APENAS NA PRIMEIRA VEZ (Apenas a imagem do print, sem texto)
                        if self.switch_send_telegram.get() and self.selected_recipient_id and screenshot_path and os.path.exists(screenshot_path):
                            self._append_log("info", f"📤 Enviando comprovante (somente print) via Telegram para: {self.selected_recipient_name}...")
                            send_res = self.telegram.send_screenshot(
                                self.selected_recipient_id, 
                                screenshot_path, 
                                caption=""
                            )
                            if send_res.get("success"):
                                self._append_log("sucesso", f"✅ Comprovante enviado via Telegram para {self.selected_recipient_name} com sucesso!")
                            else:
                                err_send = send_res.get("error", "Erro ao enviar")
                                self._append_log("aviso", f"⚠️ Não foi possível enviar comprovante no Telegram: {err_send}")

                    if lbl_st and lbl_st.winfo_exists():
                        self.after(0, lambda sl=status_label, sc=status_color: lbl_st.configure(text=sl, text_color=sc))

                    if btn_eval and btn_eval.winfo_exists():
                        self.after(0, lambda: btn_eval.configure(text="✓ Avaliado", state="disabled", fg_color="gray40"))

                    if btn_frame and btn_frame.winfo_exists() and screenshot_path and os.path.exists(screenshot_path):
                        def _add_print_btn(sp=screenshot_path):
                            btn_print = ctk.CTkButton(
                                btn_frame,
                                text="📸 Ver Print",
                                width=75,
                                height=24,
                                fg_color="#27ae60",
                                hover_color="#219955",
                                font=ctk.CTkFont(size=11),
                                command=lambda path=sp: self._open_file(path)
                            )
                            btn_print.pack(side="left", padx=(0, 4))
                        self.after(0, _add_print_btn)
                else:
                    err = res.get("error", "Erro desconhecido")
                    self._append_log("erro", f"Falha na avaliação 5★: {err}")
                    if lbl_st and lbl_st.winfo_exists():
                        self.after(0, lambda: lbl_st.configure(text="❌ Falha na Avaliação", text_color="#ff5555"))

                # Intervalo seguro para o Chrome respirar e fechar modais antes do próximo item da fila
                time.sleep(2)
                self.eval_queue.task_done()

            except Exception as e:
                self._append_log("erro", f"Erro no processamento da fila de avaliação: {e}")

    def _open_chrome_login(self):
        """Abre o Chrome com o perfil persistente para o usuário fazer login no Google."""
        self._append_log("info", "Abrindo Chrome para login na conta Google...")
        def _bg():
            self.evaluator.open_for_login()
        threading.Thread(target=_bg, daemon=True).start()

    def _open_prints_folder(self):
        """Abre a pasta de prints no Windows Explorer."""
        self._open_file(self.evaluator.prints_dir)

    def _open_file(self, target_path: str):
        """Abre arquivo ou pasta no Windows com segurança."""
        try:
            if os.name == 'nt':
                os.startfile(target_path)
            else:
                import subprocess
                subprocess.Popen(['xdg-open', target_path])
        except Exception as e:
            self._append_log("erro", f"Não foi possível abrir {target_path}: {e}")

    def _clear_links(self):
        for widget in self.scroll_links.winfo_children():
            widget.destroy()
        self.links_captured.clear()
        self.link_handler.seen_links.clear()
        
        # Remove todos os links de config.json e deleta todos os arquivos de print da pasta prints/
        deleted_prints = cleanup_prints_folder()
        clear_all_evaluated_links(delete_prints=True)
        
        self.lbl_link_counter.configure(text="Total de links encontrados hoje: 0")
        self._append_log("info", f"🗑️ Lista limpa, histórico resetado no config.json e {deleted_prints} prints removidos da pasta.")

    def _clear_logs(self):
        self.txt_logs.delete("1.0", "end")

    def _check_nightly_cleanup(self):
        """Verificador periódico para executar limpeza completa às 21:00."""
        try:
            res = check_and_run_nightly_cleanup()
            if res.get("cleaned"):
                # Limpa a interface gráfica se a limpeza das 21h disparou
                for widget in self.scroll_links.winfo_children():
                    widget.destroy()
                self.links_captured.clear()
                self.link_handler.seen_links.clear()
                self.lbl_link_counter.configure(text="Total de links encontrados hoje: 0")
                self._append_log("sucesso", f"🌙 Limpeza Noturna das 21:00 executada com sucesso! {res.get('prints_deleted', 0)} prints e {res.get('evaluated_links_cleared', 0)} links foram limpos.")
        except Exception:
            pass
        finally:
            # Re-agenda para checar a cada 30 segundos
            self.after(30000, self._check_nightly_cleanup)

    # ==========================================
    # FLUXO DE CONEXÃO & CREDENCIAIS
    # ==========================================
    def _auto_connect(self):
        # Inicia o verificador automático das 21:00
        self._check_nightly_cleanup()

        # Limpa automaticamente links e prints de dias anteriores ao iniciar um novo dia
        removed_count = cleanup_old_evaluated_links()
        if removed_count > 0:
            self._append_log("info", f"🧹 Limpeza automática de novo dia: {removed_count} links/prints de dias anteriores foram removidos.")

        creds = load_credentials()
        api_id = creds.get("api_id", "")
        api_hash = creds.get("api_hash", "")

        if api_id and api_hash:
            self._append_log("info", f"Credenciais encontradas em {CONFIG_FILE}. Testando sessão...")
            threading.Thread(target=self._verify_session_bg, args=(api_id, api_hash), daemon=True).start()
        else:
            self._append_log("aviso", "Nenhuma credencial configurada. Abra 'Configurar / Conectar Conta'.")
            self._open_credentials_modal()

    def _verify_session_bg(self, api_id: str, api_hash: str):
        try:
            res = self.telegram.check_connection(api_id, api_hash)
            if res.get("authorized"):
                user = res.get("user")
                self.after(0, lambda: self._on_connected_success(user))
            else:
                self.after(0, lambda: self._append_log("aviso", "Sessão não autorizada ou expirada. Faça login."))
        except Exception as e:
            self.after(0, lambda: self._append_log("erro", f"Erro na conexão inicial: {e}"))

    def _on_connected_success(self, user: Dict[str, Any]):
        self.is_connected = True
        self.user_data = user
        nome = user.get("first_name", "") + (" " + user.get("last_name", "") if user.get("last_name") else "")
        username = f"@{user.get('username')}" if user.get("username") else user.get("phone", "")

        self.status_badge.configure(text="🟢 Conectado", text_color="#28a745")
        self.user_info_label.configure(text=f"{nome}\n{username}")
        self._append_log("sucesso", f"Conectado com sucesso como {nome} ({username})")

        # Atualiza a lista de grupos disponíveis
        self._refresh_dialogs()

    def _open_credentials_modal(self):
        creds = load_credentials()
        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.title("Credenciais do Telegram")
        dialog.resizable(False, False)
        set_app_icon(dialog)

        # Mini Logo
        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path)
                dialog.logo_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(50, 50))
                ctk.CTkLabel(dialog, image=dialog.logo_img, text="").pack(pady=(15, 2))
            except Exception:
                pass

        lbl = ctk.CTkLabel(dialog, text="Configuração de Acesso ao Telegram", font=ctk.CTkFont(size=14, weight="bold"))
        lbl.pack(pady=(2, 5))

        sub = ctk.CTkLabel(dialog, text="Obtenha seu API ID e API Hash em https://my.telegram.org", font=ctk.CTkFont(size=11), text_color="gray70")
        sub.pack(pady=(0, 10))

        f = ctk.CTkFrame(dialog, fg_color="transparent")
        f.pack(fill="x", padx=30)

        ctk.CTkLabel(f, text="API ID:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", pady=(5, 2))
        entry_api_id = ctk.CTkEntry(f, placeholder_text="Ex: 12345678")
        entry_api_id.pack(fill="x", pady=(0, 10))
        entry_api_id.insert(0, creds.get("api_id", ""))

        ctk.CTkLabel(f, text="API HASH:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", pady=(5, 2))
        entry_api_hash = ctk.CTkEntry(f, placeholder_text="Ex: a1b2c3d4e5f6...")
        entry_api_hash.pack(fill="x", pady=(0, 10))
        entry_api_hash.insert(0, creds.get("api_hash", ""))

        ctk.CTkLabel(f, text="Número de Telefone (com DDI/DDD):", font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", pady=(5, 2))
        entry_phone = ctk.CTkEntry(f, placeholder_text="Ex: +5511999998888")
        entry_phone.pack(fill="x", pady=(0, 15))
        entry_phone.insert(0, creds.get("phone", ""))

        btn_action = ctk.CTkButton(
            dialog,
            text="Solicitar Código de Acesso",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            command=lambda: self._handle_request_code(
                entry_api_id.get().strip(),
                entry_api_hash.get().strip(),
                entry_phone.get().strip(),
                dialog
            )
        )
        btn_action.pack(fill="x", padx=30, pady=(10, 20))

        # Centraliza exatamente no monitor / janela pai e exibe
        center_window(dialog, 460, 470, parent=self)
        dialog.deiconify()
        dialog.grab_set()
        dialog.focus()

    def _handle_request_code(self, api_id: str, api_hash: str, phone: str, parent_dialog: ctk.CTkToplevel):
        if not api_id or not api_hash or not phone:
            messagebox.showwarning("Aviso", "Preencha todos os campos para continuar.", parent=parent_dialog)
            return

        # Salva as credenciais no arquivo JSON
        save_credentials(api_id, api_hash, phone)
        self._append_log("info", f"Credenciais salvas em {CONFIG_FILE}.")

        def _bg():
            self._append_log("info", f"Solicitando código de acesso para {phone}...")
            res = self.telegram.request_code(api_id, api_hash, phone)
            if res.get("success"):
                self.after(0, lambda: self._show_code_input_modal(parent_dialog))
            else:
                self.after(0, lambda: messagebox.showerror("Erro", f"Falha ao solicitar código: {res.get('error')}", parent=parent_dialog))

        threading.Thread(target=_bg, daemon=True).start()

    def _show_code_input_modal(self, parent_dialog: ctk.CTkToplevel):
        parent_dialog.destroy()

        code_dialog = ctk.CTkToplevel(self)
        code_dialog.withdraw()
        code_dialog.title("Verificação Telegram")
        code_dialog.resizable(False, False)
        set_app_icon(code_dialog)

        # Mini Logo
        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path)
                code_dialog.logo_img = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(50, 50))
                ctk.CTkLabel(code_dialog, image=code_dialog.logo_img, text="").pack(pady=(15, 2))
            except Exception:
                pass

        lbl = ctk.CTkLabel(code_dialog, text="Digite o Código do Telegram", font=ctk.CTkFont(size=14, weight="bold"))
        lbl.pack(pady=(2, 5))

        sub = ctk.CTkLabel(code_dialog, text="Verifique o código recebido no seu app do Telegram.", font=ctk.CTkFont(size=11), text_color="gray70")
        sub.pack(pady=(0, 10))

        f = ctk.CTkFrame(code_dialog, fg_color="transparent")
        f.pack(fill="x", padx=30)

        ctk.CTkLabel(f, text="Código de Verificação:", font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", pady=(5, 2))
        entry_code = ctk.CTkEntry(f, placeholder_text="Ex: 12345")
        entry_code.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(f, text="Senha 2FA (se ativada):", font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", pady=(5, 2))
        entry_2fa = ctk.CTkEntry(f, placeholder_text="Opcional se não usar 2FA", show="*")
        entry_2fa.pack(fill="x", pady=(0, 15))

        btn_verify = ctk.CTkButton(
            code_dialog,
            text="Confirmar e Conectar",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            command=lambda: self._handle_submit_code(entry_code.get().strip(), entry_2fa.get().strip(), code_dialog)
        )
        btn_verify.pack(fill="x", padx=30, pady=(10, 20))

        # Centraliza exatamente no monitor / janela pai e exibe
        center_window(code_dialog, 420, 320, parent=self)
        code_dialog.deiconify()
        code_dialog.grab_set()
        code_dialog.focus()

    def _handle_submit_code(self, code: str, password_2fa: str, dialog: ctk.CTkToplevel):
        if not code:
            messagebox.showwarning("Aviso", "Digite o código recebido.", parent=dialog)
            return

        def _bg():
            res = self.telegram.sign_in_with_code(code, password=password_2fa if password_2fa else None)
            if res.get("success"):
                self.after(0, lambda: dialog.destroy())
                self.after(0, lambda: self._on_connected_success(res.get("user")))
                self.after(0, lambda: messagebox.showinfo("Sucesso", "Conectado ao Telegram com sucesso!"))
            elif res.get("requires_2fa"):
                self.after(0, lambda: messagebox.showwarning("2FA Necessário", "Esta conta possui Verificação em Duas Etapas. Digite sua senha 2FA.", parent=dialog))
            else:
                self.after(0, lambda: messagebox.showerror("Erro de Login", res.get("error", "Erro desconhecido"), parent=dialog))

        threading.Thread(target=_bg, daemon=True).start()

    # ==========================================
    # DIÁLOGOS E MONITORAMENTO
    # ==========================================
    def _refresh_dialogs(self):
        if not self.is_connected:
            self._append_log("aviso", "Conecte sua conta para listar grupos.")
            return

        def _bg():
            self._append_log("info", "Carregando grupos e canais...")
            dialogs = self.telegram.get_dialogs_list()
            self.dialogs_cache = dialogs
            self.after(0, self._populate_dialogs_list)

        threading.Thread(target=_bg, daemon=True).start()

    def _populate_dialogs_list(self):
        self._filter_dialogs()
        self._filter_recipients()
        
        creds = load_credentials()
        saved_recip_id = creds.get("target_recipient_id")
        saved_recip_name = creds.get("target_recipient_name")

        if self.dialogs_cache:
            self._append_log("sucesso", f"{len(self.dialogs_cache)} conversas/grupos carregados!")
            
            # Restaura o grupo selecionado ou seleciona o primeiro
            if self.selected_chat_id is None and len(self.dialogs_cache) > 0:
                first_group = next((d for d in self.dialogs_cache if d.get("is_group")), self.dialogs_cache[0])
                self._select_group(first_group.get("id"), f"[{first_group.get('type')}] {first_group.get('title')}")

            # Restaura o destinatário salvo se existir na lista
            if saved_recip_id and saved_recip_name:
                self._select_recipient(saved_recip_id, saved_recip_name, persist=False)

    def _filter_dialogs(self, event=None):
        query = self.entry_search_group.get().strip().lower()
        
        # Limpa os botões anteriores
        for widget in self.scroll_groups.winfo_children():
            widget.destroy()
        self.group_buttons.clear()

        if not self.dialogs_cache:
            lbl_empty = ctk.CTkLabel(
                self.scroll_groups, 
                text="Nenhum grupo carregado", 
                font=ctk.CTkFont(size=11), 
                text_color="gray60"
            )
            lbl_empty.pack(pady=10)
            return

        matched = 0
        max_render = 35  # Limite para renderização ultra-rápida sem travar a interface

        for d in self.dialogs_cache:
            title = d.get("title", "")
            dtype = d.get("type", "")
            chat_id = d.get("id")

            if not query or query in title.lower() or query in dtype.lower():
                matched += 1
                if matched > max_render:
                    continue

                full_text = f"[{dtype}] {title}"
                is_selected = (self.selected_chat_id == chat_id)
                btn_fg = "#2b5f91" if is_selected else ("gray80", "gray20")
                text_color = "white" if is_selected else ("gray10", "gray90")

                btn = ctk.CTkButton(
                    self.scroll_groups,
                    text=full_text,
                    height=26,
                    anchor="w",
                    fg_color=btn_fg,
                    hover_color="#3a7ebf",
                    text_color=text_color,
                    font=ctk.CTkFont(size=11),
                    command=lambda cid=chat_id, txt=full_text: self._select_group(cid, txt)
                )
                btn.pack(fill="x", padx=2, pady=1)
                self.group_buttons.append(btn)

        if matched == 0:
            lbl_no_match = ctk.CTkLabel(
                self.scroll_groups, 
                text="Nenhum grupo corresponde à busca", 
                font=ctk.CTkFont(size=11), 
                text_color="gray60"
            )
            lbl_no_match.pack(pady=10)
        elif matched > max_render:
            lbl_more = ctk.CTkLabel(
                self.scroll_groups,
                text=f"... e mais {matched - max_render} grupos (use a busca acima)",
                font=ctk.CTkFont(size=10),
                text_color="gray60"
            )
            lbl_more.pack(pady=4)

    def _filter_recipients(self, event=None):
        """Filtra e renderiza a lista de contatos/conversas de destino para envio de print."""
        query = self.entry_search_recipient.get().strip().lower()

        for widget in self.scroll_recipients.winfo_children():
            widget.destroy()
        self.recipient_buttons.clear()

        if not self.dialogs_cache:
            lbl_empty = ctk.CTkLabel(
                self.scroll_recipients, 
                text="Nenhum contato carregado", 
                font=ctk.CTkFont(size=11), 
                text_color="gray60"
            )
            lbl_empty.pack(pady=10)
            return

        matched = 0
        max_render = 35

        for d in self.dialogs_cache:
            title = d.get("title", "")
            dtype = d.get("type", "")
            chat_id = d.get("id")

            if not query or query in title.lower() or query in dtype.lower():
                matched += 1
                if matched > max_render:
                    continue

                full_text = f"[{dtype}] {title}"
                is_selected = (self.selected_recipient_id == chat_id)
                btn_fg = "#28a745" if is_selected else ("gray80", "gray20")
                text_color = "white" if is_selected else ("gray10", "gray90")

                btn = ctk.CTkButton(
                    self.scroll_recipients,
                    text=full_text,
                    height=26,
                    anchor="w",
                    fg_color=btn_fg,
                    hover_color="#218838",
                    text_color=text_color,
                    font=ctk.CTkFont(size=11),
                    command=lambda cid=chat_id, txt=full_text: self._select_recipient(cid, txt)
                )
                btn.pack(fill="x", padx=2, pady=1)
                self.recipient_buttons.append(btn)

        if matched == 0:
            lbl_no_match = ctk.CTkLabel(
                self.scroll_recipients, 
                text="Nenhum contato corresponde à busca", 
                font=ctk.CTkFont(size=11), 
                text_color="gray60"
            )
            lbl_no_match.pack(pady=10)
        elif matched > max_render:
            lbl_more = ctk.CTkLabel(
                self.scroll_recipients,
                text=f"... e mais {matched - max_render} contatos (use a busca acima)",
                font=ctk.CTkFont(size=10),
                text_color="gray60"
            )
            lbl_more.pack(pady=4)

    def _select_group(self, chat_id: int, title_display: str):
        self.selected_chat_id = chat_id
        self.lbl_selected_group.configure(
            text=f"🎯 {title_display}",
            text_color="#28a745"
        )
        self._append_log("info", f"Grupo selecionado para monitoramento: {title_display}")
        self._filter_dialogs()

    def _select_recipient(self, chat_id: int, title_display: str, persist: bool = True):
        """Define o contato que receberá os comprovantes de print."""
        self.selected_recipient_id = chat_id
        self.selected_recipient_name = title_display
        self.lbl_selected_recipient.configure(
            text=f"📤 {title_display}",
            text_color="#28a745"
        )
        self._append_log("info", f"Contato destinatário selecionado: {title_display}")
        
        if persist:
            cfg = load_credentials()
            cfg["target_recipient_id"] = chat_id
            cfg["target_recipient_name"] = title_display
            save_config(cfg)

        self._filter_recipients()

    def _get_selected_chat_id(self) -> Optional[int]:
        return self.selected_chat_id

    def _toggle_monitoring(self):
        if self.telegram.is_monitoring:
            # Parar monitoramento em background thread
            def _stop_bg():
                self.telegram.stop_monitoring()

            threading.Thread(target=_stop_bg, daemon=True).start()
            self.btn_toggle_monitor.configure(
                text="▶️ Iniciar Monitoramento",
                fg_color="#28a745",
                hover_color="#218838"
            )
        else:
            # Iniciar monitoramento
            if not self.is_connected:
                messagebox.showwarning("Aviso", "Conecte sua conta do Telegram primeiro.")
                return

            chat_id = self._get_selected_chat_id()
            if not chat_id:
                messagebox.showwarning("Aviso", "Selecione um grupo válido na lista.")
                return

            fetch_today = bool(self.switch_fetch_today.get())
            
            def _bg():
                self.telegram.start_monitoring(chat_id, process_today_history=fetch_today)

            threading.Thread(target=_bg, daemon=True).start()
            
            self.btn_toggle_monitor.configure(
                text="⏸️ Pausar Monitoramento",
                fg_color="#d9534f",
                hover_color="#c9302c"
            )


if __name__ == "__main__":
    app = BootAvaliadorApp(show_splash=True)
    app.mainloop()
