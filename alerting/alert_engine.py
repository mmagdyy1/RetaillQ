"""
RetailIQ Alerting Engine
=========================
Reads HIGH severity anomalies from Snowflake
and sends email alerts via Gmail.
"""

import snowflake.connector
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

SF_USER      = "MMAGDYY1"
SF_PASSWORD  = "Mohamed12345@#"
SF_ACCOUNT   = "kpvhttk-ir63402"
SF_DATABASE  = "RETAILQ"
SF_WAREHOUSE = "COMPUTE_WH"

EMAIL_SENDER   = "dinamuhanna46@gmail.com"
EMAIL_PASSWORD = "bamqoqdhxrmpboki"
EMAIL_RECEIVER = "dinamuhanna46@gmail.com"
SMTP_SERVER    = "smtp.gmail.com"
SMTP_PORT      = 587

def get_anomalies():
    print("Fetching HIGH severity anomalies...")
    conn = snowflake.connector.connect(
        user=SF_USER, password=SF_PASSWORD, account=SF_ACCOUNT,
        warehouse=SF_WAREHOUSE, database=SF_DATABASE, schema="GOLD"
    )
    df = pd.read_sql("""
        SELECT title, source, category, price, avg_cat_price,
               z_score, anomaly_type, severity, url, detected_at
        FROM RETAILQ.GOLD.PRICE_ANOMALIES
        WHERE severity = 'HIGH'
        ORDER BY ABS(z_score) DESC
        LIMIT 20
    """, conn)
    conn.close()
    df.columns = [c.lower() for c in df.columns]
    print(f"  Found {len(df)} HIGH severity anomalies.")
    return df

def build_email_html(df):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows_html = ""
    for _, r in df.iterrows():
        diff = round(((r["price"] - r["avg_cat_price"]) / r["avg_cat_price"]) * 100, 1)
        sign = "+" if diff > 0 else ""
        color = "#e74c3c" if diff > 0 else "#2ecc71"
        rows_html += f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #2a2d3e;max-width:280px">{str(r['title'])[:60]}...</td>
          <td style="padding:10px;border-bottom:1px solid #2a2d3e;text-align:center">{str(r['source']).capitalize()}</td>
          <td style="padding:10px;border-bottom:1px solid #2a2d3e;text-align:center">{r['category']}</td>
          <td style="padding:10px;border-bottom:1px solid #2a2d3e;text-align:right;font-weight:bold">EGP {r['price']:,.0f}</td>
          <td style="padding:10px;border-bottom:1px solid #2a2d3e;text-align:right;color:#9399b2">EGP {r['avg_cat_price']:,.0f}</td>
          <td style="padding:10px;border-bottom:1px solid #2a2d3e;text-align:center;color:{color};font-weight:bold">{sign}{diff}%</td>
          <td style="padding:10px;border-bottom:1px solid #2a2d3e;text-align:center">
            <a href="{r['url']}" style="color:#6C63FF">View</a>
          </td>
        </tr>
        """

    return f"""
    <html>
    <body style="background:#0f1117;color:#fff;font-family:Arial,sans-serif;padding:20px">
      <div style="max-width:900px;margin:0 auto">
        <div style="background:#1a1d27;border-radius:16px;padding:24px;margin-bottom:20px;border-left:4px solid #e74c3c">
          <h1 style="margin:0;font-size:1.5rem">🚨 RetailIQ — Price Anomaly Alert</h1>
          <p style="color:#9399b2;margin:6px 0 0">Detected at {now} · {len(df)} HIGH severity anomalies</p>
        </div>
        <div style="background:#1a1d27;border-radius:16px;overflow:hidden">
          <table style="width:100%;border-collapse:collapse;color:#fff">
            <thead>
              <tr style="background:#6C63FF">
                <th style="padding:12px;text-align:left">Product</th>
                <th style="padding:12px">Platform</th>
                <th style="padding:12px">Category</th>
                <th style="padding:12px;text-align:right">Price</th>
                <th style="padding:12px;text-align:right">Avg</th>
                <th style="padding:12px">Diff %</th>
                <th style="padding:12px">Link</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        <p style="text-align:center;color:#9399b2;font-size:.8rem;margin-top:16px">
          RetailIQ Automated Alerts · {now}
        </p>
      </div>
    </body>
    </html>
    """

def send_email(df):
    if df.empty:
        print("No HIGH anomalies — no email sent.")
        return
    print("Sending email...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚨 RetailIQ Alert — {len(df)} Price Anomalies Detected"
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg.attach(MIMEText(build_email_html(df), "html"))
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    print(f"  Email sent to {EMAIL_RECEIVER} ✅")

def run():
    df = get_anomalies()
    send_email(df)
    print("Alerting Engine Done!")

run()
