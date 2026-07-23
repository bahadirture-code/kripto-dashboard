from flask import Flask, render_template_string, request, redirect, url_for
import os

app = Flask(__name__)

# Geçici hafıza (İstediğiniz zaman ekleyip güncelleyebileceğiniz liste)
market_opportunities = [
    {
        "id": 1,
        "name": "Pepe (PEPE)",
        "price": "$0.0000142",
        "change": "+14.85%",
        "change_val": 14.85,
        "volume": "$1,450,200,000",
        "reason": "Ani hacim patlaması ve güçlü yukarı kırılım.",
        "signal": "VOLATİL ATAK (AL)",
        "badge": "buy"
    },
    {
        "id": 2,
        "name": "Render (RENDER)",
        "price": "$7.45",
        "change": "+8.20%",
        "change_val": 8.20,
        "volume": "$620,100,000",
        "reason": "Yüksek alım iştahı ve direnç seviyesi testi.",
        "signal": "GÜÇLÜ MOMENTUM",
        "badge": "buy"
    }
]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kısa Vade Hacim Patlaması & Yönetim Paneli</title>
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
        .card { background-color: var(--card-bg); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); box-shadow: 0 4px 6px rgba(0,0,0,0.3); margin-bottom: 25px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 14px; text-align: left; border-bottom: 1px solid var(--border-color); }
        th { background-color: #111827; color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
        tr:hover { background-color: rgba(56, 189, 248, 0.05); }
        .badge { padding: 6px 12px; border-radius: 6px; font-weight: bold; font-size: 11px; display: inline-block; text-align: center; }
        .badge-buy { background: rgba(34,197,94,0.2); color: var(--buy-color); border: 1px solid var(--buy-color); }
        .badge-sell { background: rgba(239,68,68,0.2); color: var(--sell-color); border: 1px solid var(--sell-color); }
        .badge-hold { background: rgba(245,158,11,0.2); color: var(--hold-color); border: 1px solid var(--hold-color); }
        form input, form select, form button { padding: 10px; margin-right: 10px; margin-bottom: 10px; border-radius: 6px; border: 1px solid var(--border-color); background: #0f172a; color: var(--text-color); }
        form button { background: var(--accent-blue); color: #0f172a; font-weight: bold; cursor: pointer; border: none; }
        form button:hover { opacity: 0.9; }
        .btn-delete { background: var(--sell-color); color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none; font-size: 12px; font-weight: bold; }
    </style>
</head>
<body>
    <header>
        <h1>🚀 Kısa Vade Hacim Patlaması & Yönetim Paneli</h1>
        <span style="color: #22c55e; font-weight: bold; font-size: 13px;">● Dinamik Kontrol Aktif</span>
    </header>

    <!-- Yeni Varlık Ekleme Formu -->
    <div class="card">
        <h3 style="margin-top:0; color: var(--text-muted);">➕ Listeye Yeni Fırsat / Coin Ekle</h3>
        <form action="/add" method="POST">
            <input type="text" name="name" placeholder="Coin Adı (Örn: SOL)" required>
            <input type="text" name="price" placeholder="Fiyat (Örn: $145.00)" required>
            <input type="text" name="change" placeholder="Değişim (Örn: +12.5%)" required>
            <input type="text" name="volume" placeholder="Hacim (Örn: $500M)" required>
            <input type="text" name="reason" placeholder="Gerekçe / Not" style="width: 250px;" required>
            <select name="signal">
                <option value="VOLATİL ATAK (AL)">VOLATİL ATAK (AL)</option>
                <option value="GÜÇLÜ MOMENTUM">GÜÇLÜ MOMENTUM</option>
                <option value="DİP FIRSATI">DİP FIRSATI</option>
                <option value="İZLE & TOPLA">İZLE & TOPLA</option>
            </select>
            <button type="submit">Listeye Ekle</button>
        </form>
    </div>

    <!-- Mevcut Liste Tablosu -->
    <div class="card">
        <h3 style="margin-top:0; color: var(--text-muted);">Anlık Takip Edilen Fırsatlar</h3>
        <table>
            <thead>
                <tr>
                    <th>Varlık</th>
                    <th>Fiyat</th>
                    <th>24s Değişim</th>
                    <th>Toplam Hacim</th>
                    <th>Algoritma Gerekçesi</th>
                    <th>Sinyal</th>
                    <th>Aksiyon</th>
                </tr>
            </thead>
            <tbody>
                {% for item in opportunities %}
                <tr>
                    <td><strong>{{ item.name }}</strong></td>
                    <td>{{ item.price }}</td>
                    <td style="color: #22c55e">{{ item.change }}</td>
                    <td style="color: var(--text-muted); font-size: 13px;">{{ item.volume }}</td>
                    <td>{{ item.reason }}</td>
                    <td><span class="badge badge-buy">{{ item.signal }}</span></td>
                    <td><a href="/delete/{{ item.id }}" class="btn-delete">Kaldır</a></td>
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
    return render_template_string(HTML_TEMPLATE, opportunities=market_opportunities)

@app.route("/add", methods=["POST"])
def add_opportunity():
    new_id = len(market_opportunities) + 1
    name = request.form.get("name")
    price = request.form.get("price")
    change = request.form.get("change")
    volume = request.form.get("volume")
    reason = request.form.get("reason")
    signal = request.form.get("signal")

    market_opportunities.append({
        "id": new_id,
        "name": name,
        "price": price,
        "change": change,
        "change_val": 5.0,
        "volume": volume,
        "reason": reason,
        "signal": signal,
        "badge": "buy"
    })
    return redirect(url_for('index'))

@app.route("/delete/<int:item_id>")
def delete_opportunity(item_id):
    global market_opportunities
    market_opportunities = [item for item in market_opportunities if item["id"] != item_id]
    return redirect(url_for('index'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)