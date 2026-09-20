import os
import sys
import time
import threading
import ctypes
from typing import Callable, Optional
import customtkinter as ctk
from PIL import Image, ImageTk

try:
    myappid = "bootavaliador.telegram.monitor.1.0"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def set_app_icon(window):
    """Aplica o logo.ico e logo.png como ícone da janela e barra de tarefas do Windows."""
    try:
        ico_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "logo.ico"))
        png_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "logo.png"))
        if os.path.exists(ico_path):
            window.iconbitmap(ico_path)
            if os.path.exists(png_path):
                img = Image.open(png_path)
                photo = ImageTk.PhotoImage(img)
                window.iconphoto(False, photo)
                window._icon_photo_ref = photo
        elif os.path.exists(png_path):
            img = Image.open(png_path)
            photo = ImageTk.PhotoImage(img)
            window.iconphoto(False, photo)
            window._icon_photo_ref = photo
    except Exception:
        pass

def center_window(window, width: int, height: int):
    """Centraliza a janela na tela dinamicamente."""
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")

class SplashScreen(ctk.CTkToplevel):
    def __init__(self, master=None, on_complete: Optional[Callable[[], None]] = None):
        super().__init__(master)

        self.on_complete = on_complete

        # Janela sem bordas nativas
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        width = 440
        height = 480
        center_window(self, width, height)
        set_app_icon(self)

        # Container com borda moderna
        self.main_container = ctk.CTkFrame(
            self, 
            corner_radius=16, 
            fg_color=("gray95", "#18191c"),
            border_width=2,
            border_color="#3a7ebf"
        )
        self.main_container.pack(fill="both", expand=True, padx=2, pady=2)

        # Imagem da Logo
        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            try:
                pil_img = Image.open(logo_path)
                self.logo_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(160, 160))
                self.lbl_logo = ctk.CTkLabel(self.main_container, image=self.logo_image, text="")
                self.lbl_logo.pack(pady=(35, 10))
            except Exception:
                self.lbl_logo = ctk.CTkLabel(self.main_container, text="🤖", font=ctk.CTkFont(size=64))
                self.lbl_logo.pack(pady=(40, 10))
        else:
            self.lbl_logo = ctk.CTkLabel(self.main_container, text="🤖", font=ctk.CTkFont(size=64))
            self.lbl_logo.pack(pady=(40, 10))

        # Título
        self.lbl_title = ctk.CTkLabel(
            self.main_container, 
            text="Boot Avaliador", 
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=("gray10", "#ffffff")
        )
        self.lbl_title.pack(pady=(0, 4))

        # Subtítulo
        self.lbl_subtitle = ctk.CTkLabel(
            self.main_container, 
            text="Monitoramento Inteligente de Links do Telegram", 
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        )
        self.lbl_subtitle.pack(pady=(0, 25))

        # Barra de Progresso
        self.progress_bar = ctk.CTkProgressBar(
            self.main_container, 
            width=320, 
            height=10, 
            corner_radius=5,
            progress_color="#3a7ebf",
            fg_color=("gray80", "gray25")
        )
        self.progress_bar.pack(pady=(0, 10))
        self.progress_bar.set(0.0)

        # Texto de Status
        self.lbl_status = ctk.CTkLabel(
            self.main_container, 
            text="Inicializando componentes...", 
            font=ctk.CTkFont(size=11),
            text_color="gray60"
        )
        self.lbl_status.pack(pady=(0, 20))

        # Inicia a animação de carregamento
        self.after(150, self._start_loading_sequence)

    def _start_loading_sequence(self):
        steps = [
            (0.25, "Carregando configurações (config.json)...", 0.25),
            (0.55, "Inicializando serviços do Telegram...", 0.3),
            (0.80, "Carregando extrator de links e filtros...", 0.25),
            (0.95, "Preparando interface gráfica...", 0.2),
            (1.00, "Pronto! Abrindo aplicativo...", 0.25)
        ]

        def _run():
            for progress, status_text, delay in steps:
                time.sleep(delay)
                if not self.winfo_exists():
                    return
                self.after(0, lambda p=progress, s=status_text: self._update_ui(p, s))
            
            time.sleep(0.2)
            if self.winfo_exists():
                self.after(0, self._finish_splash)

        threading.Thread(target=_run, daemon=True).start()

    def _update_ui(self, progress: float, status_text: str):
        if self.winfo_exists():
            self.progress_bar.set(progress)
            self.lbl_status.configure(text=status_text)

    def _finish_splash(self):
        if self.winfo_exists():
            self.destroy()
        if self.on_complete:
            self.on_complete()
