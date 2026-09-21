import os
import sys
import time
import datetime
from typing import Optional, Callable, Dict, Any, List
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

PRINTS_DIR = "prints"
PROFILE_DIR = "chrome_profile"

class GoogleMapsEvaluator:
    def __init__(self, prints_dir: str = PRINTS_DIR, profile_dir: str = PROFILE_DIR):
        # Quando empacotado pelo PyInstaller, usa a pasta do .exe (e não a pasta temporária de extração)
        if getattr(sys, "frozen", False):
            self.base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.prints_dir = os.path.join(self.base_dir, prints_dir)
        self.profile_dir = os.path.join(self.base_dir, profile_dir)
        
        # Garante diretórios
        os.makedirs(self.prints_dir, exist_ok=True)
        os.makedirs(self.profile_dir, exist_ok=True)

        self.driver: Optional[webdriver.Chrome] = None

    def _clean_profile_locks(self):
        """Remove arquivos de lock do perfil do Chrome para evitar erro de 'Chrome instance exited'."""
        lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile", "DevToolsActivePort"]
        try:
            for root, dirs, files in os.walk(self.profile_dir):
                for file in files:
                    if file in lock_files:
                        try:
                            os.remove(os.path.join(root, file))
                        except Exception:
                            pass
                break  # Apenas no diretório raiz do perfil
        except Exception:
            pass

    def _kill_lingering_chrome(self):
        """Encerra processos órfãos do Chrome e ChromeDriver se houver travamento de perfil."""
        if os.name == 'nt':
            try:
                import subprocess
                subprocess.run(["taskkill", "/F", "/IM", "chromedriver.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def _init_driver(self, headless: bool = False) -> webdriver.Chrome:
        """Inicializa o Chrome com o perfil de usuário persistente para manter login Google."""
        if self.driver is not None:
            try:
                # Testa se o driver ainda está ativo e responsivo
                _ = self.driver.current_url
                return self.driver
            except Exception:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

        self._clean_profile_locks()

        chrome_options = Options()
        chrome_options.add_argument(f"--user-data-dir={self.profile_dir}")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        if headless:
            chrome_options.add_argument("--headless=new")

        service = Service(ChromeDriverManager().install())

        for attempt in range(3):
            try:
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                return self.driver
            except Exception as e:
                err_str = str(e)
                if "Chrome instance exited" in err_str or "session not created" in err_str or "version" in err_str:
                    self._kill_lingering_chrome()
                    self._clean_profile_locks()
                    time.sleep(1.5)
                else:
                    time.sleep(1)

        # Última tentativa após limpeza forçada
        self._kill_lingering_chrome()
        self._clean_profile_locks()
        time.sleep(1)
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        return self.driver

    def close_driver(self):
        """Encerra com segurança o navegador Chrome e limpa recursos de perfil."""
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self._clean_profile_locks()

    def open_for_login(self):
        """Abre o navegador para o usuário fazer login na sua conta Google."""
        driver = self._init_driver(headless=False)
        driver.get("https://accounts.google.com/")

    def evaluate_place(self, url: str, on_status: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """
        Executa o fluxo de verificação e avaliação no Google Maps:
        1. Abre o link
        2. Clica em 'Avaliações'
        3. Verifica se já foi avaliado ('Editar avaliação'):
           -> Se já avaliado: tira print da tela com a avaliação e finaliza com sucesso.
           -> Se não avaliado: clica em 'Avaliar', dá 5 estrelas em tudo, posta e tira print do resultado.
        Ao final (após tirar print ou identificar que já foi avaliado), fecha o navegador automaticamente.
        """
        def log(msg: str):
            if on_status:
                try:
                    on_status(msg)
                except Exception:
                    pass
            try:
                print(f"[Avaliador] {msg}")
            except Exception:
                try:
                    safe_msg = str(msg).encode('ascii', errors='replace').decode('ascii')
                    print(f"[Avaliador] {safe_msg}")
                except Exception:
                    pass

        try:
            log("Iniciando navegador automatizado...")
            driver = self._init_driver(headless=False)
            driver.get(url)
            
            # Aguarda a página carregar
            time.sleep(4)

            # Fecha aviso de cookies se houver
            self._handle_cookie_consent(driver, log)

            # Verifica se precisa fazer login no Google
            self._check_login_status(driver, log)

            log("Buscando aba 'Avaliações'...")
            self._click_reviews_tab(driver, log)

            time.sleep(2)
            log("Verificando se o local já foi avaliado...")

            # 1. VERIFICA SE JÁ FOI AVALIADO (Botão 'Editar avaliação' presente)
            for _ in range(3):
                if self._check_if_already_reviewed(driver, log):
                    log("📌 Local JÁ FOI AVALIADO anteriormente ('Editar avaliação' detectado).")
                    time.sleep(1)
                    screenshot_path = self._take_screenshot(driver, prefix="ja_avaliado_")
                    log(f"📸 Print da avaliação existente salvo em: {os.path.basename(screenshot_path)}")
                    return {
                        "success": True,
                        "already_evaluated": True,
                        "screenshot_path": screenshot_path,
                        "url": url,
                        "message": "Local já avaliado anteriormente."
                    }
                time.sleep(1)

            # 2. SE NÃO FOI AVALIADO, EXECUTA AVALIAÇÃO NOVA DE 5 ESTRELAS
            log("Buscando botão 'Avaliar'...")
            self._click_write_review_button(driver, log)

            if self._check_if_already_reviewed(driver, log):
                log("📌 Local JÁ FOI AVALIADO anteriormente ('Editar avaliação' detectado).")
                screenshot_path = self._take_screenshot(driver, prefix="ja_avaliado_")
                log(f"📸 Print da avaliação existente salvo em: {os.path.basename(screenshot_path)}")
                return {
                    "success": True,
                    "already_evaluated": True,
                    "screenshot_path": screenshot_path,
                    "url": url,
                    "message": "Local já avaliado anteriormente."
                }

            time.sleep(3)
            log("Marcando 5 estrelas em todas as categorias...")
            stars_filled = self._fill_five_stars(driver, log)

            time.sleep(2)
            log("Clicando no botão 'Postar'...")
            post_clicked = self._click_post_button(driver, log)

            # Aguarda explicitamente a confirmação ('Agradecemos sua postagem' / 'Concluído' / 'Editar avaliação')
            confirmed = self._wait_for_post_confirmation(driver, log, timeout=15)
            
            if not confirmed:
                log("❌ ERRO: A postagem da avaliação NÃO foi confirmada pelo Google Maps. Print de comprovante não será gerado.")
                return {
                    "success": False,
                    "error": "A postagem não foi confirmada pelo Google Maps (estrelas não ativaram ou botão 'Postar' não concluiu).",
                    "url": url
                }

            log("📸 Capturando print do comprovante APÓS a postagem confirmada...")
            screenshot_path = self._take_screenshot(driver, prefix="avaliacao_postada_")

            # Fecha o modal 'Concluído' se desejar
            self._click_done_button(driver, log)

            log(f"✅ Avaliação 5★ postada e comprovante salvo em: {os.path.basename(screenshot_path)}")
            return {
                "success": True,
                "already_evaluated": False,
                "screenshot_path": screenshot_path,
                "url": url,
                "message": "Avaliação postada com sucesso."
            }

        except Exception as e:
            err_msg = str(e)
            log(f"❌ Erro durante a avaliação: {err_msg}")
            try:
                if self.driver:
                    err_print = self._take_screenshot(self.driver, prefix="erro_")
                    return {"success": False, "error": err_msg, "screenshot_path": err_print}
            except Exception:
                pass
            return {"success": False, "error": err_msg}

        finally:
            log("Fechando navegador Chrome...")
            self.close_driver()

    def _handle_cookie_consent(self, driver: webdriver.Chrome, log: Callable[[str], None]):
        """Lida com dialog de consentimento do Google se aparecer."""
        selectors = [
            "//button[contains(., 'Aceitar tudo')]",
            "//button[contains(., 'Concordo')]",
            "//button[contains(., 'Accept all')]",
            "//button[contains(@aria-label, 'Aceitar tudo')]",
            "//form//button[last()]"
        ]
        for sel in selectors:
            try:
                btns = driver.find_elements(By.XPATH, sel)
                for b in btns:
                    if b.is_displayed() and ("Aceitar" in b.text or "Concordo" in b.text or "Accept" in b.text):
                        b.click()
                        log("Aviso de cookies aceito.")
                        time.sleep(2)
                        return
            except Exception:
                pass

    def _check_login_status(self, driver: webdriver.Chrome, log: Callable[[str], None]):
        """Verifica se há botão de 'Fazer login' explícito no Maps."""
        try:
            login_buttons = driver.find_elements(By.XPATH, "//a[contains(@href, 'accounts.google.com') and (contains(., 'Fazer login') or contains(., 'Sign in'))]")
            for btn in login_buttons:
                if btn.is_displayed():
                    log("⚠️ Aviso: Conta Google pode não estar conectada. Se a avaliação falhar, use o botão 'Abrir Chrome (Login Google)'.")
                    break
        except Exception:
            pass

    def _click_reviews_tab(self, driver: webdriver.Chrome, log: Callable[[str], None]):
        """Clica na aba 'Avaliações' no Google Maps."""
        tab_selectors = [
            "//button[@role='tab' and (contains(., 'Avaliações') or contains(@aria-label, 'Avaliações'))]",
            "//div[@role='tab' and (contains(., 'Avaliações') or contains(@aria-label, 'Avaliações'))]",
            "//button[contains(@aria-label, 'Avaliações')]",
            "//button[contains(@aria-label, 'Reviews')]",
            "//span[text()='Avaliações']/ancestor::button",
            "//div[text()='Avaliações']/ancestor::button",
            "//button[contains(., 'Avaliações')]",
            "//div[contains(@aria-label, 'Avaliações')]",
            "//div[contains(text(), 'Avaliações')]",
            "//span[contains(text(), 'Avaliações')]"
        ]
        for sel in tab_selectors:
            try:
                elements = driver.find_elements(By.XPATH, sel)
                for el in elements:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", el)
                        driver.execute_script("arguments[0].click();", el)
                        log("Aba 'Avaliações' clicada com sucesso.")
                        time.sleep(2)
                        return
            except Exception:
                continue
        log("Aba 'Avaliações' já ativa ou visualização direta.")

    def _check_if_already_reviewed(self, driver: webdriver.Chrome, log: Callable[[str], None]) -> bool:
        """Verifica se o botão 'Editar avaliação' ou indicativo de já avaliado está visível."""
        edit_selectors = [
            "//button[contains(., 'Editar avaliação')]",
            "//button[contains(., 'Editar a avaliação')]",
            "//button[contains(., 'Editar sua avaliação')]",
            "//button[contains(@aria-label, 'Editar avaliação')]",
            "//button[contains(@aria-label, 'Editar sua avaliação')]",
            "//button[contains(@aria-label, 'Edit review')]",
            "//span[contains(text(), 'Editar avaliação')]",
            "//div[contains(text(), 'Editar avaliação')]",
            "//a[contains(., 'Editar avaliação')]",
            "//*[contains(text(), 'Editar avaliação')]",
            "//button[contains(@jsaction, 'editReview')]",
            "//div[contains(text(), 'Sua avaliação')]",
            "//h3[contains(text(), 'Sua avaliação')]"
        ]
        for sel in edit_selectors:
            try:
                elements = driver.find_elements(By.XPATH, sel)
                for el in elements:
                    if el.is_displayed():
                        return True
            except Exception:
                continue
        return False

    def _click_write_review_button(self, driver: webdriver.Chrome, log: Callable[[str], None]):
        """Clica no botão 'Avaliar' / 'Escrever uma avaliação'."""
        selectors = [
            "//button[contains(@aria-label, 'Avaliar')]",
            "//button[contains(@aria-label, 'Escrever uma avaliação')]",
            "//button[contains(@aria-label, 'Write a review')]",
            "//button[@data-value='Avaliar']",
            "//button[contains(., 'Avaliar')]",
            "//button[contains(., 'Escrever uma avaliação')]",
            "//span[contains(text(), 'Avaliar')]/ancestor::button",
            "//span[contains(text(), 'Escrever uma avaliação')]/ancestor::button",
            "//div[contains(text(), 'Avaliar')]/ancestor::button",
            "//div[@role='button' and contains(., 'Avaliar')]",
            "//div[@role='button' and contains(., 'Escrever uma avaliação')]",
            "//button[contains(@jsaction, 'review')]",
            "//button[contains(@jsaction, 'writeReview')]"
        ]

        for attempt in range(4):
            # Primeiro re-verifica se apareceu 'Editar avaliação'
            if self._check_if_already_reviewed(driver, log):
                return

            for sel in selectors:
                try:
                    elements = driver.find_elements(By.XPATH, sel)
                    for el in elements:
                        if el.is_displayed():
                            # Se for o botão Editar avaliação, não clicar aqui
                            if "Editar" in el.text or "Edit" in el.text:
                                return
                            driver.execute_script("arguments[0].scrollIntoView(true);", el)
                            driver.execute_script("arguments[0].click();", el)
                            log(f"Botão 'Avaliar' acionado.")
                            return
                except Exception:
                    continue
            
            # Tenta rolar o painel lateral para baixo se o botão estiver mais abaixo
            try:
                driver.execute_script("""
                    const panel = document.querySelector("div[role='main']") || document.querySelector("div[role='region']") || document.body;
                    panel.scrollBy(0, 300);
                """)
            except Exception:
                pass
            time.sleep(1.5)

        raise RuntimeError("Não foi possível localizar o botão 'Avaliar'. Certifique-se de que a conta Google está conectada.")

    def _switch_to_review_frame(self, driver: webdriver.Chrome, log: Callable[[str], None]) -> bool:
        """Localiza e alterna para o iframe do widget de avaliação do Google Maps se existir."""
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        time.sleep(0.5)
        iframe_selectors = [
            "iframe[name*='goog-reviews-write-widget']",
            "iframe[src*='ReviewsService']",
            "iframe[src*='WriteW']",
            "iframe[name*='widget']",
            "iframe[src*='review']"
        ]

        for sel in iframe_selectors:
            try:
                iframes = driver.find_elements(By.CSS_SELECTOR, sel)
                for iframe in iframes:
                    if iframe.is_displayed():
                        driver.switch_to.frame(iframe)
                        log("Alternado com sucesso para o iframe do formulário de avaliação.")
                        return True
            except Exception:
                continue

        # Tenta qualquer iframe visível na página
        try:
            all_iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in all_iframes:
                try:
                    if iframe.is_displayed():
                        driver.switch_to.frame(iframe)
                        # Verifica se há radiogroup ou botão Postar dentro dele
                        radios = driver.find_elements(By.XPATH, "//*[@role='radiogroup'] | //*[@role='radio'] | //button[contains(., 'Postar')]")
                        if radios:
                            log("Iframe de avaliação identificado e selecionado.")
                            return True
                        driver.switch_to.default_content()
                except Exception:
                    driver.switch_to.default_content()
        except Exception:
            pass

        return False

    def _fill_five_stars(self, driver: webdriver.Chrome, log: Callable[[str], None]) -> bool:
        """Marca 5 estrelas em todas as seções de estrelas encontradas (Geral, Comida, Serviço, Ambiente)."""
        # Garante que estamos dentro do iframe correto ou no documento principal
        in_frame = self._switch_to_review_frame(driver, log)
        if not in_frame:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

        time.sleep(1)
        log("Atribuindo 5 estrelas na avaliação geral e em todas as categorias...")

        # 1. Clica usando Selenium ActionChains nos elementos de 5 estrelas
        star5_selectors = [
            "//div[@role='radiogroup']//div[@role='radio'][5]",
            "//div[@role='radiogroup']//*[@role='radio'][last()]",
            "//div[@role='radiogroup']//div[@data-rating='5']",
            "//div[@role='radio' and (@data-rating='5' or @aria-posinset='5' or contains(@aria-label, '5') or contains(@aria-label, 'Cinco') or contains(@aria-label, 'Excepcional'))]",
            "//*[@data-rating='5']"
        ]

        for sel in star5_selectors:
            try:
                elements = driver.find_elements(By.XPATH, sel)
                for el in elements:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                        time.sleep(0.2)
                        ActionChains(driver).move_to_element(el).pause(0.1).click().perform()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
            except Exception:
                continue

        time.sleep(1)

        # 2. Executa script JavaScript com PointerEvent e MouseEvent reais
        js_rate_script = """
        function clickStar(el) {
            if (!el) return false;
            try {
                el.scrollIntoView({block: 'center'});
                const rect = el.getBoundingClientRect();
                const cx = rect.left + (rect.width > 0 ? rect.width / 2 : 10);
                const cy = rect.top + (rect.height > 0 ? rect.height / 2 : 10);
                const opts = {
                    bubbles: true,
                    cancelable: true,
                    view: window,
                    clientX: cx,
                    clientY: cy,
                    pointerId: 1,
                    pointerType: 'mouse',
                    isPrimary: true,
                    button: 0,
                    buttons: 1
                };
                
                el.dispatchEvent(new PointerEvent('pointerover', opts));
                el.dispatchEvent(new MouseEvent('mouseover', opts));
                el.dispatchEvent(new PointerEvent('pointerenter', opts));
                el.dispatchEvent(new PointerEvent('pointerdown', opts));
                el.dispatchEvent(new MouseEvent('mousedown', opts));
                el.dispatchEvent(new PointerEvent('pointerup', opts));
                el.dispatchEvent(new MouseEvent('mouseup', opts));
                el.dispatchEvent(new MouseEvent('click', opts));
                el.click();
                return true;
            } catch(e) {
                return false;
            }
        }

        let clicked = 0;
        // Grupos de estrelas (Geral, Comida, Serviço, Ambiente)
        const groups = Array.from(document.querySelectorAll('div[role="radiogroup"], [data-rating-group]'));
        for (const g of groups) {
            const radios = Array.from(g.querySelectorAll('div[role="radio"], [data-rating]'));
            if (radios.length >= 5) {
                if (clickStar(radios[4])) clicked++;
            }
        }

        // Elementos diretos com 5 estrelas / Cinco estrelas / Excepcional
        const direct5 = Array.from(document.querySelectorAll('[aria-label*="Cinco"], [aria-label*="cinco"], [aria-label*="5 estrela"], [data-rating="5"], [aria-posinset="5"]'));
        for (const s of direct5) {
            if (clickStar(s)) clicked++;
        }

        return clicked;
        """

        try:
            total_clicks = driver.execute_script(js_rate_script)
            log(f"⭐ Script de estrelas concluído ({total_clicks} elementos marcados).")
        except Exception as e:
            log(f"Aviso JS estrelas: {e}")

        time.sleep(1)
        log("⭐ 5 estrelas selecionadas em todas as categorias.")
        return True

    def _click_post_button(self, driver: webdriver.Chrome, log: Callable[[str], None]):
        """Clica no botão 'Postar' / 'Publicar' no modal de avaliação."""
        log("Acionando o botão 'Postar'...")

        # Script JS para encontrar e acionar o botão Postar ativo
        js_post_script = """
        function triggerPost() {
            const buttons = Array.from(document.querySelectorAll('button, div[role="button"], span'));
            for (const b of buttons) {
                const txt = (b.textContent || b.innerText || '').trim();
                const aria = (b.getAttribute('aria-label') || '').trim();
                if (txt === 'Postar' || txt === 'Publicar' || aria === 'Postar' || aria === 'Publicar' || txt === 'Post') {
                    const targetBtn = b.closest('button') || b;
                    
                    targetBtn.scrollIntoView({block: 'center', inline: 'center'});
                    targetBtn.focus();
                    
                    const rect = targetBtn.getBoundingClientRect();
                    const cx = rect.left + rect.width / 2;
                    const cy = rect.top + rect.height / 2;
                    const opts = {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: cx,
                        clientY: cy,
                        pointerId: 1,
                        pointerType: 'mouse',
                        isPrimary: true,
                        button: 0,
                        buttons: 1
                    };
                    
                    targetBtn.dispatchEvent(new PointerEvent('pointerover', opts));
                    targetBtn.dispatchEvent(new MouseEvent('mouseover', opts));
                    targetBtn.dispatchEvent(new PointerEvent('pointerdown', opts));
                    targetBtn.dispatchEvent(new MouseEvent('mousedown', opts));
                    targetBtn.dispatchEvent(new PointerEvent('pointerup', opts));
                    targetBtn.dispatchEvent(new MouseEvent('mouseup', opts));
                    targetBtn.dispatchEvent(new MouseEvent('click', opts));
                    targetBtn.click();
                    return true;
                }
            }
            return false;
        }
        return triggerPost();
        """

        # Tenta acionar dentro do iframe atual
        for attempt in range(4):
            try:
                clicked = driver.execute_script(js_post_script)
                if clicked:
                    log("Botão 'Postar' acionado com sucesso.")
                    return
            except Exception:
                pass

            # XPath alternativo dentro do contexto atual
            post_selectors = [
                "//button[contains(., 'Postar')]",
                "//button[contains(., 'Publicar')]",
                "//span[text()='Postar']/ancestor::button",
                "//span[text()='Publicar']/ancestor::button",
                "//span[contains(text(), 'Postar')]/ancestor::button",
                "//span[contains(text(), 'Publicar')]/ancestor::button",
                "//div[@role='button' and contains(., 'Postar')]"
            ]
            for sel in post_selectors:
                try:
                    buttons = driver.find_elements(By.XPATH, sel)
                    for btn in buttons:
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            try:
                                ActionChains(driver).move_to_element(btn).pause(0.1).click().perform()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            log("Botão 'Postar' clicado.")
                            return
                except Exception:
                    continue

            time.sleep(1)

        # Se não encontrou no iframe atual, tenta no default_content
        try:
            driver.switch_to.default_content()
            driver.execute_script(js_post_script)
        except Exception:
            pass

        log("Botão 'Postar' processado.")

    def _wait_for_post_confirmation(self, driver: webdriver.Chrome, log: Callable[[str], None], timeout: int = 15) -> bool:
        """Aguarda a tela de confirmação de postagem ('Agradecemos sua postagem', 'Concluído', etc.) aparecer."""
        log("Aguardando confirmação da postagem do Google ('Agradecemos sua postagem')...")
        start_time = time.time()
        
        confirmation_indicators = [
            "//*[contains(text(), 'Agradecemos sua postagem')]",
            "//*[contains(text(), 'Agradecemos sua contribuição')]",
            "//*[contains(text(), 'Agradecemos')]",
            "//*[contains(text(), 'agradecemos')]",
            "//button[contains(., 'Concluído')]",
            "//button[contains(., 'Done')]",
            "//*[contains(text(), 'pontos de Local Guide')]",
            "//*[contains(text(), 'Editar avaliação')]"
        ]

        while time.time() - start_time < timeout:
            for ind in confirmation_indicators:
                try:
                    elements = driver.find_elements(By.XPATH, ind)
                    for el in elements:
                        if el.is_displayed():
                            txt = el.text.strip()
                            log(f"✅ Confirmação pós-postagem detectada na tela: '{txt[:40]}...'")
                            time.sleep(2)  # Dá tempo para a tela renderizar completamente
                            return True
                except Exception:
                    pass

            # Verifica se o modal de escrita ainda está aberto e com o botão Postar visível
            try:
                review_dialog = driver.find_elements(By.XPATH, "//textarea[contains(@placeholder, 'experiência')] | //div[contains(text(), 'Conte como foi')]")
                post_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Postar') or contains(., 'Publicar')]")
                
                # Se o formulário de escrita sumiu e voltamos à tela do Maps, a postagem foi aceita
                if not any(d.is_displayed() for d in review_dialog) and not any(b.is_displayed() for b in post_btns):
                    log("Formulário de avaliação fechado com sucesso após postagem.")
                    time.sleep(2)
                    return True
            except Exception:
                pass

            time.sleep(0.8)

        log("⚠️ Tempo limite: Nenhuma confirmação de postagem detectada na tela.")
        return False

    def _click_done_button(self, driver: webdriver.Chrome, log: Callable[[str], None]):
        """Clica no botão 'Concluído' se aparecer no modal de pontuação."""
        try:
            done_selectors = [
                "//button[contains(., 'Concluído')]",
                "//button[contains(., 'Done')]",
                "//span[contains(text(), 'Concluído')]/ancestor::button",
                "//div[@role='button' and contains(., 'Concluído')]"
            ]
            for sel in done_selectors:
                btns = driver.find_elements(By.XPATH, sel)
                for b in btns:
                    if b.is_displayed():
                        driver.execute_script("arguments[0].click();", b)
                        log("Modal de agradecimento fechado com 'Concluído'.")
                        return
        except Exception:
            pass

    def _take_screenshot(self, driver: webdriver.Chrome, prefix: str = "avaliacao_") -> str:
        """Tira print da tela inteira do navegador e salva na pasta prints/."""
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}{timestamp}.png"
        filepath = os.path.join(self.prints_dir, filename)
        driver.save_screenshot(filepath)
        return filepath

    def close(self):
        """Encerra o driver."""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
        except Exception:
            pass
