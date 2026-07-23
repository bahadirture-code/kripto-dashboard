from flask import Flask, render_template_string, request, redirect, url_for
import os
import json
from datetime import datetime

app = Flask(__name__)

# Veri dosyası
DATA_FILE = "market_opportunities.json"

def load_opportunities():
    """JSON dosyasından verileri yükle"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_opportunities(data):
    """Verileri JSON dosyasına kaydet"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def validate_input(name, price, change, volume, reason, signal):
    """Input validasyonu"""
    errors = []
    
    if not name or len(name) < 2 or len(name) > 50:
        errors.append("Varlık adı 2-50 karakter olmalı")
    if not price or not any(c.isdigit() for c in price):
        errors.append("Geçerli fiyat girin")
    if not change or "%" not in change:
        errors.append("Değişim % ile bitmelidir")
    if not volume or len(volume) < 2:
        errors.append("Hacim girin")
    if not reason or len(reason) < 5:
        errors.append("Gerekçe en az 5 karakter olmalı")
    if signal not in ["VOLATİL ATAK (AL)", "GÜÇLÜ MOMENTUM", "DİP FIRSATI", "İZLE & TOPLA"]:
        errors.append("Geçerli sinyal seçin")
    
    return errors

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
        .status { color: var(--buy-color); font-weight: bold; font-size: 12px; }
        .card { 
            background-color: var(--card-bg); 
            border-radius: 12px; 
            padding: 24px; 
            border: 1px solid var(--border-color); 
            box-shadow: 0 4px 6px rgba(0,0,0,0.3); 
            margin-bottom: 25px; 
        }
        .card h3 { margin-top: 0; color: var(--text-muted); font-size: 16px; }
        
        /* Form */
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 5px; text-transform: uppercase; }
        input, select, textarea { 
            padding: 10px 12px; 
            margin-right: 10px; 
            margin-bottom: 10px; 
            border-radius: 6px; 
            border: 1px solid var(--border-color); 
            background: #0f172a; 
            color: var(--text-color);
            width: calc(100% - 100px);
        }
        input:focus, select:focus, textarea:focus { 
            outline: none; 
            border-color: var(--accent-blue);
            box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2);
        }
        textarea { width: 100%; min-height: 60px; resize: vertical; }
        .form-row { display: flex; flex-wrap: wrap; gap: 10px; }
        
        /* Error/Success */
        .error-msg { 
            background: rgba(239,68,68,0.1); 
            border: 1px solid var(--sell-color); 
            color: var(--sell-color);
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 15px;
            font-size: 13px;
        }
        .error-msg ul { margin: 5px 0 0 0; padding-left: 20px; }
        
        .success-msg { 
            background: rgba(34,197,94,0.1); 
            border: 1px solid var(--buy-color); 
            color: var(--buy-color);
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 15px;
        }
        
        /* Search */
        .search-box { 
            margin-bottom: 20px;
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        .search-box input { width: 300px; }
        .search-box select { width: auto; padding: 10px 12px; }
        
        /* Buttons */
        button { 
            background: var(--accent-blue); 
            color: #0f172a; 
            font-weight: bold; 
            cursor: pointer; 
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            transition: opacity 0.2s;
        }
        button:hover { opacity: 0.9; }
        
        .btn-delete { 
            background: var(--sell-color); 
            color: white; 
            padding: 6px 12px; 
            border-radius: 4px; 
            text-decoration: none; 
            font-size: 11px; 
            font-weight: bold;
            border: none;
            cursor: pointer;
        }
        .btn-delete:hover { opacity: 0.8; }
        
        /* Table */
        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-top: 15px;
        }
        th, td { 
            padding: 14px; 
            text-align: left; 
            border-bottom: 1px solid var(--border-color); 
            font-size: 14px;
        }
        th { 
            background-color: #111827; 
            color: var(--text-muted); 
            font-size: 11px; 
            text-transform: uppercase;
            font-weight: 600;
        }
        tr:hover { background-color: rgba(56, 189, 248, 0.05); }
        
        /* Badge */
        .badge { 
            padding: 6px 12px; 
            border-radius: 6px; 
            font-weight: bold; 
            font-size: 11px; 
            display: inline-block;
        }
        .badge-buy { 
            background: rgba(34,197,94,0.2); 
            color: var(--buy-color); 
            border: 1px solid var(--buy-color); 
        }
        
        /* Change Color */
        .change-positive { color: var(--buy-color); font-weight: 600; }
        .change-negative { color: var(--sell-color); font-weight: 600; }
        
        .empty-state { 
            text-align: center; 
            padding: 40px; 
            color: var(--text-muted);
        }
        
        @media (max-width: 768px) {
            input, select, textarea { width: 100%; }
            header { flex-direction: column; gap: 15px; }
            table { font-size: 12px; }
            th, td { padding: 10px 8px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 Kısa Vade Hacim Patlaması & Yönetim Paneli</h1>
            <span class="status">● Dinamik Kontrol Aktif</span>
        </header>

        {% if error %}
        <div class="error-msg">
            <strong>❌ Hata!</strong>
            <ul>
            {% for err in error %}
                <li>{{ err }}</li>
            {% endfor %}
            </ul>
        </div>
        {% endif %}

        {% if success %}
        <div class="success-msg">✓ {{ success }}</div>
        {% endif %}

        <!-- Form Kartı -->
        <div class="card">
            <h3>➕ Listeye Yeni Fırsat / Coin Ekle</h3>
            <form action="/add" method="POST">
                <div class="form-row">
                    <div style="flex: 1; min-width: 200px;">
                        <label>Coin Adı *</label>
                        <input type="text" name="name" placeholder="Örn: SOL, PEPE" required maxlength="50">
                    </div>
                    <div style="flex: 1; min-width: 200px;">
                        <label>Fiyat *</label>
                        <input type="text" name="price" placeholder="Örn: $145.00" required maxlength="20">
                    </div>
                </div>
                <div class="form-row">
                    <div style="flex: 1; min-width: 200px;">
                        <label>24s Değişim *</label>
                        <input type="text" name="change" placeholder="Örn: +12.5%" required maxlength="20">
                    </div>
                    <div style="flex: 1; min-width: 200px;">
                        <label>Hacim *</label>
                        <input type="text" name="volume" placeholder="Örn: $500M" required maxlength="30">
                    </div>
                </div>
                <div class="form-group">
                    <label>Gerekçe / Not *</label>
                    <textarea name="reason" placeholder="Neden bu fırsatı takip ediyorsun?" required maxlength="200"></textarea>
                </div>
                <div class="form-row">
                    <div style="flex: 1; min-width: 200px;">
                        <label>Sinyal Türü *</label>
                        <select name="signal" required style="width: 100%;">
                            <option value="">Seç...</option>
                            <option value="VOLATİL ATAK (AL)">🔥 VOLATİL ATAK (AL)</option>
                            <option value="GÜÇLÜ MOMENTUM">📈 GÜÇLÜ MOMENTUM</option>
                            <option value="DİP FIRSATI">🎯 DİP FIRSATI</option>
                            <option value="İZLE & TOPLA">👁️ İZLE & TOPLA</option>
                        </select>
                    </div>
                </div>
                <button type="submit">✓ Listeye Ekle</button>
            </form>
        </div>

        <!-- Liste Kartı -->
        <div class="card">
            <h3>Anlık Takip Edilen Fırsatlar ({{ total }})</h3>
            
            {% if opportunities %}
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="🔍 Coin adı, sinyal veya gerekçe ara...">
                <select id="sortSelect">
                    <option value="latest">En Yeni</option>
                    <option value="change-high">Değişim ↓ (Yüksek)</option>
                    <option value="change-low">Değişim ↑ (Düşük)</option>
                </select>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Varlık</th>
                        <th>Fiyat</th>
                        <th>24s Değişim</th>
                        <th>Hacim</th>
                        <th>Gerekçe</th>
                        <th>Sinyal</th>
                        <th>Aksiyon</th>
                    </tr>
                </thead>
                <tbody id="tableBody">
                    {% for item in opportunities %}
                    <tr class="data-row" data-name="{{ item.name }}" data-signal="{{ item.signal }}" data-change="{{ item.change_val }}">
                        <td><strong>{{ item.name }}</strong></td>
                        <td>{{ item.price }}</td>
                        <td>
                            {% if item.change_val >= 0 %}
                            <span class="change-positive">{{ item.change }}</span>
                            {% else %}
                            <span class="change-negative">{{ item.change }}</span>
                            {% endif %}
                        </td>
                        <td style="color: var(--text-muted); font-size: 13px;">{{ item.volume }}</td>
                        <td>{{ item.reason }}</td>
                        <td><span class="badge badge-buy">{{ item.signal }}</span></td>
                        <td><a href="/delete/{{ item.id }}" class="btn-delete" onclick="return confirm('Silmek istediğine emin misin?')">🗑️ Sil</a></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty-state">
                <p>📭 Henüz veri yok. İlk fırsatını ekleye başla!</p>
            </div>
            {% endif %}
        </div>
    </div>

    <script>
        document.getElementById('searchInput')?.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            document.querySelectorAll('.data-row').forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        });

        document.getElementById('sortSelect')?.addEventListener('change', (e) => {
            const tbody = document.getElementById('tableBody');
            const rows = Array.from(tbody.querySelectorAll('.data-row'));
            
            if (e.target.value === 'latest') {
                rows.reverse();
            } else if (e.target.value === 'change-high') {
                rows.sort((a, b) => 
                    parseFloat(b.getAttribute('data-change')) - parseFloat(a.getAttribute('data-change'))
                );
            } else if (e.target.value === 'change-low') {
                rows.sort((a, b) => 
                    parseFloat(a.getAttribute('data-change')) - parseFloat(b.getAttribute('data-change'))
                );
            }
            
            rows.forEach(row => tbody.appendChild(row));
        });
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    opportunities = load_opportunities()
    return render_template_string(
        HTML_TEMPLATE, 
        opportunities=opportunities,
        total=len(opportunities),
        error=None,
        success=None
    )

