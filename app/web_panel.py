"""
Modern and clean Web Management Dashboard for Gamblit Promo Code Auto-Redeemer.
Allows:
- Real-time status monitoring (Uptime, WebSocket, Account, DL Balances)
- Manual Code Redeem
- Settings Management (.env editor: Discord Token, Channel ID, Cookies)
- Captcha Pool Management (Inject token or test solver)
- Code history and live stats table
"""
import asyncio
import json
import os
import time
from typing import Optional, Any, Dict
from pathlib import Path
from aiohttp import web
from app.config import Config, cfg
from app.database import Database
from app.gamblit_client import GamblitClient
from app.metrics import MetricsTracker
from app.queue import RedeemQueue
from app.captcha_pool import CaptchaPool
from app.models import ParsedCode, RedeemLatency
from app.logging_config import get_recent_logs

HTML_TEMPLATE = """<!DOCTYPE html>

<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gamblit Auto-Redeemer Pro Paneli</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #07090e;
            --bg-surface: #0c1017;
            --card-bg: rgba(16, 22, 34, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-hover: rgba(23, 32, 48, 0.9);
            --border: #1a2332;
            --border-glow: rgba(56, 189, 248, 0.25);
            --accent: #38bdf8;
            --accent-gradient: linear-gradient(135deg, #38bdf8 0%, #6366f1 100%);
            --accent-glow: rgba(56, 189, 248, 0.2);
            --green: #10b981;
            --green-glow: rgba(16, 185, 129, 0.2);
            --red: #f43f5e;
            --yellow: #f59e0b;
            --purple: #a855f7;
            --text-dim: #64748b;
            --text: #94a3b8;
            --text-bright: #f8fafc;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            background-image: 
                radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.07) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(99, 102, 241, 0.07) 0px, transparent 50%),
                radial-gradient(at 50% 100%, rgba(16, 185, 129, 0.04) 0px, transparent 60%);
            background-attachment: fixed;
            color: var(--text);
            padding: 32px 24px 60px 24px;
            max-width: 1320px;
            margin: auto;
            -webkit-font-smoothing: antialiased;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(12, 16, 23, 0.6);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 20px 24px;
            margin-bottom: 28px;
            flex-wrap: wrap;
            gap: 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
        }
        .header-title-box { display: flex; align-items: center; gap: 16px; }
        .logo-icon {
            width: 48px; height: 48px;
            background: var(--accent-gradient);
            border-radius: 14px;
            display: flex; align-items: center; justify-content: center;
            font-size: 24px;
            box-shadow: 0 0 24px rgba(56, 189, 248, 0.4);
            flex-shrink: 0;
        }
        h1 { font-size: 22px; font-weight: 800; color: var(--text-bright); letter-spacing: -0.5px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 20px; margin-bottom: 24px; }
        
        .card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 22px;
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.35);
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
            overflow: hidden;
        }
        .card:hover {
            border-color: rgba(56, 189, 248, 0.25);
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.45);
        }
        .card h2 {
            font-size: 11.5px;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            color: #94a3b8;
            margin-bottom: 14px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .metric-val {
            font-size: 28px;
            font-weight: 800;
            color: var(--text-bright);
            letter-spacing: -0.5px;
            font-family: 'JetBrains Mono', monospace;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.2px;
            backdrop-filter: blur(10px);
            transition: all 0.2s ease;
        }
        .badge-online { 
            background: rgba(16, 185, 129, 0.12); 
            color: #34d399; 
            border: 1px solid rgba(16, 185, 129, 0.35); 
            box-shadow: 0 0 16px rgba(16, 185, 129, 0.15); 
        }
        .badge-offline { 
            background: rgba(244, 63, 94, 0.12); 
            color: #fb7185; 
            border: 1px solid rgba(244, 63, 94, 0.35); 
        }
        .badge-purple { 
            background: rgba(168, 85, 247, 0.12); 
            color: #c084fc; 
            border: 1px solid rgba(168, 85, 247, 0.35); 
        }
        .badge-yellow { 
            background: rgba(245, 158, 11, 0.12); 
            color: #fbbf24; 
            border: 1px solid rgba(245, 158, 11, 0.35); 
        }
        
        .progress-bar-container {
            width: 100%;
            height: 8px;
            background: rgba(30, 41, 59, 0.8);
            border-radius: 6px;
            overflow: hidden;
            margin-top: 10px;
            margin-bottom: 16px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .progress-bar {
            height: 100%;
            background: #10b981;
            width: 0%;
            transition: width 0.5s linear, background-color 0.3s;
            box-shadow: 0 0 12px rgba(16, 185, 129, 0.6);
        }

        .form-group { margin-bottom: 16px; }
        label { 
            display: block; 
            font-size: 11px; 
            font-weight: 700; 
            margin-bottom: 7px; 
            color: #94a3b8; 
            letter-spacing: 0.8px; 
            text-transform: uppercase; 
        }
        input, textarea {
            width: 100%;
            background: #090d14;
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: var(--text-bright);
            padding: 11px 15px;
            border-radius: 10px;
            font-size: 13px;
            font-family: 'JetBrains Mono', monospace;
            transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
        }
        input::placeholder, textarea::placeholder {
            color: #475569;
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-size: 12.5px;
        }
        input:focus, textarea:focus {
            outline: none;
            border-color: var(--accent);
            background: #0a0f18;
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
        }
        button {
            background: #10b981;
            color: white;
            border: none;
            padding: 11px 20px;
            border-radius: 10px;
            font-weight: 700;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 7px;
            justify-content: center;
        }
        button:hover { 
            opacity: 0.94; 
            transform: translateY(-1.5px); 
            box-shadow: 0 6px 16px rgba(16, 185, 129, 0.3); 
        }
        button:active { transform: translateY(0); }
        button:disabled { opacity: 0.45; cursor: not-allowed; transform: none; box-shadow: none; }
        button.btn-alt { 
            background: rgba(30, 41, 59, 0.7); 
            border: 1px solid rgba(255, 255, 255, 0.1); 
            color: var(--text-bright); 
        }
        button.btn-alt:hover { 
            background: rgba(51, 65, 85, 0.85); 
            box-shadow: 0 6px 16px rgba(0,0,0,0.3); 
            border-color: rgba(255, 255, 255, 0.2);
        }
        button.btn-accent { 
            background: #0284c7; 
        }
        button.btn-accent:hover { 
            background: #0369a1; 
            box-shadow: 0 6px 16px rgba(2, 132, 199, 0.35); 
        }
        button.btn-danger { 
            background: rgba(244, 63, 94, 0.12); 
            border: 1px solid rgba(244, 63, 94, 0.35); 
            color: #fb7185; 
        }
        button.btn-danger:hover { 
            background: #f43f5e; 
            color: white; 
            box-shadow: 0 6px 16px rgba(244, 63, 94, 0.3);
        }
        
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { padding: 13px 16px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px; }
        th { color: #64748b; font-size: 11px; text-transform: uppercase; font-weight: 700; letter-spacing: 0.8px; }
        tr:hover td { background: rgba(255, 255, 255, 0.02); }
        .code-cell { font-family: 'JetBrains Mono', monospace; font-weight: 700; color: var(--accent); }
        
        details summary {
            cursor: pointer;
            color: var(--accent);
            font-size: 13px;
            font-weight: 600;
            user-select: none;
            margin-top: 12px;
            padding: 6px 0;
            transition: color 0.2s;
        }
        details summary:hover { color: #7dd3fc; }
        pre.code-box {
            background: #06090f;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 14px 16px;
            font-size: 12px;
            font-family: 'JetBrains Mono', monospace;
            color: #34d399;
            overflow-x: auto;
            margin-top: 10px;
            white-space: pre-wrap;
            line-height: 1.5;
        }

        #toast {
            position: fixed; bottom: 28px; right: 28px;
            background: #0284c7; color: white; padding: 13px 24px;
            border-radius: 10px; font-weight: 600; font-size: 13.5px;
            display: none; box-shadow: 0 12px 30px rgba(0,0,0,0.5), 0 0 1px 1px rgba(255,255,255,0.1);
            z-index: 9999;
            animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes slideIn {
            from { transform: translateY(15px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        @keyframes pulse {
            0% { opacity: 0.4; }
            50% { opacity: 1; }
            100% { opacity: 0.4; }
        }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #090d14; border-radius: 4px; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #334155; }
    </style>
</head>

<body>
    <header>
        <div class="header-title-box">
            <div class="logo-icon">⚡</div>
            <div>
                <h1>Gamblit Auto-Redeemer Pro</h1>
                <div style="font-size: 13px; color: #64748b; margin-top: 3px; font-weight: 500;">Ultra-Düşük Gecikmeli Kod Yakalayıcı & Otomatik hCaptcha Çözücü Havuzu</div>
            </div>
        </div>
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
            <span id="dc-badge" class="badge badge-purple">Discord: Bekleniyor</span>
            <span id="solver-badge" class="badge badge-purple">Çözücü: Manuel Mod</span>
            <span id="ws-badge" class="badge badge-offline">WebSocket: Bağlanıyor...</span>
        </div>
    </header>


    <div class="grid">
        <div class="card">
            <h2>👤 Gamblit Hesabı</h2>
            <div class="metric-val" id="acc-name">--</div>
            <div style="margin-top: 8px; font-size: 13px; color: #8b949e;">
                Bakiye: <strong style="color: #3fb950;" id="acc-balance">0</strong> DL &bull; 
                Level: <strong id="acc-level" style="color: var(--text-bright);">--</strong>
            </div>
        </div>
        <div class="card">
            <h2>⏱️ Performans & Hız</h2>
            <div class="metric-val" id="avg-lat">0 ms</div>
            <div style="margin-top: 8px; font-size: 13px; color: #8b949e;">
                Ortalama WebSocket Yanıt Gecikmesi
            </div>
        </div>
        <div class="card">
            <h2>📊 İşlem İstatistikleri</h2>
            <div style="display: flex; gap: 16px; margin-top: 4px;">
                <div>Toplam: <strong id="stat-total" class="metric-val" style="font-size: 20px;">0</strong></div>
                <div>Başarılı: <strong id="stat-success" class="metric-val" style="font-size: 20px; color: #3fb950;">0</strong></div>
                <div>Reddedilen: <strong id="stat-failed" class="metric-val" style="font-size: 20px; color: #f85149;">0</strong></div>
            </div>
        </div>
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <h2>💳 Çözücü Kredileri & Zamanlayıcı</h2>
                <button class="btn-alt" type="button" style="padding: 3px 8px; font-size: 11px;" onclick="refreshData()" title="Bakiyeleri Güncelle">🔄 Yenile</button>
            </div>
            <div style="font-size: 14px; margin-top: 4px;">
                NoneCap Kalan: <strong id="bal-nonecap" style="color: #38bdf8; font-family: 'JetBrains Mono', monospace; font-size: 15px;">1300 Kredi</strong>
            </div>
            <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">
                CapSolver: <strong id="bal-capsolver" style="color: #7ee787;">--</strong>
            </div>
            <div style="font-size: 12px; color: #8b949e; margin-top: 8px;">
                Havuz Döngüsü: <strong id="loop-status" style="color: #d29922;">Bekleniyor</strong>
            </div>
            <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">
                Çalışma Aralığı: <strong id="schedule-status" style="color: #58a6ff;">20:25 - 21:00</strong>
            </div>
        </div>


    </div>

    <div class="grid">
        <!-- Manual Redeem Box -->
        <div class="card">
            <h2>🎯 Manuel Kod Testi / Anında Redeem</h2>
            <form id="redeem-form">
                <div class="form-group">
                    <label>PROMO KODU</label>
                    <input type="text" id="manual-code" placeholder="Örn: HPIIVTKH veya LEVEL 5+ kodu" required autocomplete="off">
                </div>
                <div class="form-group">
                    <label>CAPTCHA TOKEN (İsteğe Bağlı / Boşsa Havuzdakini Kullanır)</label>
                    <input type="text" id="manual-captcha" placeholder="Boş bırakılırsa havuzdaki hazır token kullanılır">
                </div>
                <button type="submit" id="btn-redeem">🚀 Hemen Redeem Et</button>
            </form>
            <div id="redeem-output" style="margin-top: 14px; font-size: 12px; font-family: monospace; display: none; padding: 10px; border-radius: 4px; background: #0d1117;"></div>
        </div>

        <!-- Captcha Pool Status -->
        <div class="card">
            <h2>🛡️ hCaptcha Token Havuzu (0ms Yanıt İçin)</h2>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-size: 13px; color: #8b949e;">Durum: <strong id="captcha-status" style="color: #f85149;">Havuz Boş</strong></span>
                <span style="font-size: 12px; font-family: monospace;" id="captcha-timer-text">0 / 110 sn</span>
            </div>
            <div class="progress-bar-container">
                <div id="captcha-progress" class="progress-bar"></div>
            </div>

            <div class="form-group">
                <label>Manuel Token Ekle:</label>
                <input type="text" id="inject-token" placeholder="P0_eyJ... token yapıştır">
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button class="btn-alt" type="button" onclick="injectCaptcha()">📥 Havuzu Doldur</button>
                <button class="btn-accent" type="button" id="btn-auto-solve" onclick="triggerAutoSolve()">⚡ Hemen Çözdür</button>
            </div>

            <details style="margin-top: 14px;">
                <summary>💡 Tarayıcıdan 1-Tıkla Token Çekme Scripti (Ücretsiz)</summary>
                <p style="font-size: 12px; color: #8b949e; margin-top: 6px;">
                    1. <a href="https://gamblit.net" target="_blank" style="color: var(--accent);">gamblit.net</a> sayfasına git.<br>
                    2. Sağ üstteki profil menüsünden <strong>"Promo Code" / "Codes"</strong> modalını aç.<br>
                    3. <strong>F12</strong> tuşuna basıp <strong>Console</strong> sekmesine şu kodu yapıştırıp Enter'a bas:
                </p>
                <pre class="code-box" id="bridge-snippet">(() => { const send = (t) => { if (!t) return; fetch("http://localhost:5050/api/captcha", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({token: t}) }).then(() => console.log("%c[✔] TOKEN BOTA AKTARILDI! HAVUZ DOLDU!", "background: #00ff88; color: #000; font-weight: bold; font-size: 14px; padding: 4px;")).catch(e => console.error("Bot baglanti hatasi:", e)); }; for (let i = 0; i < 5; i++) { try { const ex = hcaptcha.getResponse(i); if (ex) { send(ex); return; } } catch(e) {} } for (let i = 0; i < 5; i++) { try { hcaptcha.execute(i, { async: true }).then(res => { const t = (typeof res === 'object' && res ? res.response : res) || hcaptcha.getResponse(i); send(t); }); break; } catch(e) {} } })();</pre>
                <button class="btn-alt" style="margin-top: 6px; font-size: 11px; padding: 6px 12px;" onclick="copySnippet()">📋 Kodu Kopyala</button>
            </details>
        </div>
    </div>

    <!-- Live Action Stream & Activity Console -->
    <div class="card" style="margin-bottom: 24px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <h2>⚡ Canlı İşlem Akışı (Anlık Bot & Kod Takibi)</h2>
            <span style="font-size: 12px; color: #3fb950; display: flex; align-items: center; gap: 6px;">
                <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #3fb950; animation: pulse 1.5s infinite;"></span>
                Canlı İzleniyor
            </span>
        </div>
        <p style="font-size: 12px; color: #8b949e; margin-bottom: 10px;">
            Discord'dan yakalanan mesajlar, seviye kodu ayıklama, hCaptcha havuzundan token çekme ve Gamblit'e otomatik fırlatma adımları anlık olarak buraya yansır:
        </p>
        <div id="live-console-box" style="
            background: #090d13;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 12px 14px;
            height: 220px;
            overflow-y: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            line-height: 1.6;
            color: #c9d1d9;
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.5);
        ">
            <div style="color: #8b949e;">[Sistem] Canlı akış terminali hazır. Olaylar bekleniyor...</div>
        </div>
    </div>

    <!-- Live Codes Table -->
    <div class="card" style="margin-bottom: 24px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <h2>📜 Son İşlenen Kodlar & Sonuçları</h2>
            <button class="btn-danger" type="button" style="padding: 5px 12px; font-size: 11px;" onclick="clearAllCodes()">🗑️ Listeyi & İstatistikleri Temizle</button>
        </div>
        <table>

            <thead>
                <tr>
                    <th>Kod</th>
                    <th>Durum</th>
                    <th>Mesaj / Sonuç</th>
                    <th>Zaman</th>
                    <th>Gecikme</th>
                </tr>
            </thead>
            <tbody id="codes-tbody">
                <tr><td colspan="5" style="text-align: center; color: #8b949e;">Henüz işlenen kod yok.</td></tr>
            </tbody>
        </table>
    </div>


    <!-- Multi-Account Manager Card -->
    <div class="card" style="margin-bottom: 24px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h2>👥 Gamblit Çoklu Hesap Havuzu (Multi-Account)</h2>
            <button class="btn-accent" type="button" style="padding: 6px 14px; font-size: 13px;" onclick="toggleAddAccountModal()">➕ Yeni Hesap Ekle</button>
        </div>
        <p style="font-size: 13px; color: #8b949e; margin-top: -6px; margin-bottom: 16px;">
            Discord'dan yakalanan her promo kodu havuzdaki tüm aktif hesaplarda <strong>aynı anda (paralel)</strong> redeem edilir!
        </p>

        <!-- Add Account Form -->
        <div id="add-account-box" style="display: none; background: #0d1117; padding: 16px; border-radius: 8px; border: 1px solid #30363d; margin-bottom: 16px;">
            <h3 style="font-size: 14px; margin-bottom: 12px; color: var(--accent);">Yeni Gamblit Hesabı Bağla</h3>
            <div class="grid" style="margin-bottom: 10px;">
                <div class="form-group" style="margin-bottom: 0;">
                    <label>HESAP ADI / ETİKETİ</label>
                    <input type="text" id="new-acc-name" placeholder="Örn: 2. Hesap - Yan Çar">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label>ÇEREZLER (Cookie Header veya JSON formatında)</label>
                    <input type="text" id="new-acc-cookies" placeholder='{"sid": "...", "_vid_t": "..."} veya Cookie metni'>
                </div>
            </div>
            <div style="display: flex; gap: 8px;">
                <button class="btn-accent" type="button" style="padding: 6px 14px; font-size: 12px;" onclick="submitNewAccount()">💾 Hesabı Ekle ve Bağla</button>
                <button class="btn-alt" type="button" style="padding: 6px 14px; font-size: 12px;" onclick="toggleAddAccountModal()">İptal</button>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Hesap Adı</th>
                    <th>Gamblit Kullanıcısı</th>
                    <th>Durum</th>
                    <th>Bakiye</th>
                    <th>Level</th>
                    <th>İşlem</th>
                </tr>
            </thead>
            <tbody id="accounts-tbody">
                <tr><td colspan="6" style="text-align: center; color: #8b949e;">Hesaplar yükleniyor...</td></tr>
            </tbody>
        </table>
    </div>

    <!-- Settings Box -->
    <div class="card">
        <h2>⚙️ Sistem Ayarları (.env)</h2>
        <form id="settings-form">
            <div class="grid" style="margin-bottom: 0;">
                <div class="form-group">
                    <label>DISCORD HESAP / BOT TOKENİ (User & Bot Destekli)</label>
                    <input type="password" id="cfg-token" placeholder="Discord hesap veya bot tokenini girin (MTUz...)">
                </div>
                <div class="form-group">
                    <label>DISCORD KANAL ID (#codes)</label>
                    <input type="text" id="cfg-channel" placeholder="Kanal ID">
                </div>
                <div class="form-group">
                    <label>DISCORD SUNUCU ID (Opsiyonel)</label>
                    <input type="text" id="cfg-guild" placeholder="Sunucu ID">
                </div>
            </div>

            <div class="grid" style="margin-bottom: 0;">
                <div class="form-group">
                    <label>NONECAP API KEY (1300 Bedava Kredi - Aktif)</label>
                    <input type="password" id="cfg-nonecap" placeholder="nc_live_...">
                </div>
                <div class="form-group">
                    <label>CAPSOLVER API KEY (Yedek Çözücü)</label>
                    <input type="password" id="cfg-capsolver" placeholder="CapSolver API anahtarın">
                </div>
            </div>
            <div class="grid" style="margin-bottom: 0;">
                <div class="form-group">
                    <label>ÇALIŞMA SAATİ BAŞLANGIÇ (Örn: 20:25)</label>
                    <input type="text" id="cfg-sched-start" placeholder="20:25">
                </div>
                <div class="form-group">
                    <label>ÇALIŞMA SAATİ BİTİŞ (Örn: 21:00)</label>
                    <input type="text" id="cfg-sched-end" placeholder="21:00">
                </div>
            </div>

            <div class="form-group">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <label style="margin-bottom: 0;">GAMBLIT ÇEREZLERİ (Cookie Header)</label>
                    <span style="font-size: 11px; color: var(--accent); cursor: pointer;" onclick="toggleAuthBridgeGuide()">⚡ 1-Tıkla Otomatik Aktarma (Kolay Yöntem)</span>
                </div>

                <!-- 1-Click Fast Sync Helper Box -->
                <div id="auth-bridge-guide" style="display: block; background: rgba(14, 21, 33, 0.85); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 12px; padding: 14px 16px; margin-bottom: 12px;">
                    <div style="font-size: 12.5px; font-weight: 700; color: var(--text-bright); display: flex; align-items: center; gap: 8px;">
                        <span>🚀</span> F12'de Çerez Aramaya Son! Oturumunu 1-Tıkla Bota Aktar:
                    </div>
                    
                    <div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">
                        <div style="font-size: 12px; color: var(--text);">
                            <strong>Yöntem A (Yer İşareti / Buton - En Kolayı):</strong> Aşağıdaki mavi butonu fareyle tutup tarayıcının <strong>Yer İşaretleri (Sık Kullanılanlar)</strong> çubuğuna sürükleyip bırak. Ardından <a href="https://gamblit.net" target="_blank" style="color: var(--accent); font-weight: 600;">gamblit.net</a> sayfasına girip bu yer işaretine tıkla! Oturumun anında bota bağlanır:
                        </div>
                        <div style="margin: 4px 0;">
                            <a id="auth-bookmarklet-link" href="#" style="
                                display: inline-flex;
                                align-items: center;
                                gap: 6px;
                                background: linear-gradient(135deg, #0284c7 0%, #6366f1 100%);
                                color: white;
                                padding: 6px 14px;
                                border-radius: 8px;
                                font-size: 12px;
                                font-weight: 700;
                                text-decoration: none;
                                cursor: grab;
                                box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3);
                            " title="Bu butonu tarayıcının Yer İşaretleri çubuğuna sürükle!">⭐ Gamblit Hesabı Bağla (Yer İşaretine Sürükle)</a>
                        </div>

                        <div style="font-size: 12px; color: var(--text); margin-top: 6px;">
                            <strong>Yöntem B (Tarayıcı Konsolu - 2 Saniye):</strong> <a href="https://gamblit.net" target="_blank" style="color: var(--accent); font-weight: 600;">gamblit.net</a> sayfasındayken <strong>F12</strong> tuşuna bas, <strong>Console</strong> sekmesine şu tek satırlık kodu yapıştırıp Enter'a bas:
                        </div>
                        <pre class="code-box" id="auth-bridge-snippet" style="margin-top: 4px; padding: 10px 12px; font-size: 11.5px;"></pre>
                        <div>
                            <button class="btn-alt" type="button" style="font-size: 11px; padding: 6px 12px;" onclick="copyAuthSnippet()">📋 Giriş Kodunu Kopyala</button>
                        </div>
                    </div>
                </div>

                <textarea id="cfg-cookies" rows="3" placeholder="_iidt=...; cf_clearance=...; sid=..."></textarea>
            </div>
            <button type="submit">💾 Ayarları Kaydet & Yenile</button>
        </form>
    </div>

    <div id="toast"></div>

    <script>
        function showToast(msg, isErr=false) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.style.background = isErr ? '#da3633' : '#238636';
            t.style.display = 'block';
            setTimeout(() => { t.style.display = 'none'; }, 3500);
        }

        async function refreshData() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                // WS Badge
                const b = document.getElementById('ws-badge');
                if (data.authenticated) {
                    b.className = 'badge badge-online';
                    b.innerText = 'WebSocket: BAĞLI (' + data.account.username + ')';
                } else {
                    b.className = 'badge badge-offline';
                    b.innerText = 'WebSocket: ÇEVRİMDIŞI';
                }

                // Discord Badge
                const dcb = document.getElementById('dc-badge');
                if (data.discord && data.discord.connected) {
                    dcb.className = 'badge badge-online';
                    dcb.innerText = 'Discord: ' + (data.discord.user || 'Bağlı') + ' (#' + data.discord.channel_id + ')';
                } else if (data.discord && data.discord.channel_id && data.discord.channel_id !== '0') {
                    dcb.className = 'badge badge-yellow';
                    dcb.innerText = 'Discord: Token Bekleniyor (#' + data.discord.channel_id + ')';
                } else {
                    dcb.className = 'badge badge-offline';
                    dcb.innerText = 'Discord: Çevrimdışı';
                }

                // Solver Badge & Balances & Schedule
                const sBadge = document.getElementById('solver-badge');
                sBadge.innerText = 'Çözücü: ' + data.captcha.active_solver;
                const hasProvider = data.captcha.active_solver.includes('NoneCap') || data.captcha.active_solver.includes('CapSolver') || data.captcha.active_solver.includes('2Captcha');
                const inSched = data.schedule ? data.schedule.in_schedule : true;
                const schedStr = (data.schedule ? `${data.schedule.start} - ${data.schedule.end}` : '20:25 - 21:00');
                
                const schedElem = document.getElementById('schedule-status');
                const countdownInfo = data.schedule && data.schedule.countdown ? data.schedule.countdown : null;
                const countdownText = countdownInfo ? ` • ⏳ ${countdownInfo.countdown_text}` : '';

                if (schedElem) {
                    const curTime = data.schedule && data.schedule.current_time ? ` [TR: ${data.schedule.current_time}]` : '';
                    schedElem.innerText = `${schedStr} (${inSched ? 'Şu An Aktif 🟢' : 'Şu An Uykuda ⏳'})${curTime}`;
                    schedElem.style.color = inSched ? '#3fb950' : '#8b949e';
                }

                if (hasProvider) {
                    sBadge.className = inSched ? 'badge badge-online' : 'badge badge-yellow';
                    if (inSched) {
                        document.getElementById('loop-status').innerText = `Aktif (Token Taze Tutuluyor)${countdownText}`;
                        document.getElementById('loop-status').style.color = '#3fb950';
                    } else {
                        document.getElementById('loop-status').innerText = `Uykuda (Kredi Harcanmıyor)${countdownText}`;
                        document.getElementById('loop-status').style.color = '#d29922';
                    }
                } else {
                    sBadge.className = 'badge badge-purple';
                    document.getElementById('loop-status').innerText = 'Pasif (API Anahtarı Yok)';
                    document.getElementById('loop-status').style.color = '#f85149';
                }

                const bal = data.captcha.balances || {};
                document.getElementById('bal-nonecap').innerText = bal.nonecap || 'Bağlı Değil';
                document.getElementById('bal-capsolver').innerText = bal.capsolver !== null ? '$' + bal.capsolver : 'Bağlı Değil';


                // Account
                document.getElementById('acc-name').innerText = data.account.username || 'Giriş Yapılmadı';
                const rawBal = parseFloat(data.account.balance_dl || 0);
                // Gamblit returns balance in WL (100 WL = 1 DL). Display as DL (e.g. 5.08 DL)
                const dlBal = (rawBal / 100.0).toFixed(2);
                document.getElementById('acc-balance').innerText = dlBal;
                document.getElementById('acc-level').innerText = data.account.level || '1';

                // Metrics
                document.getElementById('avg-lat').innerText = (data.metrics.avg_latency_ms || 0).toFixed(1) + ' ms';
                document.getElementById('stat-total').innerText = data.stats.total_codes || 0;
                document.getElementById('stat-success').innerText = data.stats.successful || 0;
                document.getElementById('stat-failed').innerText = data.stats.failed || 0;

                // Captcha Progress Bar
                const cStatus = document.getElementById('captcha-status');
                const pBar = document.getElementById('captcha-progress');
                const tText = document.getElementById('captcha-timer-text');
                const rem = Math.max(0, data.captcha.remaining || 0);

                if (data.captcha.valid && rem > 0) {
                    cStatus.innerText = 'HAZIR (' + Math.round(rem) + 's kaldı)';
                    cStatus.style.color = '#3fb950';
                    const pct = Math.min(100, Math.round((rem / 110.0) * 100));
                    pBar.style.width = pct + '%';
                    pBar.style.backgroundColor = rem < 20 ? '#d29922' : '#2ea043';
                    tText.innerText = Math.round(rem) + ' / 110 sn';
                } else if (data.captcha.is_solving) {
                    cStatus.innerText = 'Çözülüyor...';
                    cStatus.style.color = '#58a6ff';
                    pBar.style.width = '100%';
                    pBar.style.backgroundColor = '#1f6feb';
                    tText.innerText = 'İşleniyor';
                } else {
                    cStatus.innerText = 'Havuz Boş / Süresi Doldu';
                    cStatus.style.color = '#f85149';
                    pBar.style.width = '0%';
                    tText.innerText = '0 sn';
                }

                // Live Activity Console
                if (data.live_logs && data.live_logs.length > 0) {
                    const cBox = document.getElementById('live-console-box');
                    let logHtml = '';
                    for (const l of data.live_logs) {
                        let color = '#c9d1d9';
                        if (l.level === 'WARNING') color = '#d29922';
                        else if (l.level === 'ERROR') color = '#f85149';
                        else if (l.message.includes('[KOD YAKALANDI]') || l.message.includes('SUCCESS') || l.message.includes('✔')) color = '#3fb950';
                        else if (l.message.includes('hCaptcha') || l.message.includes('token') || l.message.includes('TOKEN')) color = '#58a6ff';
                        else if (l.message.includes('Redeem') || l.message.includes('Kod')) color = '#e3b341';
                        
                        logHtml += `<div><span style="color:#6e7681;">[${l.time}]</span> <span style="color:${color};">${l.message}</span></div>`;
                    }
                    const isScrolledToBottom = cBox.scrollHeight - cBox.clientHeight <= cBox.scrollTop + 30;
                    cBox.innerHTML = logHtml;
                    if (isScrolledToBottom) {
                        cBox.scrollTop = cBox.scrollHeight;
                    }
                }

                // Table
                if (data.recent_codes && data.recent_codes.length > 0) {
                    let html = '';
                    for (const c of data.recent_codes) {
                        const isOk = c.status === 'SUCCESS';
                        const badgeCls = isOk ? 'badge-online' : 'badge-offline';
                        html += `<tr>
                            <td class="code-cell">${c.code}</td>
                            <td><span class="badge ${badgeCls}">${c.status}</span></td>
                            <td style="color: #8b949e; font-size: 12px;">${c.message || '--'}</td>
                            <td>${new Date((c.processed_at||c.received_at)*1000).toLocaleTimeString()}</td>
                            <td>${(c.latency_ms||0).toFixed(1)} ms</td>
                        </tr>`;
                    }
                    document.getElementById('codes-tbody').innerHTML = html;
                }


                // Accounts Table
                if (data.accounts && data.accounts.accounts) {
                    let accHtml = '';
                    if (data.accounts.accounts.length === 0) {
                        accHtml = '<tr><td colspan="6" style="text-align: center; color: #8b949e;">Henüz kayıtlı ek hesap yok.</td></tr>';
                    } else {
                        for (const a of data.accounts.accounts) {
                            const statusBadge = a.is_authenticated 
                                ? '<span class="status-badge status-connected">● BAĞLI</span>'
                                : (a.is_connected ? '<span class="status-badge" style="background:#1f6feb22; color:#58a6ff;">● BAĞLANIYOR</span>' : '<span class="status-badge status-disconnected">○ ÇEVRİMDIŞI</span>');
                            const toggleBtn = a.enabled
                                ? `<button class="btn-alt" type="button" style="padding: 4px 8px; font-size: 11px;" onclick="toggleAccount('${a.id}')">Durdur</button>`
                                : `<button class="btn-accent" type="button" style="padding: 4px 8px; font-size: 11px;" onclick="toggleAccount('${a.id}')">Aktif Et</button>`;
                            const rawAccBal = parseFloat(a.balance_dl || 0);
                            const dlAccBal = (rawAccBal / 100.0).toFixed(2);
                            accHtml += `<tr>
                                <td><strong>${a.name}</strong></td>
                                <td style="font-family: monospace;">${a.username || '--'}</td>
                                <td>${statusBadge}</td>
                                <td><strong style="color: #3fb950;">${dlAccBal}</strong> DL <span style="font-size: 10px; color: #64748b;">(${Math.round(rawAccBal)} WL)</span></td>
                                <td>Level ${a.level || 1}</td>
                                <td style="display: flex; gap: 6px;">
                                    <button class="btn-alt" type="button" style="padding: 4px 8px; font-size: 11px; color: #58a6ff;" onclick="testAccount('${a.id}')">🔄 Test Et</button>
                                    ${toggleBtn}
                                    <button class="btn-alt" type="button" style="padding: 4px 8px; font-size: 11px; color: #f85149;" onclick="removeAccount('${a.id}')">🗑️ Sil</button>
                                </td>
                            </tr>`;
                        }
                    }
                    document.getElementById('accounts-tbody').innerHTML = accHtml;
                }
            } catch(e) {
                console.error("refreshData error:", e);
            }
        }

        async function loadConfig() {
            try {
                const res = await fetch('/api/config');
                const data = await res.json();
                document.getElementById('cfg-token').value = data.discord_token || '';
                document.getElementById('cfg-channel').value = data.discord_channel_id || '';
                document.getElementById('cfg-guild').value = data.discord_guild_id || '';
                document.getElementById('cfg-nonecap').value = data.nonecap_api_key || '';
                document.getElementById('cfg-capsolver').value = data.capsolver_api_key || '';
                document.getElementById('cfg-cookies').value = data.raw_cookies || '';
                document.getElementById('cfg-sched-start').value = data.schedule_start || '20:25';
                document.getElementById('cfg-sched-end').value = data.schedule_end || '21:00';
            } catch(e) {
                console.error("loadConfig error:", e);
            }
        }

        document.getElementById('settings-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const body = {
                discord_token: document.getElementById('cfg-token').value,
                discord_channel_id: document.getElementById('cfg-channel').value,
                discord_guild_id: document.getElementById('cfg-guild').value,
                nonecap_api_key: document.getElementById('cfg-nonecap').value,
                capsolver_api_key: document.getElementById('cfg-capsolver').value,
                raw_cookies: document.getElementById('cfg-cookies').value,
                schedule_enabled: true,
                schedule_start: document.getElementById('cfg-sched-start').value.trim() || '20:25',
                schedule_end: document.getElementById('cfg-sched-end').value.trim() || '21:00'
            };
            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body)
                });
                if (res.ok) {
                    showToast('✅ Ayarlar başarıyla kaydedildi!');
                    refreshData();
                } else {
                    showToast('❌ Ayarlar kaydedilemedi!', true);
                }
            } catch(e) {}
        });


        async function triggerAutoSolve() {
            const btn = document.getElementById('btn-auto-solve');
            btn.disabled = true;
            btn.innerText = '⏳ Çözülüyor...';
            showToast('⚡ Captcha çözülüyor, lütfen bekleyin...');
            try {
                const res = await fetch('/api/captcha/solve', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'ready') {
                    showToast('🎉 Captcha başarıyla çözüldü ve havuza eklendi!');
                } else {
                    showToast('❌ ' + (data.error || 'Çözüm başarısız'), true);
                }
            } catch(e) {
                showToast('❌ İstek hatası: ' + e, true);
            } finally {
                btn.disabled = false;
                btn.innerText = '⚡ Hemen Çözdür';
                refreshData();
            }
        }

        document.getElementById('redeem-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('btn-redeem');
            const out = document.getElementById('redeem-output');
            btn.disabled = true;
            btn.innerText = 'Redeem ediliyor...';
            out.style.display = 'block';
            out.innerText = 'İstek gönderiliyor...';

            const code = document.getElementById('manual-code').value.trim();
            const captcha = document.getElementById('manual-captcha').value.trim();

            try {
                const res = await fetch('/api/redeem', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({code, captcha})
                });
                const data = await res.json();
                out.innerText = JSON.stringify(data, null, 2);
                if (data.status === 'SUCCESS') {
                    showToast('🎉 KOD BAŞARIYLA REDEEM EDİLDİ!');
                } else {
                    showToast('Cevap: ' + (data.message || data.status), true);
                }
            } catch(err) {
                out.innerText = 'Hata: ' + err;
            } finally {
                btn.disabled = false;
                btn.innerText = '🚀 Hemen Redeem Et';
                refreshData();
            }
        });

        async function injectCaptcha() {
            const token = document.getElementById('inject-token').value.trim();
            if (!token) return;
            const res = await fetch('/api/captcha', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({token})
            });
            if (res.ok) {
                showToast('✅ hCaptcha tokenı havuzuna eklendi (100 sn aktif)!');
                document.getElementById('inject-token').value = '';
                refreshData();
            }
        }

        function toggleAuthBridgeGuide() {
            const guide = document.getElementById('auth-bridge-guide');
            guide.style.display = guide.style.display === 'none' ? 'block' : 'none';
        }

        function updateAuthBridgeSnippet() {
            const host = window.location.origin;
            const scriptBody = `(() => { const c = document.cookie; if (!c) { alert('Hata: Gamblit oturum çerezi bulunamadı! Giriş yaptığından emin ol.'); return; } fetch("${host}/api/auth/import", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({cookies: c}) }).then(r => r.json()).then(d => { if (d.status === 'ok') { alert('✅ TEBRİKLER! Gamblit hesabı (' + (d.username || 'Aktif') + ') bota bağlandı!'); console.log('%c[✔] GAMBLIT OTURUMU BOTA AKTARILDI!', 'background:#00ff88; color:#000; font-weight:bold; font-size:14px; padding:4px;'); } else { alert('Hata: ' + (d.error || 'Aktarılamadı')); } }).catch(e => alert('Bot paneline ulaşılamadı: ' + e)); })();`;
            
            const el = document.getElementById('auth-bridge-snippet');
            if (el) el.innerText = scriptBody;

            const bm = document.getElementById('auth-bookmarklet-link');
            if (bm) {
                bm.href = "javascript:" + encodeURIComponent(scriptBody);
            }
        }

        function copyAuthSnippet() {
            updateAuthBridgeSnippet();
            const text = document.getElementById('auth-bridge-snippet').innerText;
            navigator.clipboard.writeText(text).then(() => {
                showToast("📋 Gamblit giriş kodu kopyalandı! F12 Console sekmesine yapıştırıp Enter'a bas.");
            }).catch(() => {
                showToast("Kopyalama başarısız", true);
            });
        }

        function updateBridgeSnippet() {
            const host = window.location.origin;
            const snippet = `(() => { const send = (t) => { if (!t) return; fetch("${host}/api/captcha", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({token: t}) }).then(() => console.log("%c[✔] TOKEN BOTA AKTARILDI! HAVUZ DOLDU!", "background: #00ff88; color: #000; font-weight: bold; font-size: 14px; padding: 4px;")).catch(e => console.error("Bot baglanti hatasi:", e)); }; for (let i = 0; i < 5; i++) { try { const ex = hcaptcha.getResponse(i); if (ex) { send(ex); return; } } catch(e) {} } for (let i = 0; i < 5; i++) { try { hcaptcha.execute(i, { async: true }).then(res => { const t = (typeof res === 'object' && res ? res.response : res) || hcaptcha.getResponse(i); send(t); }); break; } catch(e) {} } })();`;
            const el = document.getElementById('bridge-snippet');
            if (el) el.innerText = snippet;
        }

        function copySnippet() {
            updateBridgeSnippet();
            const text = document.getElementById('bridge-snippet').innerText;
            navigator.clipboard.writeText(text).then(() => {
                showToast('📋 Konsol kodu panoya kopyalandı!');
            }).catch(() => {
                showToast('Kopyalama başarısız', true);
            });
        }

        function toggleAddAccountModal() {
            const box = document.getElementById('add-account-box');
            box.style.display = box.style.display === 'none' ? 'block' : 'none';
        }

        async function submitNewAccount() {
            const name = document.getElementById('new-acc-name').value.trim();
            const cookies = document.getElementById('new-acc-cookies').value.trim();
            if (!cookies) {
                showToast('Lütfen hesap çerezlerini girin!', true);
                return;
            }
            try {
                const res = await fetch('/api/accounts', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name, cookies})
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || '✅ Yeni hesap başarıyla eklendi ve bağlandı!');
                    document.getElementById('new-acc-name').value = '';
                    document.getElementById('new-acc-cookies').value = '';
                    toggleAddAccountModal();
                    refreshData();
                } else {
                    showToast('Hata: ' + (data.error || 'Eklenemedi'), true);
                }
            } catch(e) {
                showToast('İstek hatası: ' + e, true);
            }
        }

        async function removeAccount(accId) {
            if (!confirm('Bu hesabı listeden silmek istediğine emin misin?')) return;
            try {
                const res = await fetch('/api/accounts/' + accId, { method: 'DELETE' });
                if (res.ok) {
                    showToast('Hesap silindi.');
                    refreshData();
                }
            } catch(e) {}
        }

        async function toggleAccount(accId) {
            try {
                const res = await fetch('/api/accounts/' + accId + '/toggle', { method: 'POST' });
                if (res.ok) {
                    refreshData();
                }
            } catch(e) {}
        }

        async function testAccount(accId) {
            showToast('🔄 Hesap bağlantısı test ediliyor...');
            try {
                const res = await fetch('/api/accounts/' + accId + '/test', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    showToast(data.message || '✅ Bağlantı BAŞARILI!');
                } else {
                    showToast(data.message || '❌ Bağlantı kurulamadı!', true);
                }
                refreshData();
            } catch(e) {
                showToast('Hata: ' + e, true);
            }
        }

        async function clearAllCodes() {
            if (!confirm('Tüm geçmiş kodları ve hata istatistiklerini sıfırlamak istiyor musunuz?')) return;
            try {
                const res = await fetch('/api/codes/clear', { method: 'POST' });
                if (res.ok) {
                    showToast('🧹 Kod listesi ve istatistikler sıfırlandı!');
                    document.getElementById('codes-tbody').innerHTML = '<tr><td colspan="5" style="text-align: center; color: #8b949e;">Henüz işlenen kod yok.</td></tr>';
                    refreshData();
                } else {
                    showToast('Temizleme başarısız', true);
                }
            } catch(e) {
                showToast('Hata: ' + e, true);
            }
        }


        updateBridgeSnippet();
        updateAuthBridgeSnippet();
        refreshData();
        loadConfig();
        setInterval(refreshData, 3000);
    </script>
</body>
</html>
"""


