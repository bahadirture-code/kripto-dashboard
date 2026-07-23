from flask import Flask, jsonify, render_template_string
import requests

app = Flask(__name__)

# Canlı verileri CoinGecko API üzerinden çeken ve sinyal üreten fonksiyon
def get_crypto_signals():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,arbitrum,optimism&vs_currencies=usd&include_24hr_change=true"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
    except:
        data = {}

    # Örnek varlık verilerini dinamik olarak haritalama
    assets = [
        {
            "name": "Bitcoin (BTC)",
            "id": "bitcoin",
            "score": "88/100",
            "tech": "Destek Seviyesinde / Trend Güçlü"
        },
        {
            "name": "Ethereum (ETH)",
            "id": "ethereum",
            "score": "82/100",
            "tech": "Yükselen Kanal Akışı"
        },
        {
            "name": "Solana (SOL)",
            "id": "solana",
            "score": "85/100",
            "tech": "Yüksek Ağ Aktivitesi"
        },
        {
            "name": "Arbitrum (ARB)",
            "id": "arbitrum",
            "score": "74/100",
            "tech": "Aşırı Satım / Değer Bölgesi"
        }
    ]

    result = []
    for asset in assets:
        coin_info = data.get(asset["id"], {"usd": 0, "usd_24h_change": 0})
        price = coin_info.get("usd", 0)
        change = coin_info.get("usd_24h_change", 0)

        # Basit kural tabanlı Al/Sat/Tut sinyal algoritması
        if change > 2.5:
            signal, signal_type = "AL", "buy"
        elif change < -2.5:
            signal, signal_type = "SAT", "sell"
        else:
            signal, signal_type = "TUT", "hold"

        result.append({
            "name": asset["name"],
            "price": f"${price:,.2f}",
            "change": f"{change:+.2f}%",
            "score": asset["score"],
            "tech": asset["tech"],
            "signal": signal,
            "type": signal_type
        })
        
    return result

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bulut Kripto Sinyal Paneli</title>
    <style>
        :root { --bg: #0f172a; --card: #1e293b; --text: #f8fafc; --muted: #94a3b8; --accent: #38bdf8; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 20px; }
        header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 15px; margin-bottom: 25px; }
        h1 { margin: 0; color: var(--accent); font-size: 22px; }
        .card { background-color: var(--card); border-radius: 12px; padding: 20px; border: 1px solid #334155; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 14px; text-align: left; border-bottom: 1px solid #334155; }
        th { background-color: #111827; color: var(--muted); font-size: 12px; text-transform: uppercase; }
        .badge { padding: 5px 10px; border-radius: 6px; font-weight: bold; font-size: 12px; }
        .badge-buy { background: rgba(34,197,94,0.2); color: #22c55e; border: 1px solid #22c55e; }
        .badge-sell { background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid #ef4444; }
        .badge-hold { background: rgba(245,158,11,0.2); color: #f59e0b; border: 1px solid #f59e0b; }
    </style>
</head>
<body>
    <header>
        <h1>☁️ Bulut Tabanlı Canlı Kripto Dashboard</h1>
        <span style="color: #22c55e; font-weight: bold;">● Canlı Sistem Aktif</span>
    </header>

    <div class="card">
        <h3>Piyasa Öngörüleri ve Anlık Sinyaller</h3>
        <table>
            <thead>
                <tr>
                    <th>Varlık</th>
                    <th>Anlık Fiyat</th>
                    <th>24s Değişim</th>
                    <th>Gelecek Skoru</th>
                    <th>Teknik Durum</th>
                    <th>Stratejik Sinyal</th>
                </tr>
            </thead>
            <tbody>
                {% for item in cryptos %}
                <tr>
                    <td><strong>{{ item.name }}</strong></td>
                    <td>{{ item.price }}</td>
                    <td style="color: {{ '#22c55e' if '+' in item.change else '#ef4444' }}">{{ item.change }}</td>
                    <td>{{ item.score }}</td>
                    <td>{{ item.tech }}</td>
                    <td><span class="badge badge-{{ item.type }}">{{ item.signal }}</span></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    cryptos = get_crypto_signals()
    return render_template_string(HTML_TEMPLATE, cryptos=cryptos)

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)