from flask import Flask, render_template_string
import requests
import os

app = Flask(__name__)

def scan_volume_breakouts():
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=volume_desc&per_page=30&page=1&sparkline=false&price_change_percentage=24h"
    try:
        response = requests.get(url, timeout=5)
        coins = response.json()
    except:
        coins = []

    opportunities = []

    for coin in coins:
        name = coin.get("name")
        symbol = coin.get("symbol", "").upper()
        price = coin.get("current_price", 0)
        change_24h = coin.get("price_change_percentage_24h", 0) or 0
        volume = coin.get("total_volume", 0)
        market_cap = coin.get("market_cap", 1)

        volume_to_cap = volume / market_cap if market_cap > 0 else 0

        # Esnetilmiş ve akıllı skorlama mantığı
        if change_24h > 2.0:
            signal = "VOLATİL ATAK (AL)"
            badge = "buy"
            reason = "Yukarı yönlü ivmelenme ve hacim desteği."
        elif change_24h < -2.0:
            signal = "DİP FIRSATI"
            badge = "hold"
            reason = "Geri çekilme bölgesinde tepki arayışı."
        else:
            signal = "İzleme Listesi"
            badge = "hold"
            reason = "Yatay seyir, kırılım bekleniyor."

        opportunities.append({
            "name": f"{name} ({symbol})",
            "price": f"${price:,.2f}" if price > 1 else f"${price:.5f}",
            "change": f"{change_24h:+.2f}%",
            "change_val": change_24h,
            "volume": f"${volume:,.0f}",
            "ratio": f"{volume_to_cap:.2f}",
            "reason": reason,
            "signal": signal,
            "badge": badge
        })

    # Liste yine de boş kalırsa statik güçlü yedek oluştur
    if not opportunities:
        opportunities.append({
            "name": "Piyasa Verisi Bekleniyor",
            "price": "$0.00",
            "change": "+0.00%",
            "change_val": 0,
            "volume": "$0",
            "ratio": "0.00",
            "reason": "API bağlantısı güncelleniyor.",
            "signal": "BEKLE",
            "badge": "hold"
        })

    return opportunities

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hacim Patlaması & Atak Tarayıcısı</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #38bdf8;
            --buy-color: #22c55e;
            --sell-color: #ef4444;
            --hold-color: #f59e0b;
            --border-color: #334155;
        }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 20px; }
        header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 15px; margin-bottom: 25px; }
        h1 { margin: 0; color: var(--accent-blue); font-size: 22px; }
        .card { background-color: var(--card-bg); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 14px; text-align: left; border-bottom: 1px solid var(--border-color); }
        th { background-color: #111827; color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
        tr:hover { background-color: rgba(56, 189, 248, 0.05); }
        .badge { padding: 6px 12px; border-radius: 6px; font-weight: bold; font-size: 11px; display: inline-block; text-align: center; }
        .badge-buy { background: rgba(34,197,94,0.2); color: var(--buy-color); border: 1px solid var(--buy-color); }
        .badge-sell { background: rgba(239,68,68,0.2); color: var(--sell-color); border: 1px solid var(--sell-color); }
        .badge-hold { background: rgba(245,158,11,0.2); color: var(--hold-color); border: 1px solid var(--hold-color); }
    </style>
</head>
<body>
    <header>
        <h1>🚀 Kısa Vade Hacim Patlaması & Atak Tarayıcısı</h1>
        <span style="color: #22c55e; font-weight: bold; font-size: 13px;">● Canlı Momentom Taraması Aktif</span>
    </header>

    <div class="card">
        <h3 style="margin-top:0; color: var(--text-muted);">Anlık Hacim Alan ve Hızla Yükselen Varlıklar</h3>
        <table>
            <thead>
                <tr>
                    <th>Varlık</th>
                    <th>Fiyat</th>
                    <th>24s Değişim</th>
                    <th>Toplam Hacim</th>
                    <th>Hacim / Değer Oranı</th>
                    <th>Algoritma Gerekçesi</th>
                    <th>Aksiyon Sinyali</th>
                </tr>
            </thead>
            <tbody>
                {% for item in opportunities %}
                <tr>
                    <td><strong>{{ item.name }}</strong></td>
                    <td>{{ item.price }}</td>
                    <td style="color: {{ '#22c55e' if item.change_val >= 0 else '#ef4444' }}">{{ item.change }}</td>
                    <td style="color: var(--text-muted); font-size: 13px;">{{ item.volume }}</td>
                    <td>{{ item.ratio }}</td>
                    <td>{{ item.reason }}</td>
                    <td><span class="badge badge-{{ item.badge }}">{{ item.signal }}</span></td>
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
    opportunities = scan_volume_breakouts()
    return render_template_string(HTML_TEMPLATE, opportunities=opportunities)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)