class WebPanel:
    def __init__(
        self,
        config: Config,
        client: GamblitClient,
        db: Database,
        metrics: MetricsTracker,
        queue: RedeemQueue,
        captcha_pool: CaptchaPool,
        gateway_listener: Optional[Any] = None,
        account_manager: Optional[Any] = None,
        port: int = 5050,
    ):
        self.config = config
        self.client = client
        self.db = db
        self.metrics = metrics
        self.queue = queue
        self.captcha_pool = captcha_pool
        self.gateway_listener = gateway_listener
        self.account_manager = account_manager
        self.port = port
        # Add CORS middleware so console snippets on gamblit.net can inject tokens directly
        @web.middleware
        async def cors_middleware(request, handler):
            if request.method == "OPTIONS":
                resp = web.Response(status=200)
            else:
                try:
                    resp = await handler(request)
                except web.HTTPException as ex:
                    resp = ex
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return resp

        self.app = web.Application(middlewares=[cors_middleware])
        self.runner = None
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/config", self.handle_get_config)
        self.app.router.add_post("/api/config", self.handle_save_config)
        self.app.router.add_post("/api/redeem", self.handle_manual_redeem)
        self.app.router.add_post("/api/captcha", self.handle_inject_captcha)
        self.app.router.add_options("/api/captcha", self.handle_cors_preflight)
        self.app.router.add_post("/api/auth/import", self.handle_import_auth)
        self.app.router.add_options("/api/auth/import", self.handle_cors_preflight)
        self.app.router.add_post("/api/captcha/solve", self.handle_solve_now)
        self.app.router.add_get("/api/accounts", self.handle_get_accounts)
        self.app.router.add_post("/api/accounts", self.handle_add_account)
        self.app.router.add_delete("/api/accounts/{id}", self.handle_remove_account)
        self.app.router.add_post("/api/accounts/{id}/toggle", self.handle_toggle_account)
        self.app.router.add_post("/api/accounts/{id}/test", self.handle_test_account)
        self.app.router.add_post("/api/codes/clear", self.handle_clear_codes)

    async def handle_import_auth(self, request: web.Request) -> web.Response:
        """1-Click import cookies directly from browser bookmarklet or console snippet."""
        try:
            data = await request.json()
            raw_cookies = str(data.get("cookies", "")).strip()
            if not raw_cookies:
                return web.json_response({"status": "error", "error": "Çerez boş geldi."}, status=400)

            # Update configuration
            self.config.raw_cookies = raw_cookies
            self.config._parsed_cookies = None  # force reparse

            # Re-write .env file preserving other settings
            try:
                env_path = Path(".env")
                if env_path.exists():
                    lines = env_path.read_text(encoding="utf-8").splitlines()
                    new_lines = []
                    found = False
                    for line in lines:
                        if line.startswith("GAMBLIT_COOKIES="):
                            new_lines.append(f"GAMBLIT_COOKIES={raw_cookies}")
                            found = True
                        else:
                            new_lines.append(line)
                    if not found:
                        new_lines.append(f"GAMBLIT_COOKIES={raw_cookies}")
                    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            except Exception as e:
                pass

            # Re-authenticate Gamblit client immediately
            if self.client._connected:
                await self.client.close()
            
            connected = await self.client.connect_ws()
            profile = await self.client.get_profile()

            username = profile.username if profile.is_authenticated else "Bağlanıyor"
            return web.json_response({
                "status": "ok",
                "authenticated": profile.is_authenticated,
                "username": username,
                "balance_dl": profile.balance_dl,
            })
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)}, status=500)

    async def handle_clear_codes(self, request: web.Request) -> web.Response:
        try:
            async with self.db._connection.cursor() as cursor:
                await cursor.execute("DELETE FROM codes")
                await cursor.execute("DELETE FROM events")
                await self.db._connection.commit()
            if self.metrics:
                self.metrics.reset()
            return web.json_response({"status": "cleared"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)


    async def handle_get_accounts(self, request: web.Request) -> web.Response:
        if self.account_manager:
            return web.json_response(self.account_manager.get_summary())
        return web.json_response({"total_accounts": 0, "connected_accounts": 0, "total_dl": 0, "accounts": []})

    async def handle_add_account(self, request: web.Request) -> web.Response:
        if not self.account_manager:
            return web.json_response({"error": "Account manager not available"}, status=500)
        data = await request.json()
        name = str(data.get("name", "")).strip()
        cookies = str(data.get("cookies", "")).strip()
        if not cookies:
            return web.json_response({"error": "Çerezler zorunludur"}, status=400)

        acc = await self.account_manager.add_account(name=name, cookies=cookies)
        
        # Test connection immediately
        is_connected = await acc.client.connect_ws()
        profile = acc.client._profile

        if profile and profile.is_authenticated:
            return web.json_response({
                "status": "added",
                "message": f"✅ Hesap başarıyla doğrulandı: {profile.username} (Level {profile.level})",
                "account": acc.to_dict()
            })
        else:
            return web.json_response({
                "status": "added_pending",
                "message": "⚠️ Hesap eklendi fakat henüz doğrulanmadı. Çerezlerin geçerli olduğunu veya GEO onayını kontrol edin.",
                "account": acc.to_dict()
            })

    async def handle_remove_account(self, request: web.Request) -> web.Response:
        if not self.account_manager:
            return web.json_response({"error": "Account manager not available"}, status=500)
        acc_id = request.match_info.get("id")
        ok = await self.account_manager.remove_account(acc_id)
        return web.json_response({"status": "deleted" if ok else "not_found"})

    async def handle_toggle_account(self, request: web.Request) -> web.Response:
        if not self.account_manager:
            return web.json_response({"error": "Account manager not available"}, status=500)
        acc_id = request.match_info.get("id")
        ok = await self.account_manager.toggle_account(acc_id)
        return web.json_response({"status": "toggled" if ok else "not_found"})

    async def handle_test_account(self, request: web.Request) -> web.Response:
        if not self.account_manager:
            return web.json_response({"error": "Account manager not available"}, status=500)
        acc_id = request.match_info.get("id")
        acc = self.account_manager.accounts.get(acc_id)
        if not acc:
            return web.json_response({"error": "Hesap bulunamadı"}, status=404)
        
        # Test connection
        if acc.client._connected:
            await acc.client.close()
        await acc.client.connect_ws()
        profile = acc.client._profile
        if profile and profile.is_authenticated:
            return web.json_response({
                "status": "success",
                "message": f"✅ Bağlantı BAŞARILI: {profile.username} (Level {profile.level}, {profile.balance_dl} DL)",
                "account": acc.to_dict()
            })
        return web.json_response({
            "status": "failed",
            "message": "❌ Bağlantı kurulamadı. Çerezler geçersiz olabilir veya onay bekliyor.",
            "account": acc.to_dict()
        })

    async def handle_cors_preflight(self, request: web.Request) -> web.Response:
        return web.Response(status=200)

    async def handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=HTML_TEMPLATE, content_type="text/html")

    async def handle_status(self, request: web.Request) -> web.Response:
        profile = await self.client.get_profile()
        stats = await self.db.get_stats()
        balances = await self.captcha_pool.get_balances()

        recent = []
        try:
            async with self.db._connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT code, status, latency_ms, processed_at, received_at, response FROM codes ORDER BY id DESC LIMIT 15"
                )
                rows = await cursor.fetchall()
                for r in rows:
                    item = dict(r)
                    msg = ""
                    if item.get("response"):
                        try:
                            parsed_resp = json.loads(item["response"])
                            msg = parsed_resp.get("message") or parsed_resp.get("error") or str(parsed_resp)
                        except Exception:
                            msg = str(item["response"])
                    item["message"] = msg
                    recent.append(item)
        except Exception:
            pass

        active_solver = "Manuel Mod"
        if self.captcha_pool.nonecap_api_key:
            active_solver = "NoneCap (1300 Bedava Kredi)"
        elif self.captcha_pool.capsolver_api_key:
            active_solver = "CapSolver (Otomatik)"
        elif self.captcha_pool.twocaptcha_api_key:
            active_solver = "2Captcha (Otomatik)"

        discord_info = {
            "connected": self.gateway_listener.is_connected if self.gateway_listener else False,
            "user": self.gateway_listener.username if self.gateway_listener else "",
            "channel_id": str(self.config.discord_channel_id),
        }

        live_logs = get_recent_logs(limit=40)
        in_sched = self.config.is_in_schedule()

        return web.json_response({
            "authenticated": profile.is_authenticated,
            "account": {
                "username": profile.username,
                "balance_dl": profile.balance_dl,
                "level": profile.level,
            },
            "metrics": self.metrics.summary(),
            "stats": stats,
            "captcha": {
                "valid": self.captcha_pool.is_token_valid,
                "remaining": self.captcha_pool.remaining_seconds,
                "active_solver": active_solver,
                "is_solving": self.captcha_pool.is_solving,
                "last_error": self.captcha_pool.last_error,
                "balances": balances,
            },
            "schedule": {
                "enabled": self.config.schedule_enabled,
                "start": self.config.schedule_start,
                "end": self.config.schedule_end,
                "in_schedule": in_sched,
                "current_time": self.config.get_tr_now().strftime("%H:%M:%S"),
                "countdown": self.config.get_schedule_countdown(),
            },
            "discord": discord_info,
            "recent_codes": recent,
            "live_logs": live_logs,
            "accounts": self.account_manager.get_summary() if self.account_manager else None,
        })


    async def handle_get_config(self, request: web.Request) -> web.Response:
        return web.json_response({
            "discord_token": self.config.discord_token,
            "discord_channel_id": str(self.config.discord_channel_id),
            "discord_guild_id": str(self.config.discord_guild_id),
            "nonecap_api_key": self.config.nonecap_api_key,
            "capsolver_api_key": self.config.capsolver_api_key,
            "raw_cookies": self.config.raw_cookies,
            "schedule_enabled": self.config.schedule_enabled,
            "schedule_start": self.config.schedule_start,
            "schedule_end": self.config.schedule_end,
        })

    async def handle_save_config(self, request: web.Request) -> web.Response:
        data = await request.json()
        token = data.get("discord_token", "").strip()
        channel_id = data.get("discord_channel_id", "0").strip()
        guild_id = data.get("discord_guild_id", "0").strip()
        nonecap_key = data.get("nonecap_api_key", "").strip()
        capsolver_key = data.get("capsolver_api_key", "").strip()
        raw_cookies = data.get("raw_cookies", "").strip()
        sched_enabled = bool(data.get("schedule_enabled", True))
        sched_start = data.get("schedule_start", "20:25").strip()
        sched_end = data.get("schedule_end", "21:00").strip()


        # Update in-memory config
        self.config.discord_token = token
        self.config.discord_channel_id = int(channel_id or 0)
        self.config.discord_guild_id = int(guild_id or 0)
        self.config.nonecap_api_key = nonecap_key
        self.config.capsolver_api_key = capsolver_key
        self.config.raw_cookies = raw_cookies
        self.config.schedule_enabled = sched_enabled
        self.config.schedule_start = sched_start
        self.config.schedule_end = sched_end

        # Update captcha pool keys
        self.captcha_pool.nonecap_api_key = nonecap_key
        self.captcha_pool.capsolver_api_key = capsolver_key

        # Save to .env
        env_content = f"""# Gamblit Promo Code Auto-Redeemer Configuration
DISCORD_TOKEN={token}
DISCORD_GUILD_ID={guild_id or 0}
DISCORD_CHANNEL_ID={channel_id or 0}

GAMBLIT_BASE_URL={self.config.gamblit_base_url}
GAMBLIT_COOKIES={raw_cookies}
GAMBLIT_USER_AGENT={self.config.gamblit_user_agent}

NONECAP_API_KEY={nonecap_key}
CAPSOLVER_API_KEY={capsolver_key}

SCHEDULE_ENABLED={"true" if sched_enabled else "false"}
SCHEDULE_START={sched_start}
SCHEDULE_END={sched_end}

REDEEM_ENDPOINTS={",".join(self.config.redeem_endpoints)}
CONNECT_TIMEOUT_SEC={self.config.connect_timeout_sec}
READ_TIMEOUT_SEC={self.config.read_timeout_sec}
MAX_RETRIES={self.config.max_retries}
RATE_LIMIT_BACKOFF_FACTOR={self.config.rate_limit_backoff_factor}

DATABASE_PATH={self.config.database_path}
LOG_LEVEL={self.config.log_level}
LOG_FILE={self.config.log_file}
"""
        with open(".env", "w", encoding="utf-8") as f:
            f.write(env_content)


        # Trigger auto solver loop if keys provided
        if nonecap_key or capsolver_key:
            await self.captcha_pool.start_auto_solver_loop()

        # Reconnect gateway listener if token/channel configured
        if self.gateway_listener:
            await self.gateway_listener.stop()
            if token:
                await self.gateway_listener.start()

        # Reconnect WS if cookies changed
        if self.client._connected:
            await self.client.close()
        asyncio.create_task(self.client.connect_ws())

        return web.json_response({"status": "saved"})

    async def handle_solve_now(self, request: web.Request) -> web.Response:
        token = await self.captcha_pool.auto_solve_once()
        if token:
            return web.json_response({"status": "ready", "token": token[:20] + "..."})
        err_msg = self.captcha_pool.last_error or "Çözüm başarısız veya API anahtarı geçersiz."
        return web.json_response({"status": "failed", "error": err_msg}, status=400)

    async def handle_manual_redeem(self, request: web.Request) -> web.Response:
        data = await request.json()
        code = str(data.get("code", "")).strip().upper()
        captcha_override = str(data.get("captcha", "")).strip()

        token = captcha_override or await self.captcha_pool.get_token()

        latency = RedeemLatency(t0_discord_received=time.time())
        result = await self.client.redeem_code(code, latency=latency, captcha_token=token)

        # Invalidate used token so it's not reused
        if not captcha_override and token:
            self.captcha_pool.invalidate()

        await self.db.update_redeem_result(result)
        self.metrics.record_redeem(result)

        return web.json_response({
            "code": result.code,
            "status": result.status.value,
            "message": result.message,
            "latency_ms": result.latency.http_request_ms,
            "response_data": result.response_data,
        })

    async def handle_inject_captcha(self, request: web.Request) -> web.Response:
        data = await request.json()
        token = str(data.get("token", "")).strip()
        if token:
            self.captcha_pool.set_token(token)
            return web.json_response({"status": "injected"})
        return web.json_response({"error": "Empty token"}, status=400)

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        target_port = self.port
        for p in range(target_port, target_port + 5):
            try:
                site = web.TCPSite(self.runner, "0.0.0.0", p)
                await site.start()
                self.port = p
                print(f"\n🌐 Web Kontrol Paneli Yayında: http://localhost:{self.port}\n")
                return
            except OSError as e:
                # WinError 10048 (Windows) or 98 (Linux): Port already in use
                if getattr(e, "winerror", None) == 10048 or getattr(e, "errno", None) in (10048, 98):
                    continue
                raise
        raise OSError(f"Port 5050-5055 arası tüm portlar meşgul!")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
