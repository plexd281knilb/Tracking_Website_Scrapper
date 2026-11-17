import atexit
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TEMP_DIR = tempfile.mkdtemp(prefix="spirit_tracker_test_")
os.environ["DATA_DIR"] = _TEMP_DIR
atexit.register(lambda: shutil.rmtree(_TEMP_DIR, ignore_errors=True))

from fastapi.testclient import TestClient

from app.database import init_db, SessionLocal, SMTPSetting
from app.main import app
from app.notifier import notify_stock_alert
from app.scrapers.base import is_safe_public_url


class TestSpiritTrackerSecurityAndUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_01_isolated_wal_db_and_public_routes(self):
        db_file = Path(_TEMP_DIR) / "track_bourbon.db"
        self.assertTrue(db_file.exists(), "Tests must use isolated temporary DATA_DIR")
        conn = sqlite3.connect(db_file)
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal")

        res_home = self.client.get("/")
        self.assertEqual(res_home.status_code, 200)
        res_fav = self.client.get("/favicon.svg")
        self.assertEqual(res_fav.status_code, 200)
        self.assertIn("image/svg+xml", res_fav.headers.get("content-type", ""))

    def test_02_ssrf_and_tracker_url_validation(self):
        self.assertFalse(is_safe_public_url("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(is_safe_public_url("http://127.0.0.1:8080/admin"))
        self.assertFalse(is_safe_public_url("file:///etc/passwd"))

        bad_tracker = self.client.post(
            "/api/trackers",
            json={
                "name": "Metadata Probe",
                "retailer": "custom",
                "url": "http://169.254.169.254/latest/meta-data/",
            },
        )
        self.assertEqual(bad_tracker.status_code, 400)
        self.assertIn("no-store", bad_tracker.headers.get("cache-control", ""))

    def test_03_smtp_password_redaction_and_preservation(self):
        save_res = self.client.post(
            "/api/smtp",
            json={
                "host": "smtp.example.com",
                "port": 587,
                "username": "alerts@example.com",
                "password": "super-secret-smtp-password",
                "recipient_email": "owner@example.com",
            },
        )
        self.assertEqual(save_res.status_code, 200)

        get_res = self.client.get("/api/smtp")
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertEqual(data["password"], "")
        self.assertTrue(data["has_password"])
        self.assertIn("no-store", get_res.headers.get("cache-control", ""))

        # Re-saving without password preserves stored secret
        self.client.post(
            "/api/smtp",
            json={
                "host": "smtp.example.com",
                "port": 587,
                "username": "alerts@example.com",
                "password": "",
                "recipient_email": "owner@example.com",
            },
        )
        db = SessionLocal()
        try:
            row = db.query(SMTPSetting).filter(SMTPSetting.id == 1).first()
            self.assertEqual(row.password, "super-secret-smtp-password")
        finally:
            db.close()

    def test_04_optional_api_token_gating(self):
        with patch.dict(os.environ, {"SCRAPER_API_TOKEN": "top-secret-token-value"}):
            unauth = self.client.get("/api/smtp")
            self.assertEqual(unauth.status_code, 401)
            wrong = self.client.get("/api/smtp", headers={"Authorization": "Bearer wrong"})
            self.assertEqual(wrong.status_code, 401)
            authed = self.client.get("/api/smtp", headers={"Authorization": "Bearer top-secret-token-value"})
            self.assertEqual(authed.status_code, 200)

    def test_05_notifier_html_escaping_and_safe_href(self):
        captured = {}

        def fake_send(_cfg, subject, body_html, _text=""):
            captured["html"] = body_html

        db = SessionLocal()
        try:
            with patch("app.notifier.send_email", side_effect=fake_send):
                ok, _ = notify_stock_alert(
                    db=db,
                    product_title='<script>alert("xss")</script>',
                    price='$49.99" onclick="evil()',
                    url="javascript:alert(1)",
                    retailer="custom<img src=x>",
                )
            self.assertTrue(ok)
            self.assertNotIn("<script>", captured["html"])
            self.assertIn("&lt;script&gt;", captured["html"])
            self.assertNotIn("javascript:alert", captured["html"])
        finally:
            db.close()

    def test_06_tls_verification_and_responsive_light_dark_ui(self):
        root = Path(__file__).resolve().parent.parent
        for py_file in (root / "app" / "scrapers").glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            self.assertNotIn("verify=False", content, f"{py_file.name} must verify TLS certificates")

        html_doc = (root / "app" / "templates" / "index.html").read_text(encoding="utf-8")
        css_doc = (root / "app" / "static" / "css" / "style.css").read_text(encoding="utf-8")
        js_doc = (root / "app" / "static" / "js" / "main.js").read_text(encoding="utf-8")

        self.assertIn("viewport-fit=cover", html_doc)
        self.assertIn("/favicon.svg", html_doc)
        self.assertIn('[data-theme="light"]', css_doc)
        self.assertIn("-webkit-backdrop-filter", css_doc)
        self.assertIn("100dvh", css_doc)
        self.assertIn("font-size: 16px !important", css_doc)
        self.assertIn("spirit_tracker_theme", js_doc)
        self.assertIn("safeHttpUrl", js_doc)
        self.assertIn("&#39;", js_doc)


if __name__ == "__main__":
    unittest.main()
