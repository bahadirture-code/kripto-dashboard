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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO recommendations 
                 (coin_id, symbol, price, signal, score, confidence, timestamp, change_24h, change_7d)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (coin_id, symbol, price, signal, score, confidence, datetime.now(), change_24h, change_7d))
    conn.commit()
    conn.close()

def get_recent_recommendations(limit=50):
    """Son önerileri getir"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM recommendations ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_coin_history(symbol, limit=10):
    """Coin'in geçmiş önerileri"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT signal, score, timestamp FROM recommendations WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?', 
              (symbol, limit))
    rows = c.fetchall()
    conn.close()
    return rows

# Global veri
bot_data = {
    "last_update": None,
    "status": "Initializing...",
    "recommendations": [],
    "total_analyzed": 0,
    "buy_count": 0,
    "sell_count": 0,
    "hold_count": 0
}

BINANCE_API = "https://api.binance.com/api/v3"
COINGECKO_API = "https://api.coingecko.com/api/v3"

def get_top_coins():
    """Top 50 coini al"""
    try:
        url = f"{COINGECKO_API}/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 50,
            "price_change_percentage": "1h,24h,7d"
        }
        response = requests.get(url, params=params, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error getting coins: {e}")
        return []

def analyze_and_recommend(coin):
    """Coin'i analiz et ve tavsiye ver"""
    try:
        score = 50
        confidence = 0
        
        change_24h = coin.get("price_change_percentage_24h", 0) or 0
        change_7d = coin.get("price_change_percentage_7d", 0) or 0
        market_cap = coin.get("market_cap", 0) or 0
        ath = coin.get("ath", coin.get("current_price", 1)) or 1
        current_price = coin.get("current_price", 1) or 1
        
        # Market cap faktörü
        if market_cap and market_cap > 1000000000:
            confidence += 20
        
        # 24h momentum - GÜÇLÜ SINYAL
        if change_24h > 8:
            score += 25
            confidence += 20
        elif change_24h > 4:
            score += 15
            confidence += 10
        elif change_24h > 2:
            score += 8
            confidence += 5
        elif change_24h < -8:
            score -= 25
            confidence += 20
        elif change_24h < -4:
            score -= 15
            confidence += 10
        elif change_24h < -2:
            score -= 8
            confidence += 5
        
        # 7d trend - ÖNEMLİ SINYAL
        if change_7d > 15:
            score += 20
            confidence += 15
        elif change_7d > 8:
            score += 12
            confidence += 10
        elif change_7d < -15:
            score -= 20
            confidence += 15
        elif change_7d < -8:
            score -= 12
            confidence += 10
        
        # ATH mesafesi - UZUN DÖNEM
        if ath > 0 and current_price > 0:
            distance_from_ath = ((ath - current_price) / ath) * 100
            
            # Dip fırsatı (50%+ aşağıda)
            if distance_from_ath > 50:
                score += 15
                confidence += 10
            # ATH'ye yakın (5% içinde) - Risk
            elif distance_from_ath < 5:
                score -= 10
        
        # Volatilite (aktif işlem)
        if change_24h != 0:
            volatility = abs(change_24h)
            if volatility > 10:
                confidence += 10
            elif volatility > 5:
                confidence += 5
        
        score = max(0, min(100, score))
        confidence = max(0, min(100, confidence))
        
        # Tavsiye ver
        if score >= 70 and confidence >= 50:
            signal = "🟢 STRONG BUY"
        elif score >= 60:
            signal = "🟢 BUY"
        elif score >= 55:
            signal = "🟡 BUY (CAUTION)"
        elif score <= 30 and confidence >= 50:
            signal = "🔴 STRONG SELL"
        elif score <= 40:
            signal = "🔴 SELL"
        elif score <= 45:
            signal = "🔴 SELL (CAUTION)"
        else:
            signal = "⚪ HOLD"
        
        return {
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "change_24h": change_24h,
            "change_7d": change_7d
        }
        
    except Exception as e:
        print(f"Analysis error: {e}")
        return None

def run_bot():
    """Bot analiz döngüsü"""
    global bot_data
    
    init_db()
    
    while True:
        try:
            bot_data["status"] = "Analyzing..."
            
            coins = get_top_coins()
            if not coins:
                bot_data["status"] = "Failed to fetch data"
                time.sleep(30)
                continue
            
            recommendations = []
            buy_count = 0
            sell_count = 0
            hold_count = 0
            
            for coin in coins:
                try:
                    analysis = analyze_and_recommend(coin)
                    
                    if not analysis:
                        continue
                    
                    coin_id = coin.get("id", "")
                    symbol = coin.get("symbol", "").upper()
                    price = coin.get("current_price", 0)
                    
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
                    
                    # Sadece önemli sinyalleri göster (BUY/SELL)
                    if "BUY" in analysis["signal"]:
                        buy_count += 1
                        if analysis["score"] >= 65:  # Strong signals only
                            recommendations.append({
                                "symbol": symbol,
                                "name": coin.get("name", ""),
                                "price": f"${price:.2f}",
                                "signal": analysis["signal"],
                                "score": analysis["score"],
                                "confidence": analysis["confidence"],
                                "change_24h": f"{analysis['change_24h']:+.2f}%",
                                "change_7d": f"{analysis['change_7d']:+.2f}%",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                    elif "SELL" in analysis["signal"]:
                        sell_count += 1
                        if analysis["score"] <= 35:
                            recommendations.append({
                                "symbol": symbol,
                                "name": coin.get("name", ""),
                                "price": f"${price:.2f}",
                                "signal": analysis["signal"],
                                "score": analysis["score"],
                                "confidence": analysis["confidence"],
                                "change_24h": f"{analysis['change_24h']:+.2f}%",
                                "change_7d": f"{analysis['change_7d']:+.2f}%",
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                    else:
                        hold_count += 1
                
                except Exception as e:
                    print(f"Error analyzing coin: {e}")
                    continue
            
            # Sıralama (score'a göre)
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            
            bot_data["recommendations"] = recommendations[:20]
            bot_data["last_update"] = datetime.now().strftime("%H:%M:%S")
            bot_data["total_analyzed"] = len(coins)
            bot_data["buy_count"] = buy_count
            bot_data["sell_count"] = sell_count
            bot_data["hold_count"] = hold_count
            bot_data["status"] = f"✓ Analyzed {len(coins)} coins | Found {len(recommendations)} signals"
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] BUY: {buy_count}, SELL: {sell_count}, HOLD: {hold_count}")
            
            time.sleep(300)  # Her 5 dakika
            
        except Exception as e:
            bot_data["status"] = f"❌ Error: {str(e)}"
            print(f"Bot error: {e}")
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
    <title>Crypto Analyzer Bot</title>
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
                <h1>🤖 Crypto Analyzer Bot</h1>
                <span style="color: var(--text-muted); font-size: 12px;">Fully Automated Analysis</span>
            </div>
            <div class="stats">
                <div class="stat">
                    <span class="stat-value" id="analyzed">0</span>
                    <span class="stat-label">Coins Analyzed</span>
                </div>
                <div class="stat">
                    <span class="stat-value" style="color: var(--buy-color);" id="buyCount">0</span>
                    <span class="stat-label">BUY Signals</span>
                </div>
                <div class="stat">
                    <span class="stat-value" style="color: var(--sell-color);" id="sellCount">0</span>
                    <span class="stat-label">SELL Signals</span>
                </div>
                <div class="stat">
                    <span class="stat-value" id="lastUpdate">--:--</span>
                    <span class="stat-label">Last Update</span>
                </div>
                <div class="stat">
                    <span class="status-badge loading" id="status">● Analyzing...</span>
                </div>
            </div>
        </header>

        <div class="card">
            <h3>📊 Live Trading Signals</h3>
            
            <div id="signalsContainer">
                <div class="empty-state loading">
                    Analyzing market data...
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

                    if (data.status.includes('Analyzed')) {
                        document.getElementById('status').classList.remove('loading');
                    }

                    const container = document.getElementById('signalsContainer');
                    
                    if (data.recommendations.length === 0) {
                        container.innerHTML = '<div class="empty-state">No strong signals yet. Bot is analyzing...</div>';
                        return;
                    }

                    container.innerHTML = data.recommendations.map(rec => {
                        const isBuy = rec.signal.includes('BUY');
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
                                        <div class="score-label">Score</div>
                                    </div>
                                    <div class="score-box">
                                        <div class="score-value">${rec.confidence}%</div>
                                        <div class="score-label">Confidence</div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('');
                })
                .catch(err => console.error('Error:', err));
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