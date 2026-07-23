from flask import Flask, render_template_string, jsonify
import requests
import threading
import time
from datetime import datetime, timedelta
import json

app = Flask(__name__)

# Global veri
scanner_data = {
    "opportunities": [],
    "last_update": None,
    "status": "Scanning...",
    "total_scanned": 0
}

# Binance API endpoints
BINANCE_API = "https://api.binance.com/api/v3"

def get_top_symbols():
    """Top 200 USDT coinleri al"""
    try:
        url = f"{BINANCE_API}/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # USDT'de en yüksek volume'leri filtrele
        symbols = []
        for coin in data:
            if coin['symbol'].endswith('USDT'):
                try:
                    volume = float(coin['quoteAssetVolume'])
                    if volume > 10000000:  # $10M+ hacim
                        symbols.append(coin['symbol'])
                except:
                    pass
        
        return sorted(symbols)[:200]  # Top 200
    except Exception as e:
        print(f"Error getting symbols: {e}")
        return []

def get_kline_data(symbol, interval="1h"):
    """Mum verisini al (1h ve 4h)"""
    try:
        url = f"{BINANCE_API}/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": 50
        }
        response = requests.get(url, params=params, timeout=5)
        return response.json()
    except:
        return None

def calculate_volume_spike(symbol):
    """Volume spike hesapla"""
    try:
        # 1h ve 4h veri al
        klines_1h = get_kline_data(symbol, "1h")
        klines_4h = get_kline_data(symbol, "4h")
        
        if not klines_1h or len(klines_1h) < 2:
            return None
        
        # Son 1h volume
        current_volume = float(klines_1h[-1][7])  # quote asset volume
        
        # Ortalama volume (son 20 saat)
        avg_volume = sum([float(k[7]) for k in klines_1h[:-1]]) / len(klines_1h[:-1]) if len(klines_1h) > 1 else current_volume
        
        if avg_volume == 0:
            return None
        
        # Volume spike yüzdesi
        spike_percentage = ((current_volume - avg_volume) / avg_volume) * 100
        
        # Son 1h fiyat değişimi
        open_price = float(klines_1h[-1][1])
        close_price = float(klines_1h[-1][4])
        price_change = ((close_price - open_price) / open_price) * 100
        
        # 24h fiyat değişimi
        if klines_4h and len(klines_4h) > 6:
            open_24h = float(klines_4h[-6][1])
            close_24h = float(klines_4h[-1][4])
            change_24h = ((close_24h - open_24h) / open_24h) * 100
        else:
            change_24h = 0
        
        return {
            "volume_spike": spike_percentage,
            "current_volume": current_volume,
            "avg_volume": avg_volume,
            "price_change_1h": price_change,
            "price_change_24h": change_24h,
            "current_price": close_price
        }
    except Exception as e:
        print(f"Error calculating spike for {symbol}: {e}")
        return None

