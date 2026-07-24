from flask import Flask, render_template_string, jsonify
import requests
import threading
import time
from datetime import datetime
import sqlite3
import json

app = Flask(__name__)

DB_FILE = "crypto_recommendations.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recommendations (
        id INTEGER PRIMARY KEY,
        symbol TEXT,
        price REAL,
        signal TEXT,
        score INTEGER,
        confidence INTEGER,
        timestamp DATETIME,
        change_24h REAL,
        change_7d REAL
    )''')
    conn.commit()
    conn.close()

def save_recommendation(symbol, price, signal, score, confidence, change_24h, change_7d):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO recommendations 
                     (symbol, price, signal, score, confidence, timestamp, change_24h, change_7d)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (symbol, price, signal, score, confidence, datetime.now(), change_24h, change_7d))
        conn.commit()
        conn.close()
    except:
        pass

bot_data = {
    "last_update": None,
    "status": "Başlatılıyor...",
    "recommendations": [],
    "total_analyzed": 0,
    "buy_count": 0,
    "sell_count": 0,
    "hold_count": 0
}

def get_top_coins():
    """CoinGecko'dan top 50 coini al"""
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 50,
            "price_change_percentage": "24h,7d"
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ {len(data)} coin alındı")
            return data
    except Exception as e:
        print(f"API hatası: {e}")
    return []

def analyze_coin(coin):
    """Basit ve doğru analiz"""
    try:
        change_24h = coin.get("price_change_percentage_24h") or 0
        change_7d = coin.get("price_change_percentage_7d") or 0
        
        score = 50
        
        # Basit algoritma
        if change_24h > 3:
            score += 15
        elif change_24h > 0:
            score += 8
        elif change_24h < -3:
            score -= 15
        elif change_24h < 0:
            score -= 8
        
        if change_7d > 8:
            score += 12
        elif change_7d < -8:
            score -= 12
        
        score = max(0, min(100, score))
        confidence = 60
        
        # Tavsiye
        if score >= 70:
            signal = "🟢 ALIŞ"
        elif score >= 60:
            signal = "🟡 ALIŞ"
        elif score <= 30:
            signal = "🔴 SATIŞ"
        elif score <= 40:
            signal = "🔴 SATIŞ"
        else:
            signal = "⚪ BEKLE"
        
        return {
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "change_24h": change_24h,
            "change_7d": change_7d
        }
    except:
        return None

def run_bot():
    global bot_data
    init_db()
    
    print("🤖 Bot başlatılıyor...")
    
    while True:
        try:
            bot_data["status"] = "Analiz ediliyor..."
            
            coins = get_top_coins()
            
            if not coins:
                bot_data["status"] = "❌ Veri alınamadı"
                time.sleep(30)
                continue
            
            recommendations = []
            buy_count = 0
            sell_count = 0
            hold_count = 0
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {len(coins)} coin analiz ediliyor...")
            
            for coin in coins:
                try:
                    analysis = analyze_coin(coin)
                    if not analysis:
                        continue
                    
                    symbol = coin.get("symbol", "").upper()
                    name = coin.get("name", "")
                    price = coin.get("current_price", 0)
                    
                    save_recommendation(
                        symbol, price, analysis["signal"],
                        analysis["score"], analysis["confidence"],
                        analysis["change_24h"], analysis["change_7d"]
                    )
                    
                    if "ALIŞ" in analysis["signal"]:
                        buy_count += 1
                        recommendations.append({
                            "symbol": symbol,
                            "name": name,
                            "price": f"${price:.4f}" if price < 1 else f"${price:.2f}",
                            "signal": analysis["signal"],
                            "score": analysis["score"],
                            "confidence": analysis["confidence"],
                            "change_24h": f"{analysis['change_24h']:+.2f}%",
                            "change_7d": f"{analysis['change_7d']:+.2f}%",
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
                    elif "SATIŞ" in analysis["signal"]:
                        sell_count += 1
                        recommendations.append({
                            "symbol": symbol,
                            "name": name,
                            "price": f"${price:.4f}" if price < 1 else f"${price:.2f}",
                            "signal": analysis["signal"],
                            "score": analysis["score"],
                            "confidence": analysis["confidence"],
                            "change_24h": f"{analysis['change_24h']:+.2f}%",
                            "change_7d": f"{analysis['change_7d']:+.2f}%",
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
                    else:
                        hold_count += 1
                
                except Exception as e:
                    print(f"Coin hatası: {e}")
                    continue
            
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            
            bot_data["recommendations"] = recommendations
            bot_data["last_update"] = datetime.now().strftime("%H:%M:%S")
            bot_data["total_analyzed"] = len(coins)
            bot_data["buy_count"] = buy_count
            bot_data["sell_count"] = sell_count
            bot_data["hold_count"] = hold_count
            bot_data["status"] = f"✓ {len(coins)} coin | {len(recommendations)} sinyal"
            
            print(f"ALIŞ: {buy_count}, SATIŞ: {sell_count}, BEKLE: {hold_count}, TOPLAM: {len(recommendations)}")
            
            time.sleep(300)
            
        except Exception as e:
            bot_data["status"] = f"❌ {str(e)}"
            print(f"Hata: {e}")
            time.sleep(60)

bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kripto Analiz Botu</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #38bdf8;
            --buy-color: #22c55e;
            --sell-color: #ef4444;
            --border-color: #334155;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid var(--accent-blue);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        h1 { margin: 0; color: var(--accent-blue); font-size: 24px; }
        .stats {
            display: flex;
            gap: 20px;
            font-size: 13px;
        }
        .stat {
            display: flex;
            flex-direction: column;
        }
        .stat-value {
            color: var(--accent-blue);
            font-weight: bold;
            font-size: 18px;
        }
        .stat-label {
            color: var(--text-muted);
            margin-top: 3px;
        }
        .status-badge {
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 12px;
            background: rgba(34, 197, 94, 0.2);
            color: var(--buy-color);
            border: 1px solid var(--buy-color);
        }
        .card {
            background-color: var(--card-bg);
            border-radius: 12px;
            padding: 24px;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .card h3 { margin-top: 0; color: var(--text-muted); }
        
        .signal-item {
            padding: 15px;
            border-left: 4px solid;
            margin-bottom: 12px;
            border-radius: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .signal-item.buy {
            border-left-color: var(--buy-color);
            background: rgba(34, 197, 94, 0.1);
        }
        .signal-item.sell {
            border-left-color: var(--sell-color);
            background: rgba(239, 68, 68, 0.1);
        }
        
        .signal-left {
            display: flex;
            gap: 15px;
            align-items: center;
            flex: 1;
        }
        .signal-info h4 {
            margin: 0 0 5px 0;
            font-size: 16px;
        }
        .signal-info p {
            margin: 0;
            font-size: 12px;
            color: var(--text-muted);
        }
        
        .signal-right {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .box {
            text-align: center;
            padding: 8px 12px;
            background: #0f172a;
            border-radius: 4px;
            border: 1px solid var(--border-color);
            font-size: 12px;
        }
        .box-value {
            font-weight: bold;
            font-size: 16px;
            color: var(--accent-blue);
        }
        
        .empty-state {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
        }
        
        .loading { animation: pulse 1s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>🤖 Kripto Analiz Botu</h1>
                <span style="color: var(--text-muted); font-size: 12px;">Otomatik Analiz Sistemi</span>
            </div>
            <div class="stats">
                <div class="stat">
                    <span class="stat-value" id="analyzed">0</span>
                    <span class="stat-label">Coin Analiz</span>
                </div>
                <div class="stat">
                    <span class="stat-value" style="color: var(--buy-color);" id="buyCount">0</span>
                    <span class="stat-label">ALIŞ</span>
                </div>
                <div class="stat">
                    <span class="stat-value" style="color: var(--sell-color);" id="sellCount">0</span>
                    <span class="stat-label">SATIŞ</span>
                </div>
                <div class="stat">
                    <span class="stat-value" id="lastUpdate">--:--</span>
                    <span class="stat-label">Son Güncelleme</span>
                </div>
                <div class="stat">
                    <span class="status-badge loading" id="status">● Başlatılıyor...</span>
                </div>
            </div>
        </header>

        <div class="card">
            <h3>📊 Canlı Sinyaller</h3>
            <div id="signals">
                <div class="empty-state loading">Veriler yükleniyor...</div>
            </div>
        </div>
    </div>

    <script>
        function update() {
            fetch('/api/signals')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('analyzed').textContent = data.total_analyzed;
                    document.getElementById('buyCount').textContent = data.buy_count;
                    document.getElementById('sellCount').textContent = data.sell_count;
                    document.getElementById('lastUpdate').textContent = data.last_update || '--:--';
                    document.getElementById('status').textContent = data.status;

                    const container = document.getElementById('signals');
                    
                    if (!data.recommendations || data.recommendations.length === 0) {
                        container.innerHTML = '<div class="empty-state">Bot analiz yapıyor. Birkaç dakika bekleyin...</div>';
                        return;
                    }

                    container.innerHTML = data.recommendations.map(r => {
                        const isBuy = r.signal.includes('ALIŞ');
                        const change24h = parseFloat(r.change_24h);
                        const priceColor = change24h >= 0 ? 'var(--buy-color)' : 'var(--sell-color)';
                        
                        return `
                            <div class="signal-item ${isBuy ? 'buy' : 'sell'}">
                                <div class="signal-left">
                                    <strong style="font-size: 16px;">${r.signal}</strong>
                                    <div class="signal-info">
                                        <h4>${r.symbol}</h4>
                                        <p>${r.name}</p>
                                        <p>${r.price} | ${r.timestamp}</p>
                                    </div>
                                </div>
                                <div class="signal-right">
                                    <div class="box">
                                        <div class="box-value" style="color: ${priceColor}">${r.change_24h}</div>
                                        <div>24h</div>
                                    </div>
                                    <div class="box">
                                        <div class="box-value">${r.score}</div>
                                        <div>Skor</div>
                                    </div>
                                    <div class="box">
                                        <div class="box-value">${r.confidence}%</div>
                                        <div>Güven</div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('');
                })
                .catch(e => console.log('Hata:', e));
        }

        update();
        setInterval(update, 10000);
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/signals")
def api_signals():
    return jsonify(bot_data)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)