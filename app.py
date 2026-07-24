from flask import Flask, render_template_string, jsonify
import requests
import threading
import time
from datetime import datetime, timedelta
import sqlite3
import json
import os

app = Flask(__name__)

# Database setup
DB_FILE = "crypto_recommendations.db"

def init_db():
    """Database'i başlat"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recommendations (
        id INTEGER PRIMARY KEY,
        coin_id TEXT,
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

def save_recommendation(coin_id, symbol, price, signal, score, confidence, change_24h, change_7d):
    """Öneriye DB'ye kaydet"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO recommendations 
                     (coin_id, symbol, price, signal, score, confidence, timestamp, change_24h, change_7d)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (coin_id, symbol, price, signal, score, confidence, datetime.now(), change_24h, change_7d))
        conn.commit()
        conn.close()
    except:
        pass

# Global veri
bot_data = {
    "last_update": None,
    "status": "Başlatılıyor...",
    "recommendations": [],
    "total_analyzed": 0,
    "buy_count": 0,
    "sell_count": 0,
    "hold_count": 0
}

COINGECKO_API = "https://api.coingecko.com/api/v3"

def get_top_coins():
    """Top 100 coini al"""
    try:
        url = f"{COINGECKO_API}/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "price_change_percentage": "1h,24h,7d"
        }
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        print(f"[DEBUG] {len(data)} coin getiridi")
        return data
    except Exception as e:
        print(f"Coin getirme hatası: {e}")
        return []

def analyze_and_recommend(coin):
    """Coin'i analiz et ve tavsiye ver"""
    try:
        score = 50
        confidence = 30
        
        change_24h = coin.get("price_change_percentage_24h") or 0
        change_7d = coin.get("price_change_percentage_7d") or 0
        market_cap = coin.get("market_cap") or 0
        ath = coin.get("ath") or coin.get("current_price") or 1
        current_price = coin.get("current_price") or 1
        
        # Market cap faktörü
        if market_cap and market_cap > 500000000:  # $500M+
            confidence += 15
        elif market_cap and market_cap > 100000000:  # $100M+
            confidence += 10
        
        # 24h momentum - GÜÇLÜ SINYAL
        if change_24h > 5:
            score += 20
            confidence += 15
        elif change_24h > 2:
            score += 10
            confidence += 8
        elif change_24h > 0:
            score += 5
            confidence += 3
        elif change_24h < -5:
            score -= 20
            confidence += 15
        elif change_24h < -2:
            score -= 10
            confidence += 8
        elif change_24h < 0:
            score -= 5
            confidence += 3
        
        # 7d trend - ÖNEMLİ SINYAL
        if change_7d > 10:
            score += 18
            confidence += 12
        elif change_7d > 5:
            score += 10
            confidence += 8
        elif change_7d < -10:
            score -= 18
            confidence += 12
        elif change_7d < -5:
            score -= 10
            confidence += 8
        
        # ATH mesafesi
        if ath > 0 and current_price > 0:
            distance_from_ath = ((ath - current_price) / ath) * 100
            
            if distance_from_ath > 60:
                score += 12
                confidence += 8
            elif distance_from_ath > 40:
                score += 8
                confidence += 5
            elif distance_from_ath < 5:
                score -= 8
        
        score = max(0, min(100, score))
        confidence = max(0, min(100, confidence))
        
        # Tavsiye ver - GENİŞ FİLTRE
        if score >= 65:
            signal = "🟢 ALIŞ"
        elif score >= 55:
            signal = "🟡 ALIŞ (DİKKAT)"
        elif score <= 35:
            signal = "🔴 SATIŞ"
        elif score <= 45:
            signal = "🔴 SATIŞ (DİKKAT)"
        else:
            signal = "⚪ BEKLE"
        
        return {
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "change_24h": change_24h,
            "change_7d": change_7d
        }
        
    except Exception as e:
        print(f"Analiz hatası: {e}")
        return None

def run_bot():
    """Bot analiz döngüsü"""
    global bot_data
    
    init_db()
    first_run = True
    
    while True:
        try:
            bot_data["status"] = "Analiz ediliyor..."
            
            coins = get_top_coins()
            if not coins:
                bot_data["status"] = "❌ Veri alınamadı"
                time.sleep(60)
                continue
            
            recommendations = []
            buy_count = 0
            sell_count = 0
            hold_count = 0
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {len(coins)} coin analiz ediliyor...")
            
            for i, coin in enumerate(coins):
                try:
                    analysis = analyze_and_recommend(coin)
                    
                    if not analysis:
                        continue
                    
                    coin_id = coin.get("id", "")
                    symbol = coin.get("symbol", "").upper()
                    price = coin.get("current_price", 0)
                    name = coin.get("name", "")
                    
                    # DB'ye kaydet
                    save_recommendation(
                        coin_id,
                        symbol,
                        price,
                        analysis["signal"],
                        analysis["score"],
                        analysis["confidence"],
                        analysis["change_24h"],
                        analysis["change_7d"]
                    )
                    
                    # Tüm sinyalleri kaydet (STRONG değil, normal)
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
                    
                    if (i + 1) % 25 == 0:
                        print(f"  {i+1}/{len(coins)} tamamlandı...")
                
                except Exception as e:
                    print(f"Coin analiz hatası: {e}")
                    continue
            
            # Sıralama (score'a göre)
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            
            bot_data["recommendations"] = recommendations
            bot_data["last_update"] = datetime.now().strftime("%H:%M:%S")
            bot_data["total_analyzed"] = len(coins)
            bot_data["buy_count"] = buy_count
            bot_data["sell_count"] = sell_count
            bot_data["hold_count"] = hold_count
            bot_data["status"] = f"✓ {len(coins)} coin analiz | {len(recommendations)} sinyal bulundu"
            
            print(f"SONUÇ: ALIŞ={buy_count}, SATIŞ={sell_count}, BEKLE={hold_count}, TOTAL={len(recommendations)} sinyal")
            
            if first_run:
                print("✓ Bot başlatıldı, canlı tarama başladı!")
                first_run = False
            
            time.sleep(300)  # Her 5 dakika
            
        except Exception as e:
            bot_data["status"] = f"❌ Hata: {str(e)}"
            print(f"Bot hatası: {e}")
            time.sleep(60)

