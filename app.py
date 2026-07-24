from flask import Flask, render_template_string, jsonify, request
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
        change_7d REAL,
        volume_spike REAL
    )''')
    conn.commit()
    conn.close()

def save_recommendation(symbol, price, signal, score, confidence, change_24h, change_7d, volume_spike):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO recommendations 
                     (symbol, price, signal, score, confidence, timestamp, change_24h, change_7d, volume_spike)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (symbol, price, signal, score, confidence, datetime.now(), change_24h, change_7d, volume_spike))
        conn.commit()
        conn.close()
    except:
        pass

bot_data = {
    "last_update": None,
    "status": "Hazır",
    "recommendations": [],
    "total_analyzed": 0,
    "buy_count": 0,
    "sell_count": 0,
    "hold_count": 0,
    "analyzing": False
}

def get_1h_klines(symbol):
    """Binance'den son 1h mum verisini al"""
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": "1m",
            "limit": 60
        }
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def get_24h_volume_avg(klines):
    """24h volume ortalaması"""
    try:
        url = "https://api.binance.com/api/v3/klines"
        # 1h interval'de 24 mum = 24 saat
        params = {
            "symbol": klines[0][0] if isinstance(klines, list) and len(klines) > 0 else "BTCUSDT",
            "interval": "1h",
            "limit": 24
        }
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            volumes = [float(k[7]) for k in data]  # Quote asset volume
            return sum(volumes) / len(volumes) if volumes else 0
    except:
        pass
    return 0

def get_top_coins():
    """CoinGecko'dan top 100 coini al - USDT pairing'ler"""
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "price_change_percentage": "1h,24h"
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"API hatası: {e}")
    return []

def analyze_coin_volatility(coin):
    """HACIM + OYNAKLIK analizi"""
    try:
        symbol = coin.get("symbol", "").upper()
        name = coin.get("name", "")
        price = coin.get("current_price", 0)
        change_1h = coin.get("price_change_percentage_1h_in_currency") or 0
        change_24h = coin.get("price_change_percentage_24h") or 0
        
        # Binance symbol
        if symbol not in ["BTC", "ETH", "BNB", "XRP", "SOL"]:
            binance_symbol = f"{symbol}USDT"
        else:
            binance_symbol = f"{symbol}USDT"
        
        # 1h mum verisini al
        klines_1h = get_1h_klines(binance_symbol)
        
        volume_spike = 0
        
        if klines_1h and len(klines_1h) > 0:
            # Son 1 dakika hacmi
            last_volume = float(klines_1h[-1][7])
            
            # Önceki 59 dakikanın ortalaması
            if len(klines_1h) > 1:
                prev_volumes = [float(k[7]) for k in klines_1h[:-1]]
                avg_volume = sum(prev_volumes) / len(prev_volumes)
                
                # Volume spike yüzdesi
                if avg_volume > 0:
                    volume_spike = ((last_volume - avg_volume) / avg_volume) * 100
        
        # OYNAKLLIK SKORU
        score = 50
        confidence = 40
        
        # 1h fiyat oynaklığı (KISA VADELİ)
        abs_change_1h = abs(change_1h)
        if abs_change_1h > 2:
            score += 20
            confidence += 20
        elif abs_change_1h > 1:
            score += 12
            confidence += 12
        elif abs_change_1h > 0.5:
            score += 8
            confidence += 8
        
        # Volume spike (HACIM PATLAMASI)
        if volume_spike > 100:  # 100% artış
            score += 25
            confidence += 25
        elif volume_spike > 50:  # 50% artış
            score += 18
            confidence += 18
        elif volume_spike > 30:  # 30% artış
            score += 12
            confidence += 12
        elif volume_spike > 15:  # 15% artış
            score += 8
            confidence += 8
        
        # 24h trend (destekle)
        if change_24h > 3:
            score += 8
            confidence += 5
        elif change_24h < -3:
            score -= 8
        
        score = max(0, min(100, score))
        confidence = max(0, min(100, confidence))
        
        # Tavsiye - AGRESIF (yüksek volatilite için)
        if score >= 80 and confidence >= 70:
            signal = "🟢🔥 HIZLI ALIŞ"
        elif score >= 70 and confidence >= 60:
            signal = "🟢 ALIŞ"
        elif score >= 60:
            signal = "🟡 DİKKAT"
        elif score <= 20 and confidence >= 60:
            signal = "🔴🔥 HIZLI SATIŞ"
        elif score <= 35:
            signal = "🔴 SATIŞ"
        else:
            signal = "⚪ BEKLE"
        
        return {
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "change_1h": change_1h,
            "change_24h": change_24h,
            "volume_spike": volume_spike
        }
    except Exception as e:
        print(f"Analiz hatası: {e}")
        return None

def run_analysis():
    """Analiz çalıştır"""
    global bot_data
    
    bot_data["analyzing"] = True
    bot_data["status"] = "Analiz yapılıyor..."
    
    try:
        coins = get_top_coins()
        
        if not coins:
            bot_data["status"] = "❌ Veri alınamadı"
            bot_data["analyzing"] = False
            return
        
        recommendations = []
        buy_count = 0
        sell_count = 0
        hold_count = 0
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] HACIM + OYNAKLLIK ANALİZİ: {len(coins)} coin")
        
        for i, coin in enumerate(coins):
            try:
                analysis = analyze_coin_volatility(coin)
                if not analysis:
                    continue
                
                symbol = coin.get("symbol", "").upper()
                name = coin.get("name", "")
                price = coin.get("current_price", 0)
                
                save_recommendation(
                    symbol, price, analysis["signal"],
                    analysis["score"], analysis["confidence"],
                    analysis["change_1h"], analysis["change_24h"],
                    analysis["volume_spike"]
                )
                
                # Yüksek volatilite ve hacim sinyalleri
                if "ALIŞ" in analysis["signal"] or "SATIŞ" in analysis["signal"]:
                    is_buy = "ALIŞ" in analysis["signal"]
                    
                    recommendations.append({
                        "symbol": symbol,
                        "name": name,
                        "price": f"${price:.4f}" if price < 1 else f"${price:.2f}",
                        "signal": analysis["signal"],
                        "score": analysis["score"],
                        "confidence": analysis["confidence"],
                        "change_1h": f"{analysis['change_1h']:+.2f}%",
                        "change_24h": f"{analysis['change_24h']:+.2f}%",
                        "volume_spike": f"{analysis['volume_spike']:+.1f}%",
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })
                    
                    if is_buy:
                        buy_count += 1
                    else:
                        sell_count += 1
                else:
                    hold_count += 1
                
                if (i + 1) % 20 == 0:
                    print(f"  {i+1}/{len(coins)} işlendi...")
            
            except Exception as e:
                continue
        
        # Skora göre sırala
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        
        bot_data["recommendations"] = recommendations[:30]
        bot_data["last_update"] = datetime.now().strftime("%H:%M:%S")
        bot_data["total_analyzed"] = len(coins)
        bot_data["buy_count"] = buy_count
        bot_data["sell_count"] = sell_count
        bot_data["hold_count"] = hold_count
        bot_data["status"] = f"✓ {len(coins)} coin | {len(recommendations)} VOLATIL coin bulundu"
        bot_data["analyzing"] = False
        
        print(f"\n✓ ALIŞ: {buy_count}, SATIŞ: {sell_count}, BEKLE: {hold_count}, TOPLAM: {len(recommendations)} volatil coin")
        
    except Exception as e:
        bot_data["status"] = f"❌ {str(e)}"
        bot_data["analyzing"] = False
        print(f"Hata: {e}")

def auto_bot_loop():
    """Otomatik analiz (her 5 dakika)"""
    init_db()
    print("🤖 Otomatik bot başlatıldı (Her 5 dakika)")
    
    while True:
        try:
            run_analysis()
            time.sleep(300)  # 5 dakika
        except Exception as e:
            print(f"Loop hatası: {e}")
            time.sleep(60)

bot_thread = threading.Thread(target=auto_bot_loop, daemon=True)
bot_thread.start()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hacim Patlaması Analiz Botu</title>
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
            margin-bottom: 25px;
        }
        .card h3 { margin-top: 0; color: var(--text-muted); }
        
        .buttons {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        
        .btn {
            padding: 10px 20px;
            border-radius: 6px;
            border: none;
            font-weight: bold;
            cursor: pointer;
            font-size: 14px;
            transition: opacity 0.2s;
        }
        
        .btn-analyze {
            background: var(--accent-blue);
            color: #0f172a;
        }
        
        .btn-analyze:hover:not(:disabled) {
            opacity: 0.9;
        }
        
        .btn-analyze:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
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
            font-size: 11px;
        }
        .box-value {
            font-weight: bold;
            font-size: 14px;
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
                <h1>🚀 Hacim Patlaması Analiz Botu</h1>
                <span style="color: var(--text-muted); font-size: 12px;">Volatilite + Hacim Tarayıcı</span>
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
                    <span class="status-badge" id="status">Hazır</span>
                </div>
            </div>
        </header>

        <div class="card">
            <div class="buttons">
                <button class="btn btn-analyze" id="analyzeBtn" onclick="startAnalysis()">
                    🔄 ANALİZ YAP
                </button>
                <span id="analyzeStatus" style="color: var(--text-muted); align-self: center;"></span>
            </div>

            <h3>📊 Volatil Coinler</h3>
            <div id="signals">
                <div class="empty-state">Analiz yapmak için butona basın yada otomatik analizin tamamlanmasını bekleyin...</div>
            </div>
        </div>
    </div>

    <script>
        function startAnalysis() {
            const btn = document.getElementById('analyzeBtn');
            const status = document.getElementById('analyzeStatus');
            
            btn.disabled = true;
            status.textContent = "Analiz yapılıyor...";
            
            fetch('/api/analyze', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    status.textContent = "✓ Tamamlandı";
                    setTimeout(() => { status.textContent = ""; }, 2000);
                })
                .catch(e => {
                    status.textContent = "❌ Hata";
                    console.log('Error:', e);
                })
                .finally(() => {
                    btn.disabled = false;
                    update();
                });
        }

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
                        container.innerHTML = '<div class="empty-state">Henüz volatil coin bulunmadı</div>';
                        return;
                    }

                    container.innerHTML = data.recommendations.map(r => {
                        const isBuy = r.signal.includes('ALIŞ');
                        const change1h = parseFloat(r.change_1h);
                        const priceColor = change1h >= 0 ? 'var(--buy-color)' : 'var(--sell-color)';
                        
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
                                        <div class="box-value" style="color: ${priceColor}">${r.change_1h}</div>
                                        <div>1h</div>
                                    </div>
                                    <div class="box">
                                        <div class="box-value" style="color: ${change1h >= 0 ? 'var(--buy-color)' : 'var(--sell-color)'}">${r.volume_spike}</div>
                                        <div>Hacim</div>
                                    </div>
                                    <div class="box">
                                        <div class="box-value">${r.score}</div>
                                        <div>Skor</div>
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

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Manual analiz çalıştır"""
    threading.Thread(target=run_analysis, daemon=True).start()
    return jsonify({"status": "Analiz başlatıldı"})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)