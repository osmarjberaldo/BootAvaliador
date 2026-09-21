import os
import unittest
from config_manager import save_credentials, load_credentials
from link_handler import LinkHandler

class TestBootAvaliador(unittest.TestCase):
    def test_json_save_and_load(self):
        test_json = "test_config.json"
        saved = save_credentials("999888", "hash12345", "+5511988887777", json_path=test_json)
        self.assertTrue(saved)
        
        creds = load_credentials(json_path=test_json)
        self.assertEqual(creds["api_id"], "999888")
        self.assertEqual(creds["api_hash"], "hash12345")
        self.assertEqual(creds["phone"], "+5511988887777")
        
        if os.path.exists(test_json):
            os.remove(test_json)

    def test_auto_migration_from_txt_to_json(self):
        test_txt = "test_legacy_creds.txt"
        test_json = "test_migrated_config.json"

        # Cria TXT legado
        with open(test_txt, "w", encoding="utf-8") as f:
            f.write("API_ID=112233\nAPI_HASH=my_hash_abc\nPHONE=+5544999990000\n")

        # Chama load_credentials passando os caminhos de teste
        creds = load_credentials(json_path=test_json, txt_path=test_txt)
        
        # Verifica se os dados foram migrados com sucesso
        self.assertEqual(creds["api_id"], "112233")
        self.assertEqual(creds["api_hash"], "my_hash_abc")
        self.assertEqual(creds["phone"], "+5544999990000")
        self.assertTrue(os.path.exists(test_json))

        # Limpeza
        if os.path.exists(test_txt):
            os.remove(test_txt)
        if os.path.exists(test_json):
            os.remove(test_json)

    def test_link_extraction(self):
        handler = LinkHandler()
        sample_text = (
            "Olá pessoal! Confiram a nova oferta em https://example.com/item123 e também "
            "no link http://promocao.com/teste. Link telegram: t.me/meugrupo ou www.google.com/search?q=teste"
        )
        links = handler.extract_links(sample_text)
        self.assertIn("https://example.com/item123", links)
        self.assertIn("http://promocao.com/teste", links)
        self.assertTrue(any("google.com" in l for l in links))
        self.assertTrue(any("t.me" in l for l in links))

        # Testa rejeição de mensagens com pontuação de frase, horários e emojis (falsos positivos)
        false_positive_text = (
            "O pedido de hoje foi concluído.Por favor, todos entrem em contato com seus "
            "respectivos recepcionistas amanhã entre 9h e 9.30h para receber a recompensa de R$10 pelo check-in! Boa noite 💫💫💫"
        )
        false_links = handler.extract_links(false_positive_text)
        self.assertEqual(len(false_links), 0)

    def test_evaluated_links_tracking(self):
        test_json = "test_eval_config.json"
        from config_manager import save_evaluated_link, is_link_evaluated, get_evaluated_link_info
        
        sample_url = "https://maps.app.goo.gl/qtv3bFPPh8YR1wGh8"
        self.assertFalse(is_link_evaluated(sample_url, json_path=test_json))

        saved = save_evaluated_link(sample_url, screenshot_path="prints/test_print.png", status="avaliado", json_path=test_json)
        self.assertTrue(saved)
        self.assertTrue(is_link_evaluated(sample_url, json_path=test_json))
        self.assertTrue(is_link_evaluated("https://maps.app.goo.gl/qtv3bFPPh8YR1wGh8/", json_path=test_json))

        info = get_evaluated_link_info(sample_url, json_path=test_json)
        self.assertIsNotNone(info)
        self.assertEqual(info.get("status"), "avaliado")

        if os.path.exists(test_json):
            os.remove(test_json)

    def test_daily_rollover_cleanup(self):
        test_json = "test_rollover_config.json"
        from config_manager import save_evaluated_link, cleanup_old_evaluated_links, is_link_evaluated, clear_all_evaluated_links
        import json
        import datetime

        # Datas dinâmicas: ontem e hoje relativos à data real (evita falha quando a data muda)
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        today_prefix = today.strftime("%Y-%m-%d")
        date_ontem = yesterday.strftime("%Y-%m-%d") + " 10:00:00"
        date_hoje = today.strftime("%Y-%m-%d") + " 09:00:00"

        # Insere dados de ontem e de hoje
        cfg = {
            "evaluated_links": {
                "maps.app.goo.gl/link_ontem": {
                    "url": "https://maps.app.goo.gl/link_ontem",
                    "date": date_ontem,
                    "screenshot_path": "prints/ontem.png",
                    "status": "avaliado"
                },
                "maps.app.goo.gl/link_hoje": {
                    "url": "https://maps.app.goo.gl/link_hoje",
                    "date": date_hoje,
                    "screenshot_path": "prints/hoje.png",
                    "status": "avaliado"
                }
            }
        }
        with open(test_json, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        # Executa limpeza considerando a data de hoje como referência
        removed = cleanup_old_evaluated_links(json_path=test_json, reference_date=today_prefix)
        self.assertEqual(removed, 1)
        self.assertFalse(is_link_evaluated("https://maps.app.goo.gl/link_ontem", json_path=test_json))
        self.assertTrue(is_link_evaluated("https://maps.app.goo.gl/link_hoje", json_path=test_json))

        # Testa limpeza total com deleção de prints
        cleared = clear_all_evaluated_links(json_path=test_json, delete_prints=False)
        self.assertTrue(cleared)
        self.assertFalse(is_link_evaluated("https://maps.app.goo.gl/link_hoje", json_path=test_json))

        if os.path.exists(test_json):
            os.remove(test_json)

    def test_prints_folder_and_nightly_cleanup(self):
        import shutil
        from config_manager import cleanup_prints_folder, check_and_run_nightly_cleanup, save_config

        test_prints_dir = "test_prints_tmp"
        test_json = "test_nightly_config.json"
        os.makedirs(test_prints_dir, exist_ok=True)

        # Cria arquivos dummy na pasta de prints
        dummy_file1 = os.path.join(test_prints_dir, "print1.png")
        dummy_file2 = os.path.join(test_prints_dir, "print2.jpg")
        with open(dummy_file1, "w") as f:
            f.write("fake img")
        with open(dummy_file2, "w") as f:
            f.write("fake img")

        # Testa cleanup_prints_folder
        deleted = cleanup_prints_folder(prints_dir=test_prints_dir)
        self.assertEqual(deleted, 2)
        self.assertEqual(len(os.listdir(test_prints_dir)), 0)

        # Cria novos prints e dados para testar check_and_run_nightly_cleanup
        with open(dummy_file1, "w") as f:
            f.write("fake img 1")
        save_config({
            "evaluated_links": {"maps.app.goo.gl/abc": {"url": "https://maps.app.goo.gl/abc"}},
            "last_nightly_cleanup": ""
        }, json_path=test_json)

        # Força target_hour=0 para disparar a limpeza
        res = check_and_run_nightly_cleanup(json_path=test_json, prints_dir=test_prints_dir, target_hour=0)
        self.assertTrue(res.get("cleaned"))
        self.assertEqual(res.get("prints_deleted"), 1)
        self.assertEqual(len(os.listdir(test_prints_dir)), 0)

        # Limpeza
        if os.path.exists(test_prints_dir):
            shutil.rmtree(test_prints_dir)
        if os.path.exists(test_json):
            os.remove(test_json)

if __name__ == "__main__":
    unittest.main()