# Bot thread başlat
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
            --hold-color: #f59e0b;
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
            margin-bottom: 25px;
        }
        .card h3 { margin-top: 0; color: var(--text-muted); }
        
        .signal-item {
            padding: 15px;
            border-left: 4px solid var(--border-color);
            margin-bottom: 12px;
            background: rgba(56, 189, 248, 0.05);
            border-radius: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .signal-item.buy {
            border-left-color: var(--buy-color);
            background: rgba(34, 197, 94, 0.05);
        }
        .signal-item.sell {
            border-left-color: var(--sell-color);
            background: rgba(239, 68, 68, 0.05);
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
        .signal-badge {
            font-weight: 600;
            font-size: 14px;
            min-width: 120px;
        }
        
        .signal-right {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        
        .score-box {
            text-align: center;
            padding: 10px 15px;
            background: #0f172a;
            border-radius: 6px;
            border: 1px solid var(--border-color);
        }
        .score-value {
            font-weight: bold;
            font-size: 18px;
            color: var(--accent-blue);
        }
        .score-label {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 3px;
        }
        
        .change-box {
            text-align: center;
            padding: 10px 15px;
            background: #0f172a;
            border-radius: 6px;
            border: 1px solid var(--border-color);
        }
        .change-24h {
            font-weight: 600;
            font-size: 14px;
        }
        .change-7d {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 3px;
        }
        
        .empty-state {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
        }
        
        .loading { animation: pulse 1s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        
        @media (max-width: 768px) {
            header { flex-direction: column; gap: 15px; }
            .stats { flex-direction: column; }
            .signal-item { flex-direction: column; align-items: flex-start; }
            .signal-right { width: 100%; margin-top: 12px; }
        }
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
                    <span class="stat-label">ALIŞ Sinyali</span>
                </div>
                <div class="stat">
                    <span class="stat-value" style="color: var(--sell-color);" id="sellCount">0</span>
                    <span class="stat-label">SATIŞ Sinyali</span>
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
            <h3>📊 Canlı İşlem Sinyalleri</h3>
            
            <div id="signalsContainer">
                <div class="empty-state loading">
                    Pazar verisi analiz ediliyor...
                </div>
            </div>
        </div>
    </div>

    <script>
        function updateSignals() {
            fetch('/api/signals')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('analyzed').textContent = data.total_analyzed;
                    document.getElementById('buyCount').textContent = data.buy_count;
                    document.getElementById('sellCount').textContent = data.sell_count;
                    document.getElementById('lastUpdate').textContent = data.last_update || '--:--';
                    document.getElementById('status').textContent = data.status;

                    if (data.status.includes('✓')) {
                        document.getElementById('status').classList.remove('loading');
                    }

                    const container = document.getElementById('signalsContainer');
                    
                    if (data.recommendations.length === 0) {
                        container.innerHTML = '<div class="empty-state">Henüz sinyal bulunamadı. Bot analiz yapıyor...</div>';
                        return;
                    }

                    container.innerHTML = data.recommendations.map(rec => {
                        const isBuy = rec.signal.includes('ALIŞ');
                        const itemClass = isBuy ? 'buy' : 'sell';
                        
                        const change24h = parseFloat(rec.change_24h);
                        const change24hClass = change24h >= 0 ? 'color: var(--buy-color)' : 'color: var(--sell-color)';
                        
                        return `
                            <div class="signal-item ${itemClass}">
                                <div class="signal-left">
                                    <div class="signal-badge">${rec.signal}</div>
                                    <div class="signal-info">
                                        <h4>${rec.symbol}</h4>
                                        <p>${rec.name}</p>
                                        <p>${rec.price}</p>
                                        <p>${rec.timestamp}</p>
                                    </div>
                                </div>
                                <div class="signal-right">
                                    <div class="change-box">
                                        <div class="change-24h" style="${change24hClass}">${rec.change_24h}</div>
                                        <div class="change-7d">${rec.change_7d}</div>
                                    </div>
                                    <div class="score-box">
                                        <div class="score-value">${rec.score}</div>
                                        <div class="score-label">Skor</div>
                                    </div>
                                    <div class="score-box">
                                        <div class="score-value">${rec.confidence}%</div>
                                        <div class="score-label">Güven</div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('');
                })
                .catch(err => console.error('Hata:', err));
        }

        updateSignals();
        setInterval(updateSignals, 10000);
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)