def analyze_volatility():
    """Volatility analizi yap"""
    global scanner_data
    
    scanner_data["status"] = "Scanning..."
    
    try:
        symbols = get_top_symbols()
        scanner_data["total_scanned"] = len(symbols)
        
        opportunities = []
        
        for i, symbol in enumerate(symbols):
            # Her 100 request'te rate limit'i aşmamak için
            if i % 20 == 0:
                time.sleep(0.5)
            
            analysis = calculate_volume_spike(symbol)
            
            if analysis:
                # Koşulları kontrol et
                volume_spike = analysis["volume_spike"]
                price_change = analysis["price_change_1h"]
                change_24h = analysis["price_change_24h"]
                
                # Volatilite trigger'ları
                trigger = False
                signal_type = ""
                confidence = 0
                
                # VOLATİL ATAK - Volume spike + fiyat artış
                if volume_spike > 50 and price_change > 2:
                    trigger = True
                    signal_type = "VOLATİL ATAK (AL)"
                    confidence = min(100, int((volume_spike / 100) * 50 + abs(price_change) * 5))
                
                # DİP FIRSATI - Volume spike + fiyat düşüş
                elif volume_spike > 40 and price_change < -1.5:
                    trigger = True
                    signal_type = "DİP FIRSATI"
                    confidence = min(100, int((volume_spike / 100) * 50 + abs(price_change) * 5))
                
                # GÜÇLÜ MOMENTUM - Yüksek 24h değişim + volume
                elif change_24h > 5 and volume_spike > 30:
                    trigger = True
                    signal_type = "GÜÇLÜ MOMENTUM"
                    confidence = min(100, int((change_24h / 10) * 50 + (volume_spike / 100) * 30))
                
                if trigger:
                    # Coin base adı (BTCUSDT -> BTC)
                    coin_name = symbol.replace("USDT", "")
                    
                    opportunity = {
                        "id": len(opportunities) + 1,
                        "name": coin_name,
                        "symbol": symbol,
                        "price": f"${analysis['current_price']:.2f}",
                        "price_val": analysis['current_price'],
                        "change_1h": f"{price_change:+.2f}%",
                        "change_24h": f"{change_24h:+.2f}%",
                        "volume": f"${analysis['current_volume']/1000000:.2f}M",
                        "volume_val": analysis['current_volume'],
                        "volume_spike": f"{volume_spike:+.1f}%",
                        "signal": signal_type,
                        "confidence": confidence,
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "reason": f"Volume spike: {volume_spike:.1f}% | 1h: {price_change:+.2f}% | 24h: {change_24h:+.2f}%"
                    }
                    opportunities.append(opportunity)
        
        # En yüksek confidence'a göre sırala
        opportunities.sort(key=lambda x: x["confidence"], reverse=True)
        
        scanner_data["opportunities"] = opportunities[:50]  # Top 50
        scanner_data["last_update"] = datetime.now().strftime("%H:%M:%S")
        scanner_data["status"] = f"✓ Hazır ({len(opportunities)} fırsat bulundu)"
        
    except Exception as e:
        scanner_data["status"] = f"❌ Hata: {str(e)}"
        print(f"Scanner error: {e}")

def scanner_loop():
    """Arka planda sürekli tarama yap"""
    while True:
        try:
            analyze_volatility()
            time.sleep(30)  # Her 30 saniye
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(30)