@app.route("/add", methods=["POST"])
def add_opportunity():
    name = request.form.get("name", "").strip()
    price = request.form.get("price", "").strip()
    change = request.form.get("change", "").strip()
    volume = request.form.get("volume", "").strip()
    reason = request.form.get("reason", "").strip()
    signal = request.form.get("signal", "").strip()

    # Validasyon
    errors = validate_input(name, price, change, volume, reason, signal)
    if errors:
        opportunities = load_opportunities()
        return render_template_string(
            HTML_TEMPLATE,
            opportunities=opportunities,
            total=len(opportunities),
            error=errors,
            success=None
        )

    # Değişim değerini parse et
    try:
        change_val = float(change.replace("%", "").replace("+", ""))
    except:
        change_val = 0.0

    # Yeni varlık
    opportunities = load_opportunities()
    new_id = max([item["id"] for item in opportunities], default=0) + 1
    
    new_item = {
        "id": new_id,
        "name": name,
        "price": price,
        "change": change,
        "change_val": change_val,
        "volume": volume,
        "reason": reason,
        "signal": signal,
        "badge": "buy",
        "added_at": datetime.now().isoformat()
    }
    
    opportunities.append(new_item)
    save_opportunities(opportunities)
    
    return render_template_string(
        HTML_TEMPLATE,
        opportunities=opportunities,
        total=len(opportunities),
        error=None,
        success=f"✓ {name} başarıyla eklendi!"
    )

@app.route("/delete/<int:item_id>")
def delete_opportunity(item_id):
    opportunities = load_opportunities()
    deleted_name = None
    
    for item in opportunities:
        if item["id"] == item_id:
            deleted_name = item["name"]
            break
    
    opportunities = [item for item in opportunities if item["id"] != item_id]
    save_opportunities(opportunities)
    
    return redirect(url_for('index'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)