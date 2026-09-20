import sys
import os
import subprocess
import ctypes

try:
    myappid = "bootavaliador.telegram.monitor.1.0"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def check_requirements():
    """Verifica se os pacotes essenciais estão instalados."""
    try:
        import customtkinter
        import telethon
        from PIL import Image
    except ImportError:
        print("Instalando dependencias necessarias...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def main():
    # Define diretório de trabalho local
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    check_requirements()
    
    from gui import BootAvaliadorApp

    print("Iniciando Boot Avaliador...")
    app = BootAvaliadorApp(show_splash=True)
    app.mainloop()

if __name__ == "__main__":
    main()
