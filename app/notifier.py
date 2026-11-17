import html
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from sqlalchemy.orm import Session
from app.database import SMTPSetting

logger = logging.getLogger(__name__)


def send_email(smtp_config: SMTPSetting, subject: str, body_html: str, body_text: str = ""):
    """Dispatches email using specified SMTP settings."""
    if not smtp_config.host or not smtp_config.recipient_email:
        raise ValueError("SMTP host or recipient email is not configured.")

    sender = smtp_config.sender_email or smtp_config.username or "no-reply@spirit-tracker.local"
    recipient = smtp_config.recipient_email

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    if body_text:
        msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    host = smtp_config.host
    port = int(smtp_config.port or 587)

    logger.info(f"Connecting to SMTP server {host}:{port}...")

    if smtp_config.use_ssl:
        server = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        server = smtplib.SMTP(host, port, timeout=15)

    try:
        server.ehlo()
        if smtp_config.use_tls and not smtp_config.use_ssl:
            server.starttls()
            server.ehlo()

        if smtp_config.username and smtp_config.password:
            server.login(smtp_config.username, smtp_config.password)

        server.sendmail(sender, [recipient], msg.as_string())
        logger.info(f"Email successfully sent to {recipient}")
    finally:
        try:
            server.quit()
        except Exception:
            pass


def notify_stock_alert(db: Session, product_title: str, price: str, url: str, retailer: str):
    """Sends alert email when a product becomes IN STOCK."""
    smtp_config = db.query(SMTPSetting).filter(SMTPSetting.id == 1).first()
    if not smtp_config or not smtp_config.host or not smtp_config.recipient_email:
        logger.warning("Stock alert skipped: SMTP configuration incomplete.")
        return False, "SMTP server not configured."

    subject = f"🥃 IN STOCK ALERT: {product_title}!"
    safe_title = html.escape(str(product_title or ""))
    safe_retailer = html.escape(str(retailer or "").upper())
    safe_price = html.escape(str(price or "N/A"))
    safe_url = str(url or "").strip()
    if not safe_url.startswith(("http://", "https://")):
        safe_url = "#"
    safe_url_attr = html.escape(safe_url, quote=True)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px; }}
            .card {{ background-color: #1e293b; border-radius: 12px; padding: 24px; max-width: 600px; margin: 0 auto; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            .header {{ font-size: 22px; font-weight: bold; color: #fbbf24; margin-bottom: 16px; border-bottom: 2px solid #334155; padding-bottom: 12px; }}
            .title {{ font-size: 18px; color: #f1f5f9; margin-bottom: 12px; }}
            .detail {{ font-size: 15px; color: #94a3b8; margin-bottom: 8px; }}
            .price {{ font-size: 20px; font-weight: bold; color: #4ade80; margin: 12px 0; }}
            .btn {{ display: inline-block; background: linear-gradient(135deg, #d97706, #f59e0b); color: #090d16 !important; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; margin-top: 16px; }}
            .footer {{ font-size: 12px; color: #64748b; margin-top: 24px; border-top: 1px solid #334155; padding-top: 12px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">🥃 Spirit Tracker Alert</div>
            <div class="title"><strong>{safe_title}</strong> is now <strong>IN STOCK</strong>!</div>
            <div class="detail"><strong>Retailer:</strong> {safe_retailer}</div>
            <div class="price">Price: {safe_price}</div>
            <a href="{safe_url_attr}" target="_blank" rel="noopener noreferrer" class="btn">View &amp; Purchase Item</a>
            <div class="footer">Sent automatically by your self-hosted Spirit Tracker &amp; Scraper.</div>
        </div>
    </body>
    </html>
    """

    text_content = f"IN STOCK ALERT!\n\nProduct: {product_title}\nRetailer: {retailer}\nPrice: {price}\nLink: {url}\n"

    try:
        send_email(smtp_config, subject, html_content, text_content)
        return True, "Alert email dispatched successfully!"
    except Exception as e:
        logger.error(f"Failed to send stock alert email: {e}")
        return False, str(e)


def send_test_email(db: Session):
    """Sends a test email to verify SMTP credentials."""
    smtp_config = db.query(SMTPSetting).filter(SMTPSetting.id == 1).first()
    if not smtp_config or not smtp_config.host or not smtp_config.recipient_email:
        raise ValueError("SMTP host and recipient email are required to send a test email.")

    subject = "🧪 Spirit Tracker - Test Email Notification"
    html_content = """
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px;">
        <div style="background-color: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #334155; max-width: 500px;">
            <h2 style="color: #4ade80; margin-top: 0;">✅ SMTP Test Successful!</h2>
            <p>Your SMTP settings on <strong>Spirit Tracker & Scraper</strong> are properly configured.</p>
            <p style="color: #94a3b8; font-size: 14px;">You will now receive email notifications whenever monitored bourbons become in stock.</p>
        </div>
    </body>
    </html>
    """
    text_content = "SMTP Test Successful! Your Spirit Tracker email settings are working properly."

    send_email(smtp_config, subject, html_content, text_content)
    return True
