from flask import Flask, render_template_string, jsonify, request
import requests
import threading
import time
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import sqlite3
import os

# --- Loglama ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
DB_FILE = "crypto_recommendations.db"
LOCK = threading.Lock()
TZ_TR = ZoneInfo("Europe/Istanbul")

# --- Veritabanı ---
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
        change_1h REAL,
        change_24h REAL,
        volume_change REAL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON recommendations(timestamp)')
    conn.commit()
    conn.close()
    logger.info("Veritabanı hazır")

def save_recommendations_bulk(recommendations):
    if not recommendations:
        return
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        now_utc = datetime.now(timezone.utc)
        data = []
        for r in recommendations:
            data.append((
                r["symbol"], r["price"], r["signal"],
                r["score"], r["confidence"], now_utc,
                r["change_1h"], r["change_24h"], r["volume_ratio"]
            ))
        c.executemany('''INSERT INTO recommendations 
                         (symbol, price, signal, score, confidence, timestamp, change_1h, change_24h, volume_change)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', data)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB hatası: {e}")

def clean_old_records(keep_days=7):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM recommendations WHERE timestamp < datetime('now', ?)", (f'-{keep_days} days',))
        deleted = c.rowcount
        conn.commit()
        conn.close()
        if deleted:
            logger.info(f"{deleted} eski kayıt temizlendi")
    except Exception as e:
        logger.error(f"Temizlik hatası: {e}")

# --- Bot durumu ---
bot_data = {
    "last_update": None,
    "status": "Hazır",
    "recommendations": [],
    "total_analyzed": 0,
    "buy_count": 0,
    "sell_count": 0,
    "analyzing": False
}

# --- CoinGecko API (geliştirilmiş) ---
def get_coins_with_volume(retries=3, delay=3):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 50,
        "price_change_percentage": "1h,24h",
        "sparkline": False
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"API yanıt kodu {response.status_code}, deneme {attempt+1}/{retries}")
                if response.status_code == 429:  # Rate limit
                    time.sleep(delay * 5)  # daha uzun bekle
                    continue
        except requests.exceptions.Timeout:
            logger.warning(f"Zaman aşımı, deneme {attempt+1}/{retries}")
        except Exception as e:
            logger.warning(f"API istek hatası: {e}, deneme {attempt+1}/{retries}")
        time.sleep(delay * (attempt + 1))
    logger.error("CoinGecko API'den veri alınamadı - internet bağlantınızı kontrol edin")
    return []

# --- Analiz (değişmedi) ---
def analyze_volatility(coin):
    try:
        symbol = coin.get("symbol", "").upper()
        price = coin.get("current_price", 0)
        change_1h = coin.get("price_change_percentage_1h_in_currency") or 0
        change_24h = coin.get("price_change_percentage_24h") or 0
        market_cap = coin.get("market_cap") or 0
        total_volume = coin.get("total_volume") or 0
        volume_ratio = (total_volume / market_cap * 100) if market_cap > 0 else 0
        
        score = 50
        confidence = 40
        abs_1h = abs(change_1h)
        if abs_1h > 3:
            score += 25; confidence += 25
        elif abs_1h > 1.5:
            score += 15; confidence += 15
        elif abs_1h > 0.5:
            score += 8; confidence += 8
        if change_24h > 5:
            score += 12; confidence += 10
        elif change_24h < -5:
            score -= 12
        if volume_ratio > 50:
            score += 15; confidence += 15
        elif volume_ratio > 30:
            score += 10; confidence += 10
        elif volume_ratio > 20:
            score += 5; confidence += 5
        score = max(0, min(100, score))
        confidence = max(0, min(100, confidence))
        
        if score >= 80 and abs_1h > 2.5:
            signal = "🟢🔥 HIZLI ALIŞ"
        elif score >= 70:
            signal = "🟢 ALIŞ"
        elif score >= 60:
            signal = "🟡 DİKKAT"
        elif score <= 25 and abs_1h > 2.5:
            signal = "🔴🔥 HIZLI SATIŞ"
        elif score <= 35:
            signal = "🔴 SATIŞ"
        else:
            signal = "⚪ BEKLE"
        
        return {
            "symbol": symbol,
            "price": price,
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "change_1h": change_1h,
            "change_24h": change_24h,
            "volume_ratio": volume_ratio
        }
    except Exception as e:
        logger.error(f"Analiz hatası ({coin.get('symbol', '?')}): {e}")
        return None

def run_analysis():
    global bot_data
    with LOCK:
        if bot_data["analyzing"]:
            logger.info("Analiz zaten çalışıyor, atlanıyor")
            return
        bot_data["analyzing"] = True
        bot_data["status"] = "Analiz yapılıyor..."
    
    try:
        logger.info("Analiz başlatılıyor...")
        coins = get_coins_with_volume()
        
        if not coins:
            with LOCK:
                bot_data["status"] = "❌ Veri alınamadı - lütfen internet bağlantınızı kontrol edin"
                bot_data["analyzing"] = False
            return
        
        all_analyses = []
        recommendations = []
        buy_count = 0
        sell_count = 0
        
        for coin in coins:
            analysis = analyze_volatility(coin)
            if not analysis:
                continue
            all_analyses.append(analysis)
            
            if "ALIŞ" in analysis["signal"] or "SATIŞ" in analysis["signal"]:
                is_buy = "ALIŞ" in analysis["signal"]
                name_upper = coin.get("name", "").upper()
                recommendations.append({
                    "symbol": analysis["symbol"],
                    "name": name_upper,
                    "price": f"${analysis['price']:.4f}" if analysis['price'] < 1 else f"${analysis['price']:.2f}",
                    "signal": analysis["signal"],
                    "score": analysis["score"],
                    "confidence": analysis["confidence"],
                    "change_1h": f"{analysis['change_1h']:+.2f}%",
                    "change_24h": f"{analysis['change_24h']:+.2f}%",
                    "volume": f"{analysis['volume_ratio']:.1f}%",
                    "timestamp": datetime.now(TZ_TR).strftime("%H:%M:%S")
                })
                if is_buy:
                    buy_count += 1
                else:
                    sell_count += 1
            
            logger.debug(f"{analysis['symbol']}: {analysis['signal']} (Skor:{analysis['score']}, Vol:{analysis['volume_ratio']:.1f}%)")
        
        save_recommendations_bulk(all_analyses)
        clean_old_records(keep_days=7)
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        
        with LOCK:
            bot_data["recommendations"] = recommendations
            bot_data["last_update"] = datetime.now(TZ_TR).strftime("%H:%M:%S")
            bot_data["total_analyzed"] = len(coins)
            bot_data["buy_count"] = buy_count
            bot_data["sell_count"] = sell_count
            bot_data["status"] = f"✓ {len(coins)} coin | {len(recommendations)} volatil"
            bot_data["analyzing"] = False
        
        logger.info(f"Analiz tamamlandı - ALIŞ:{buy_count}, SATIŞ:{sell_count}, Toplam sinyal:{len(recommendations)}")
        
    except Exception as e:
        logger.error(f"Analiz hatası: {e}", exc_info=True)
        with LOCK:
            bot_data["status"] = f"❌ {str(e)[:50]}"
            bot_data["analyzing"] = False

# --- Otomatik döngü ---
def auto_bot_loop():
    init_db()
    logger.info("🔄 Otomatik bot döngüsü başladı")
    run_analysis()
    while True:
        time.sleep(300)
        run_analysis()

bot_thread = threading.Thread(target=auto_bot_loop, daemon=True)
bot_thread.start()

# --- HTML şablonu (öncekiyle aynı) ---
HTML_TEMPLATE = """<!DOCTYPE html>
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
            flex-wrap: wrap;
        }
        h1 { margin: 0; color: var(--accent-blue); font-size: 24px; }
        .stats {
            display: flex;
            gap: 20px;
            font-size: 13px;
            flex-wrap: wrap;
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
            white-space: nowrap;
        }
        .status-badge.analyzing {
            background: rgba(56, 189, 248, 0.2);
            color: var(--accent-blue);
            border-color: var(--accent-blue);
            animation: pulse 1s infinite;
        }
        .status-badge.error {
            background: rgba(239, 68, 68, 0.2);
            color: var(--sell-color);
            border-color: var(--sell-color);
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        
        .card {
            background-color: var(--card-bg);
            border-radius: 12px;
            padding: 24px;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            margin-bottom: 25px;
        }
        .card h3 { margin-top: 0; color: var(--text-muted); }
        
        .btn {
            padding: 12px 24px;
            border-radius: 6px;
            border: none;
            background: var(--accent-blue);
            color: #0f172a;
            font-weight: bold;
            cursor: pointer;
            font-size: 14px;
            transition: opacity 0.2s;
        }
        .btn:hover:not(:disabled) { opacity: 0.9; }
        .btn:disabled {
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
            flex-wrap: wrap;
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
            flex: 1;
            min-width: 150px;
        }
        .signal-left h4 {
            margin: 0 0 5px 0;
            font-size: 16px;
        }
        .signal-left p {
            margin: 0 0 3px 0;
            font-size: 12px;
            color: var(--text-muted);
        }
        
        .signal-right {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .box {
            text-align: center;
            padding: 8px 12px;
            background: #0f172a;
            border-radius: 4px;
            border: 1px solid var(--border-color);
            min-width: 60px;
        }
        .box-value {
            font-weight: bold;
            font-size: 14px;
            color: var(--accent-blue);
        }
        .box-label {
            font-size: 10px;
            color: var(--text-muted);
            margin-top: 2px;
        }
        
        .empty-state {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
        }
        
        .loading { animation: pulse 1s infinite; }
        .update-info {
            color: var(--text-muted);
            font-size: 12px;
            margin-left: 15px;
        }
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
            <button class="btn" id="analyzeBtn" onclick="startAnalysis()">
                🔄 ANALİZ YAP
            </button>
            <span id="analyzeStatus" class="update-info"></span>

            <h3 style="margin-top: 20px;">📊 Volatil Coinler</h3>
            <div id="signals">
                <div class="empty-state">Analiz butonuna basın veya otomatik çalışmasını bekleyin...</div>
            </div>
        </div>
    </div>

    <script>
        function startAnalysis() {
            const btn = document.getElementById('analyzeBtn');
            const status = document.getElementById('analyzeStatus');
            btn.disabled = true;
            status.textContent = "⏳ Analiz başlatılıyor...";
            fetch('/api/analyze', { method: 'POST' })
                .then(() => {
                    status.textContent = "✅ Analiz başladı, sonuçlar gelecek...";
                    setTimeout(() => { update(); status.textContent = ""; }, 2000);
                })
                .catch(() => { status.textContent = "❌ Hata oluştu"; btn.disabled = false; });
        }

        function update() {
            fetch('/api/signals')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('analyzed').textContent = data.total_analyzed;
                    document.getElementById('buyCount').textContent = data.buy_count;
                    document.getElementById('sellCount').textContent = data.sell_count;
                    document.getElementById('lastUpdate').textContent = data.last_update || '--:--';
                    
                    const statusEl = document.getElementById('status');
                    statusEl.textContent = data.status;
                    statusEl.className = 'status-badge';
                    if (data.analyzing) statusEl.classList.add('analyzing');
                    else if (data.status && data.status.includes('❌')) statusEl.classList.add('error');
                    
                    const btn = document.getElementById('analyzeBtn');
                    if (data.analyzing) {
                        btn.disabled = true;
                        document.getElementById('analyzeStatus').textContent = '⏳ Analiz devam ediyor...';
                    } else {
                        btn.disabled = false;
                        const st = document.getElementById('analyzeStatus');
                        if (st.textContent.includes('devam')) {
                            st.textContent = '✅ Analiz tamamlandı';
                            setTimeout(() => st.textContent = '', 3000);
                        }
                    }

                    const container = document.getElementById('signals');
                    if (!data.recommendations || data.recommendations.length === 0) {
                        container.innerHTML = '<div class="empty-state">Henüz volatil coin bulunamadı</div>';
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
                                    <p>${r.symbol} - ${r.name}</p>
                                    <p>${r.price} | ${r.timestamp}</p>
                                </div>
                                <div class="signal-right">
                                    <div class="box">
                                        <div class="box-value" style="color: ${priceColor}">${r.change_1h}</div>
                                        <div class="box-label">1h</div>
                                    </div>
                                    <div class="box">
                                        <div class="box-value" style="color: var(--buy-color)">${r.volume}</div>
                                        <div class="box-label">Hacim</div>
                                    </div>
                                    <div class="box">
                                        <div class="box-value">${r.score}</div>
                                        <div class="box-label">Skor</div>
                                    </div>
                                    <div class="box">
                                        <div class="box-value">${r.confidence}%</div>
                                        <div class="box-label">Güven</div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('');
                })
                .catch(e => console.log('Güncelleme hatası:', e));
        }

        setInterval(update, 5000);
        update();
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/signals")
def api_signals():
    with LOCK:
        return jsonify(bot_data)

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    threading.Thread(target=run_analysis, daemon=True).start()
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)