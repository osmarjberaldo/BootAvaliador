# 🚀 Boot Avaliador - Telegram Link Monitor & Avaliador 5★ Google Maps

Aplicativo desktop com interface gráfica moderna em **CustomTkinter**, **Telethon** e **Selenium** para monitorar links do Telegram em tempo real e **avaliar automaticamente com 5 estrelas no Google Maps**, postar e salvar o print da confirmação na pasta `prints/`.

---

## 📋 Como Funciona a Avaliação Automática

1. **Primeira Inicialização (Login Google)**:
   - Na barra lateral do aplicativo, clique no botão **`🌐 Abrir Chrome (Login Google)`**.
   - Faça login na sua conta Google normalmente uma única vez. A sessão ficará salva de forma permanente na pasta [`chrome_profile/`](chrome_profile/).
2. **Monitoramento e Avaliação em Tempo Real**:
   - Assim que o grupo do Telegram recebe um link do Google Maps, o robô:
     1. Abre o local no Google Maps.
     2. Lida com avisos de cookies caso existam.
     3. Clica na aba **"Avaliações"**.
     4. Clica no botão **"Avaliar"** (ou **"Editar avaliação"** se já avaliado antes).
     5. Marca **5 estrelas** na nota geral e em todas as categorias secundárias (Comida, Serviço, Ambiente).
     6. Clica em **"Postar"** / **"Publicar"**.
     7. Aguarda o popup de confirmação de pontos (`+4 pontos`).
     8. Tira print da tela inteira e salva com data/hora em [`prints/`](prints/).
3. **Acesso aos Prints**:
   - No card do link na interface, clique em **`📸 Ver Print`** para abrir o screenshot diretamente.
   - Ou clique em **`📂 Abrir Pasta de Prints`** na barra lateral para ver todas as imagens.

---

## 🛠️ Instalação e Como Executar

### 1. Pré-requisitos
Certifique-se de ter o Python 3.8+ instalado e o Google Chrome instalado no computador.

### 2. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 3. Iniciar o Aplicativo
```bash
python main.py
```
ou
```bash
python gui.py
```

---

## ⚙️ Arquivo de Configuração (`config.json`)

```json
{
    "api_id": "12345678",
    "api_hash": "abcdef0123456789abcdef0123456789",
    "phone": "+5511999998888",
    "auto_open_links": false,
    "ignore_duplicates": true,
    "fetch_today_history": true,
    "last_selected_group_id": null,
    "target_recipient_id": 1538766525,
    "target_recipient_name": "[Contato] Helena Da Silva",
    "auto_send_screenshot": true,
    "evaluated_links": {}
}
```

---

## 🧪 Regra Obrigatória de Testes e Validação

Antes de qualquer conclusão ou entrega de alterações no projeto, execute obrigatoriamente os seguintes passos de validação:

1. **Compilação e Verificação de Sintaxe**:
   ```bash
   python -m py_compile maps_evaluator.py gui.py config_manager.py telegram_service.py link_handler.py
   ```

2. **Execução da Suíte de Testes Automatizados**:
   ```bash
   python test_modules.py
   ```
   *(Todos os testes devem passar com `OK`)*.

3. **Verificação de Regras de Negócio**:
   - `Limpar Lista`: Apaga os cards da interface, zera `evaluated_links` no `config.json` e **deleta todos os arquivos da pasta `prints/`** para não acumular imagens no disco.
   - `Virada de Dia (Rollover)`: Remove links e arquivos de print de dias anteriores ao iniciar o aplicativo.
   - `🌙 Limpeza Automática Noturna (21:00)`: A partir das 21:00, o sistema realiza automaticamente a limpeza geral de todos os prints da pasta `prints/` e zera o histórico de links do dia caso ainda não tenham sido limpos.
   - `Envio de Prints`: Envia apenas a foto limpa sem texto para o contato selecionado, sem repetições para locais já avaliados anteriormente.
   - `Confirmação de Post`: Só gera print e só envia comprovante se a postagem no Google Maps for confirmada.


