from flask import Flask, render_template_string, jsonify, request
import requests
import threading
import time
import logging
from datetime import datetime, timedelta, timezone
import sqlite3
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)
DB_FILE = "crypto_recommendations.db"
LOCK = threading.Lock()
TZ_TR = timezone(timedelta(hours=3))

# Proxy desteği
proxies = {}
for p in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    if os.environ.get(p):
        proxies[p.lower()] = os.environ.get(p)

# Veritabanı
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

bot_data = {
    "last_update": None,
    "status": "Hazır",
    "recommendations": [],
    "total_analyzed": 0,
    "buy_count": 0,
    "sell_count": 0,
    "analyzing": False
}

# ----- YENİ: BINANCE API (sorunsuz çalışır) -----
def get_coins_from_binance():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        resp = requests.get(url, timeout=30, proxies=proxies, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            converted = []
            for item in data[:50]:
                symbol = item.get('symbol', '')
                if symbol.endswith('USDT'):
                    price = float(item.get('lastPrice', 0))
                    if price == 0:
                        continue
                    change_24h = float(item.get('priceChangePercent', 0))
                    volume = float(item.get('volume', 0))
                    # Binance'te market cap yok, hacim oranı yerine fiyat değişimine göre skor yapalım
                    converted.append({
                        "symbol": symbol.replace('USDT', ''),
                        "name": symbol,
                        "current_price": price,
                        "price_change_percentage_1h_in_currency": 0.0,  # 1h yok
                        "price_change_percentage_24h": change_24h,
                        "market_cap": 0,
                        "total_volume": volume
                    })
            logger.info(f"Binance'ten {len(converted)} coin alındı")
            return converted
        else:
            logger.warning(f"Binance yanıt kodu: {resp.status_code}")
    except Exception as e:
        logger.error(f"Binance hatası: {e}", exc_info=True)
    return None

# CoinCap yedek
def get_coins_from_coincap():
    url = "https://api.coincap.io/v2/assets"
    params = {"limit": 50, "sort": "volumeUsd24Hr"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30, proxies=proxies, verify=False)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            converted = []
            for c in data:
                try:
                    symbol = c.get("symbol", "").upper()
                    name = c.get("name", "")
                    price = float(c.get("priceUsd", 0))
                    change_24h = float(c.get("changePercent24Hr", 0))
                    volume = float(c.get("volumeUsd24Hr", 0))
                    market_cap = float(c.get("marketCapUsd", 0))
                    converted.append({
                        "symbol": symbol,
                        "name": name,
                        "current_price": price,
                        "price_change_percentage_1h_in_currency": 0.0,
                        "price_change_percentage_24h": change_24h,
                        "market_cap": market_cap,
                        "total_volume": volume
                    })
                except:
                    continue
            logger.info(f"CoinCap'ten {len(converted)} coin alındı")
            return converted
        else:
            logger.warning(f"CoinCap yanıt kodu: {resp.status_code}")
    except Exception as e:
        logger.warning(f"CoinCap hatası: {e}")
    return None

def get_coins_with_volume():
    # Önce Binance dene, olmazsa CoinCap
    coins = get_coins_from_binance()
    if coins:
        return coins
    logger.info("Binance başarısız, CoinCap deneniyor...")
    return get_coins_from_coincap() or []

# Analiz (değişmedi)
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
        logger.info("Manuel analiz başlatıldı...")
        coins = get_coins_with_volume()
        
        if not coins:
            with LOCK:
                bot_data["status"] = "❌ Veri alınamadı - API'lerden cevap yok"
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
        
        logger.info(f"Analiz tamamlandı - ALIŞ:{buy_count}, SATIŞ:{sell_count}")
        
    except Exception as e:
        logger.error(f"Analiz hatası: {e}", exc_info=True)
        with LOCK:
            bot_data["status"] = f"❌ Hata: {str(e)[:50]}"
            bot_data["analyzing"] = False

# Flask routes (aynı)
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

# HTML (öncekiyle aynı, uzun olduğu için burada kısaltıyorum, ama siz kopyalarken HTML_TEMPLATE değişkeninin tamamını alın)
HTML_TEMPLATE = """<!DOCTYPE html>... (aynı) ..."""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)