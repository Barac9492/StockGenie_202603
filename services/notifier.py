import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config.settings import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO
from services.signal_generator import get_todays_signals


def compose_digest_html(signals: list[dict]) -> str:
    """Compose the daily email digest as HTML."""
    date_str = datetime.now().strftime("%Y-%m-%d")

    buy_signals = [s for s in signals if s["signal_type"] == "BUY"]
    sell_signals = [s for s in signals if s["signal_type"] == "SELL"]

    rows_html = ""
    for s in signals:
        color = "#00D26A" if s["signal_type"] == "BUY" else "#FF4B4B"
        rows_html += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #333">{s['ticker']}</td>
            <td style="padding:8px;border-bottom:1px solid #333;color:{color};font-weight:bold">{s['signal_type']}</td>
            <td style="padding:8px;border-bottom:1px solid #333">{s.get('strategy_name', '-')}</td>
            <td style="padding:8px;border-bottom:1px solid #333">{s.get('price', '-'):,.0f}</td>
        </tr>
        """

    html = f"""
    <html>
    <body style="background:#0E1117;color:#FAFAFA;font-family:sans-serif;padding:24px">
        <h1 style="color:#636EFA">QuantRadar Daily Digest</h1>
        <p style="color:#A3A8B8">{date_str} | {len(buy_signals)} BUY, {len(sell_signals)} SELL signals</p>
        <table style="width:100%;border-collapse:collapse;margin-top:16px">
            <tr style="border-bottom:2px solid #636EFA">
                <th style="padding:8px;text-align:left">Ticker</th>
                <th style="padding:8px;text-align:left">Signal</th>
                <th style="padding:8px;text-align:left">Strategy</th>
                <th style="padding:8px;text-align:left">Price</th>
            </tr>
            {rows_html if rows_html else '<tr><td colspan="4" style="padding:16px;color:#A3A8B8">No signals today</td></tr>'}
        </table>
        <p style="color:#A3A8B8;margin-top:24px;font-size:14px">
            Open QuantRadar to review and act on these signals.
        </p>
    </body>
    </html>
    """
    return html


def send_digest():
    """Fetch today's signals and send email digest."""
    if not SMTP_USER or not EMAIL_TO:
        return False

    signals = get_todays_signals()
    html = compose_digest_html(signals)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"QuantRadar — {datetime.now().strftime('%Y-%m-%d')} Daily Digest"
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())

    return True