# Arka plan thread başlat
scanner_thread = threading.Thread(target=scanner_loop, daemon=True)
scanner_thread.start()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Volatility Scanner - Pump/Dump Tespiti</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #38bdf8;
            --buy-color: #22c55e;
            --sell-color: #ef4444;
            --orange: #f59e0b;
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
        .container { max-width: 1400px; margin: 0 auto; }
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
            gap: 30px; 
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
            display: inline-block;
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
        .card h3 { margin-top: 0; color: var(--text-muted); font-size: 16px; }
        
        .controls {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .filter-btn {
            padding: 8px 16px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            background: #0f172a;
            color: var(--text-color);
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            transition: all 0.2s;
        }
        .filter-btn.active {
            background: var(--accent-blue);
            color: #0f172a;
            border-color: var(--accent-blue);
        }
        .filter-btn:hover {
            border-color: var(--accent-blue);
        }
        
        table { 
            width: 100%; 
            border-collapse: collapse;
        }
        th, td { 
            padding: 14px; 
            text-align: left; 
            border-bottom: 1px solid var(--border-color); 
            font-size: 13px;
        }
        th { 
            background-color: #111827; 
            color: var(--text-muted); 
            font-size: 11px; 
            text-transform: uppercase;
            font-weight: 600;
        }
        tr:hover { background-color: rgba(56, 189, 248, 0.05); }
        
        .badge { 
            padding: 6px 12px; 
            border-radius: 6px; 
            font-weight: bold; 
            font-size: 10px;
            display: inline-block;
            white-space: nowrap;
        }
        .badge-attack { 
            background: rgba(239, 68, 68, 0.2); 
            color: var(--sell-color); 
            border: 1px solid var(--sell-color);
        }
        .badge-dip { 
            background: rgba(245, 158, 11, 0.2); 
            color: var(--orange); 
            border: 1px solid var(--orange);
        }
        .badge-momentum { 
            background: rgba(34, 197, 94, 0.2); 
            color: var(--buy-color); 
            border: 1px solid var(--buy-color);
        }
        
        .price-up { color: var(--buy-color); font-weight: 600; }
        .price-down { color: var(--sell-color); font-weight: 600; }
        
        .volume-spike { 
            color: var(--sell-color); 
            font-weight: 600;
        }
        
        .confidence-bar {
            width: 100%;
            height: 20px;
            background: #0f172a;
            border-radius: 4px;
            overflow: hidden;
            border: 1px solid var(--border-color);
        }
        .confidence-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--buy-color), var(--accent-blue));
            transition: width 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 600;
            color: #0f172a;
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
            .stats { flex-direction: column; gap: 10px; }
            table { font-size: 11px; }
            th, td { padding: 10px 6px; }
            .badge { padding: 4px 8px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>🔍 Volatility Scanner</h1>
                <span style="color: var(--text-muted); font-size: 12px;">Real-time Pump/Dump Tespiti</span>
            </div>
            <div class="stats">
                <div class="stat">
                    <span class="stat-value" id="oppCount">0</span>
                    <span class="stat-label">Fırsat Bulundu</span>
                </div>
                <div class="stat">
                    <span class="stat-value" id="lastUpdate">--:--</span>
                    <span class="stat-label">Son Güncelleme</span>
                </div>
                <div class="stat">
                    <span class="status-badge loading" id="status">● Taranıyor...</span>
                </div>
            </div>
        </header>

        <div class="card">
            <h3>📊 Anlık Volatilite Fırsatları</h3>
            
            <div class="controls">
                <button class="filter-btn active" onclick="filterTable('all')">Tümü</button>
                <button class="filter-btn" onclick="filterTable('VOLATİL ATAK (AL)')">🔥 Volatil Atak</button>
                <button class="filter-btn" onclick="filterTable('DİP FIRSATI')">🎯 Dip Fırsatı</button>
                <button class="filter-btn" onclick="filterTable('GÜÇLÜ MOMENTUM')">📈 Momentum</button>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Coin</th>
                        <th>Fiyat</th>
                        <th>1h Değişim</th>
                        <th>24h Değişim</th>
                        <th>Volume Spike</th>
                        <th>Sinyal</th>
                        <th>Güven</th>
                        <th>Saat</th>
                    </tr>
                </thead>
                <tbody id="tableBody">
                    <tr>
                        <td colspan="8" class="empty-state">
                            <div class="loading">Veriler yükleniyor...</div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let currentFilter = 'all';

        function updateTable() {
            fetch('/api/data')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('tableBody');
                    
                    document.getElementById('oppCount').textContent = data.opportunities.length;
                    document.getElementById('lastUpdate').textContent = data.last_update || '--:--';
                    
                    const status = document.getElementById('status');
                    status.textContent = data.status;
                    if (data.status.includes('Hazır')) {
                        status.classList.remove('loading');
                    } else {
                        status.classList.add('loading');
                    }

                    if (data.opportunities.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Henüz fırsat bulunmadı. Tarama devam ediyor...</td></tr>';
                        return;
                    }

                    tbody.innerHTML = data.opportunities.map(opp => {
                        let badgeClass = 'badge-momentum';
                        if (opp.signal.includes('ATAK')) badgeClass = 'badge-attack';
                        if (opp.signal.includes('DİP')) badgeClass = 'badge-dip';

                        const change1hClass = parseFloat(opp.change_1h) >= 0 ? 'price-up' : 'price-down';
                        const change24hClass = parseFloat(opp.change_24h) >= 0 ? 'price-up' : 'price-down';

                        return `
                            <tr class="data-row" data-signal="${opp.signal}">
                                <td><strong>${opp.name}</strong></td>
                                <td>${opp.price}</td>
                                <td class="${change1hClass}">${opp.change_1h}</td>
                                <td class="${change24hClass}">${opp.change_24h}</td>
                                <td class="volume-spike">${opp.volume_spike}</td>
                                <td><span class="badge ${badgeClass}">${opp.signal}</span></td>
                                <td>
                                    <div class="confidence-bar">
                                        <div class="confidence-fill" style="width: ${opp.confidence}%">
                                            ${opp.confidence}%
                                        </div>
                                    </div>
                                </td>
                                <td>${opp.timestamp}</td>
                            </tr>
                        `;
                    }).join('');

                    filterTable(currentFilter);
                })
                .catch(err => {
                    console.error('Error:', err);
                    document.getElementById('status').textContent = '❌ Bağlantı hatası';
                });
        }

        function filterTable(signal) {
            currentFilter = signal;
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event?.target?.classList.add('active');

            document.querySelectorAll('.data-row').forEach(row => {
                if (signal === 'all' || row.getAttribute('data-signal') === signal) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }

        // İlk yükleme + her 10 saniyede güncelle
        updateTable();
        setInterval(updateTable, 10000);
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/data")
def api_data():
    return jsonify(scanner_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
