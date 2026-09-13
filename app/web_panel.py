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
from app.models import ParsedCode, RedeemLatency, RedeemStatus, RedeemResult
from app.parser import CodeParser
from app.logging_config import get_recent_logs, get_all_logs

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
            <a href="/yardim" style="color: #c084fc; text-decoration: none; font-size: 13px; font-weight: 700; padding: 6px 12px; border-radius: 8px; background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3);">📚 Yardım Rehberi (/yardım)</a>
            <a href="/test" style="color: #c084fc; text-decoration: none; font-size: 13px; font-weight: 700; padding: 6px 12px; border-radius: 8px; background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3);">🧪 Test Et (/test)</a>
            <a href="/durum" style="color: #38bdf8; text-decoration: none; font-size: 13px; font-weight: 700; padding: 6px 12px; border-radius: 8px; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3);">📊 Canlı Durum (/durum)</a>
            <a href="/logs" style="color: #34d399; text-decoration: none; font-size: 13px; font-weight: 700; padding: 6px 12px; border-radius: 8px; background: rgba(52, 211, 153, 0.1); border: 1px solid rgba(52, 211, 153, 0.3);">📜 Loglar (/logs)</a>
            <a href="/captcha" style="color: #fbbf24; text-decoration: none; font-size: 13px; font-weight: 700; padding: 6px 12px; border-radius: 8px; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3);">🛡️ Captcha & API (/captcha)</a>
            <a href="/cc" style="color: #ec4899; text-decoration: none; font-size: 13px; font-weight: 700; padding: 6px 12px; border-radius: 8px; background: rgba(236, 72, 153, 0.1); border: 1px solid rgba(236, 72, 153, 0.3);">🍪 Çerez Ayrıştırıcı (/cc)</a>
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
                Ortalama WebSocket Yanıt Gecikmesi <span style="font-size: 11px; color: #38bdf8;">(10 dk'da bir güncellenir • 0 Kredi)</span>
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
                NoneCap (Ana): <strong id="bal-nonecap" style="color: #38bdf8; font-family: 'JetBrains Mono', monospace; font-size: 14px;">1300 Kredi</strong>
            </div>
            <div style="font-size: 13px; margin-top: 4px;">
                NoneCap (Yedek): <strong id="bal-nonecap-backup" style="color: #a78bfa; font-family: 'JetBrains Mono', monospace; font-size: 13px;">--</strong>
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
                <button class="btn-alt" type="button" onclick="injectCaptcha()">📥 Manuel Ekle</button>
                <button class="btn-accent" type="button" id="btn-auto-solve" onclick="triggerAutoSolve()">⚡ 1 Çözüm Yap</button>
                <button class="btn-accent" style="background: #059669; border-color: #10b981;" type="button" id="btn-warmup" onclick="triggerWarmup(7)">🚀 Turbo Doldur (7 Token)</button>
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
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <h2>👥 Gamblit Çoklu Hesap Havuzu (Multi-Account)</h2>
            <div style="display: flex; gap: 8px;">
                <button class="btn-alt" type="button" style="padding: 6px 14px; font-size: 13px;" onclick="verifyAllAccounts()">🔄 Tümünü Doğrula & Tazele</button>
                <button class="btn-accent" type="button" style="padding: 6px 14px; font-size: 13px;" onclick="toggleAddAccountModal()">➕ Yeni Hesap Ekle</button>
            </div>
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
                    <label>NONECAP API KEY (Ana Çözücü)</label>
                    <input type="password" id="cfg-nonecap" placeholder="nc_live_...">
                </div>
                <div class="form-group">
                    <label>NONECAP YEDEK KEY (Ana Bitince Devreye Girer)</label>
                    <input type="password" id="cfg-nonecap-backup" placeholder="nc_live_...">
                </div>
            </div>
            <div class="grid" style="margin-bottom: 0;">
                <div class="form-group">
                    <label>CAPSOLVER API KEY (Yedek Çözücü)</label>
                    <input type="password" id="cfg-capsolver" placeholder="CapSolver API anahtarın">
                </div>
                <div class="form-group">
                    <label>ÇALIŞMA SAATİ BAŞLANGIÇ (Örn: 20:25)</label>
                    <input type="text" id="cfg-sched-start" placeholder="20:25">
                </div>
                <div class="form-group">
                    <label>ÇALIŞMA SAATİ BİTİŞ (Örn: 21:00)</label>
                    <input type="text" id="cfg-sched-end" placeholder="21:00">
                </div>
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
                const balBakElem = document.getElementById('bal-nonecap-backup');
                if (balBakElem) {
                    balBakElem.innerText = bal.nonecap_backup || 'Yedek Tanımsız';
                }
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
                const tokenCount = data.captcha.valid_count || 0;
                const targetCount = data.captcha.target_pool_size || 1;

                const btnWarmup = document.getElementById('btn-warmup');
                if (btnWarmup && !btnWarmup.disabled) {
                    btnWarmup.innerText = `🚀 Turbo Doldur (${targetCount} Hesap / ${targetCount} Token)`;
                }

                if (data.captcha.valid && rem > 0) {
                    cStatus.innerText = `HAZIR (${tokenCount} Token - ${Math.round(rem)}s kaldı)`;
                    cStatus.style.color = '#3fb950';
                    const pct = Math.min(100, Math.round((rem / 110.0) * 100));
                    pBar.style.width = pct + '%';
                    pBar.style.backgroundColor = rem < 20 ? '#d29922' : '#2ea043';
                    tText.innerText = `${tokenCount} Token / ${Math.round(rem)} sn`;
                } else if (data.captcha.is_solving) {
                    cStatus.innerText = 'Çözülüyor...';
                    cStatus.style.color = '#58a6ff';
                    pBar.style.width = '100%';
                    pBar.style.backgroundColor = '#1f6feb';
                    tText.innerText = 'İşleniyor';
                } else {
                    cStatus.innerText = `Havuz Boş (Hedef: ${targetCount} Token)`;
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
                            <td>${new Date((c.processed_at||c.received_at)*1000).toLocaleTimeString('tr-TR', {timeZone: 'Europe/Istanbul'})}</td>
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
                const cfgBak = document.getElementById('cfg-nonecap-backup');
                if (cfgBak) cfgBak.value = data.nonecap_backup_api_key || '';
                document.getElementById('cfg-capsolver').value = data.capsolver_api_key || '';
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
                nonecap_backup_api_key: document.getElementById('cfg-nonecap-backup') ? document.getElementById('cfg-nonecap-backup').value : '',
                capsolver_api_key: document.getElementById('cfg-capsolver').value,
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
                btn.innerText = '⚡ 1 Çözüm Yap';
                refreshData();
            }
        }

        async function triggerWarmup(count) {
            const btn = document.getElementById('btn-warmup');
            btn.disabled = true;
            btn.innerText = '⏳ 7 Token Çözülüyor (Paralel)...';
            showToast('⚡ 7 Token paralel çözülüyor, lütfen 5-10 sn bekleyin...');
            try {
                const res = await fetch('/api/captcha/warmup', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({count: count || 7})
                });
                const data = await res.json();
                if (data.status === 'ready') {
                    showToast('🎉 ' + (data.message || '7 Token hazırlandı!'));
                } else {
                    showToast('❌ ' + (data.error || 'Warmup başarısız'), true);
                }
            } catch(e) {
                showToast('❌ Hata: ' + e, true);
            } finally {
                btn.disabled = false;
                btn.innerText = '🚀 Turbo Doldur (7 Token)';
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

        async function verifyAllAccounts() {
            showToast('🔄 Tüm hesapların bağlantıları ve seviyeleri tazeleniyor...');
            try {
                const res = await fetch('/api/accounts/verify', { method: 'POST' });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || '✅ Tüm hesaplar doğrulandı!');
                    refreshData();
                } else {
                    showToast('Doğrulama hatası: ' + (data.error || 'Hata'), true);
                }
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
        refreshData();
        loadConfig();
        setInterval(refreshData, 3000);
    </script>
</body>
</html>
"""

DURUM_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Canlı Durum & Aktif Hesaplar • Gamblit Auto-Redeemer</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #07090e;
            --surface: #0c1017;
            --card-bg: rgba(16, 22, 34, 0.85);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent: #38bdf8;
            --accent-green: #10b981;
            --accent-red: #f43f5e;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg);
            background-image: 
                radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.08) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(16, 185, 129, 0.06) 0px, transparent 50%);
            color: var(--text-main);
            font-family: 'Plus Jakarta Sans', sans-serif;
            min-height: 100vh;
            padding: 30px 20px;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 28px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--card-border);
            flex-wrap: wrap;
            gap: 16px;
        }
        .title-area h1 {
            font-size: 22px;
            font-weight: 800;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .live-badge {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.35);
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 20px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            letter-spacing: 0.5px;
        }
        .live-dot {
            width: 7px;
            height: 7px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 10px #10b981;
            animation: pulse 1.8s infinite;
        }
        .header-links a {
            color: var(--text-muted);
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--card-border);
            transition: all 0.2s;
        }
        .header-links a:hover {
            color: white;
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.15);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 14px;
            margin-bottom: 28px;
        }
        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 18px 20px;
            backdrop-filter: blur(12px);
        }
        .stat-card .label {
            font-size: 11.5px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-muted);
            font-weight: 700;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .stat-card .val {
            font-size: 24px;
            font-weight: 800;
            color: var(--text-main);
            font-family: 'JetBrains Mono', monospace;
        }
        .stat-card .sub {
            font-size: 11.5px;
            color: var(--text-muted);
            margin-top: 5px;
        }
        .section-title {
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-main);
        }
        .accounts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }
        .acc-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 20px;
            transition: transform 0.2s, border-color 0.2s;
            position: relative;
            overflow: hidden;
        }
        .acc-card:hover {
            transform: translateY(-2px);
            border-color: rgba(56, 189, 248, 0.35);
        }
        .acc-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 16px;
        }
        .acc-info h3 {
            font-size: 16px;
            font-weight: 700;
            color: white;
            margin-bottom: 4px;
        }
        .acc-info .acc-username {
            font-size: 12.5px;
            color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
        }
        .level-badge {
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(14, 165, 233, 0.1));
            border: 1px solid rgba(56, 189, 248, 0.35);
            color: #7dd3fc;
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
        }
        .acc-details {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            background: rgba(0, 0, 0, 0.25);
            padding: 12px 14px;
            border-radius: 10px;
            margin-bottom: 14px;
            border: 1px solid rgba(255, 255, 255, 0.04);
        }
        .acc-prop .p-lbl { font-size: 11px; color: var(--text-muted); margin-bottom: 2px; text-transform: uppercase; font-weight: 600; }
        .acc-prop .p-val { font-size: 15px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: white; }
        .acc-eligibility {
            font-size: 11.5px;
            color: #94a3b8;
            line-height: 1.4;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
        }
        .status-connected {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .status-disconnected {
            background: rgba(244, 63, 94, 0.15);
            color: #fb7185;
            border: 1px solid rgba(244, 63, 94, 0.3);
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.9); }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-area">
                <h1>⚡ Gamblit Auto-Redeemer</h1>
                <span class="live-badge"><span class="live-dot"></span> SİSTEM CANLI</span>
            </div>
            <div class="header-links">
                <a href="/yardim" style="background: rgba(168, 85, 247, 0.15); border-color: rgba(168, 85, 247, 0.35); color: #c084fc;">📚 Yardım Rehberi (/yardım)</a>
                <a href="/test" style="background: rgba(168, 85, 247, 0.15); border-color: rgba(168, 85, 247, 0.35); color: #c084fc;">🧪 Eski Kodla Test Et (/test)</a>
                <a href="/sonuc">📋 Test Sonucu</a>
                <a href="/captcha" style="background: rgba(245, 158, 11, 0.15); border-color: rgba(245, 158, 11, 0.35); color: #fbbf24;">🛡️ Captcha</a>
                <a href="/cc" style="background: rgba(236, 72, 153, 0.15); border-color: rgba(236, 72, 153, 0.35); color: #f472b6;">🍪 Çerez Ayrıştırıcı (/cc)</a>
                <a href="/">⚙️ Kontrol Paneli</a>
            </div>
        </header>

        <!-- Stats Overview -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">👥 Aktif Hesaplar</div>
                <div class="val" id="stat-acc-count">--</div>
                <div class="sub" id="stat-acc-sub">Yükleniyor...</div>
            </div>
            <div class="stat-card">
                <div class="label">💰 Toplam Bakiye</div>
                <div class="val" id="stat-total-dl" style="color: #38bdf8;">-- DL</div>
                <div class="sub">Tüm aktif hesapların toplamı</div>
            </div>
            <div class="stat-card">
                <div class="label">⏱️ WebSocket Ping</div>
                <div class="val" id="stat-ping">-- ms</div>
                <div class="sub" id="stat-ws-sub">Gamblit WS bağlantısı</div>
            </div>
            <div class="stat-card">
                <div class="label">🛡️ Captcha Havuzu</div>
                <div class="val" id="stat-tokens" style="color: #34d399;">--</div>
                <div class="sub" id="stat-captcha-sub">NoneCap Kredisi</div>
            </div>
        </div>

        <div class="section-title">
            👤 Bağlı & Aktif Hesaplar
        </div>
        <div class="accounts-grid" id="accounts-container">
            <!-- Account Cards dynamically loaded here -->
            <div style="color: var(--text-muted); font-size: 13px; padding: 20px;">Hesaplar yükleniyor...</div>
        </div>
    </div>

    <script>
        function getEligibleText(level) {
            const lvl = parseInt(level) || 1;
            const dropTiers = [175, 150, 125, 100, 80, 60, 40, 25, 5];
            const eligible = dropTiers.filter(t => lvl >= t);
            if (eligible.length === 0) return "⚠️ Seviye 5'in altında (seviye dropu alamaz)";
            return `🎯 Seviye ${eligible[0]}+ ödülünden başlayarak ${eligible.length} adet drop kodunu toplar.`;
        }

        async function updateDurum() {
            try {
                const res = await fetch('/api/durum');
                const data = await res.json();

                // Stats Overview
                const totalAcc = data.total_accounts || 0;
                const connAcc = data.connected_accounts || 0;
                document.getElementById('stat-acc-count').innerText = `${connAcc} / ${totalAcc}`;
                document.getElementById('stat-acc-sub').innerText = `${connAcc} Hesap Bağlı & Hazır`;

                document.getElementById('stat-total-dl').innerText = (data.total_dl || 0).toFixed(2) + ' DL';
                document.getElementById('stat-ping').innerText = (data.avg_latency_ms || 0).toFixed(1) + ' ms';
                document.getElementById('stat-ws-sub').innerText = data.accounts.some(a => a.is_connected) ? '✅ WebSocket Aktif' : '❌ Bağlantı Yok';

                const poolTokens = (data.captcha && data.captcha.valid_tokens) ? data.captcha.valid_tokens : 0;
                const remCredits = (data.captcha && data.captcha.nonecap_remaining) ? data.captcha.nonecap_remaining : 1300;
                document.getElementById('stat-tokens').innerText = `${poolTokens} Hazır Token`;
                document.getElementById('stat-captcha-sub').innerText = `${remCredits} NoneCap Kredisi Kaldı`;

                // Render Account Cards
                const container = document.getElementById('accounts-container');
                if (!data.accounts || data.accounts.length === 0) {
                    container.innerHTML = '<div style="color: #94a3b8; font-size: 13px; padding: 20px;">Kayıtlı hesap bulunamadı. Panelden hesap ekleyebilirsiniz.</div>';
                    return;
                }

                let html = '';
                for (const acc of data.accounts) {
                    const isConn = acc.is_authenticated || acc.is_connected;
                    const statusClass = isConn ? 'status-connected' : 'status-disconnected';
                    const statusText = isConn ? '● Bağlı' : '● Bağlantı Yok';
                    const eligText = getEligibleText(acc.level);
                    const balDl = ((parseFloat(acc.balance_dl || 0)) / 100.0).toFixed(2);

                    html += `
                        <div class="acc-card">
                            <div class="acc-header">
                                <div class="acc-info">
                                    <h3>${acc.name || 'Hesap'}</h3>
                                    <div class="acc-username">👤 ${acc.username || '--'}</div>
                                </div>
                                <div class="level-badge">LVL ${acc.level || 1}</div>
                            </div>
                            <div class="acc-details">
                                <div class="acc-prop">
                                    <div class="p-lbl">Bakiye</div>
                                    <div class="p-val" style="color: #38bdf8;">${balDl} DL</div>
                                </div>
                                <div class="acc-prop">
                                    <div class="p-lbl">Durum</div>
                                    <div class="p-val"><span class="status-badge ${statusClass}">${statusText}</span></div>
                                </div>
                            </div>
                            <div class="acc-eligibility">
                                ${eligText}
                            </div>
                        </div>
                    `;
                }
                container.innerHTML = html;
            } catch (e) {
                console.error("Durum güncelleme hatası:", e);
            }
        }

        updateDurum();
        setInterval(updateDurum, 3000);
    </script>
</body>
</html>
"""

SONUC_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Redeem Sonuçları • Gamblit Auto-Redeemer</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #07090e;
            --surface: #0c1017;
            --card-bg: rgba(16, 22, 34, 0.85);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent: #38bdf8;
            --accent-purple: #a855f7;
            --accent-green: #10b981;
            --accent-red: #f43f5e;
            --accent-yellow: #f59e0b;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg);
            background-image: 
                radial-gradient(at 0% 0%, rgba(168, 85, 247, 0.08) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(56, 189, 248, 0.08) 0px, transparent 50%);
            color: var(--text-main);
            font-family: 'Plus Jakarta Sans', sans-serif;
            min-height: 100vh;
            padding: 30px 20px;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--card-border);
            flex-wrap: wrap;
            gap: 16px;
        }
        .title-area h1 { font-size: 22px; font-weight: 800; display: flex; align-items: center; gap: 8px; }
        .header-links { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .header-links a {
            text-decoration: none;
            font-size: 12.5px;
            font-weight: 700;
            padding: 7px 14px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
            border: 1px solid var(--card-border);
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .header-links a:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
            transform: translateY(-1px);
        }
        .btn-test {
            background: linear-gradient(135deg, #a855f7 0%, #6366f1 100%) !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 4px 14px rgba(168, 85, 247, 0.35);
        }
        .btn-test:hover { opacity: 0.95; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 18px 20px;
        }
        .stat-card .label { font-size: 11.5px; text-transform: uppercase; font-weight: 700; color: var(--text-muted); margin-bottom: 6px; letter-spacing: 0.5px; }
        .stat-card .val { font-size: 24px; font-weight: 800; font-family: 'JetBrains Mono', monospace; }
        .stat-card .sub { font-size: 11.5px; color: var(--text-muted); margin-top: 4px; }
        .section-title {
            font-size: 15px;
            font-weight: 800;
            margin: 28px 0 14px 0;
            display: flex;
            align-items: center;
            gap: 8px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: #cbd5e1;
        }
        .results-table-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
            margin-bottom: 24px;
        }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th {
            background: rgba(0, 0, 0, 0.3);
            color: #94a3b8;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            font-weight: 700;
            padding: 14px 18px;
            border-bottom: 1px solid var(--card-border);
        }
        td {
            padding: 14px 18px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-size: 13px;
        }
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: rgba(255, 255, 255, 0.02); }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 6px;
        }
        .badge-warning {
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }
        .badge-info {
            background: rgba(56, 189, 248, 0.15);
            color: #7dd3fc;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }
        .badge-success {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .badge-purple {
            background: rgba(168, 85, 247, 0.15);
            color: #c084fc;
            border: 1px solid rgba(168, 85, 247, 0.3);
        }
        .info-box {
            background: rgba(56, 189, 248, 0.06);
            border: 1px solid rgba(56, 189, 248, 0.2);
            border-radius: 12px;
            padding: 16px 20px;
            font-size: 13px;
            line-height: 1.6;
            color: #94a3b8;
        }
        .info-box strong { color: var(--text-main); }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-area">
                <h1>🧪 Test Redeem Sonuçları</h1>
                <div style="font-size: 12.5px; color: var(--text-muted); margin-top: 4px;">Gerçek Gamblit WebSocket soketinden alınan canlı yanıtlar</div>
            </div>
            <div class="header-links">
                <a href="/test" class="btn-test">⚡ Hızlı Test (0 Kredi)</a>
                <a href="/test?solve=1" class="btn-test" style="background: linear-gradient(135deg, #10b981 0%, #0284c7 100%) !important; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35) !important;">🛡️ Token Çözerek Test Et (11 Kredi)</a>
                <a href="/durum">📊 Canlı Durum</a>
                <a href="/">⚙️ Kontrol Paneli</a>
            </div>
        </header>

        <!-- Stats Grid -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">🎯 Test Edilen Kod</div>
                <div class="val" id="stat-code" style="color: #38bdf8;">--</div>
                <div class="sub" id="stat-time">Test saati: --</div>
            </div>
            <div class="stat-card">
                <div class="label">⏱️ Sunucu Gecikmesi</div>
                <div class="val" id="stat-lat" style="color: #34d399;">-- ms</div>
                <div class="sub" id="stat-lat-sub">WebSocket RTT süresi (Soket hızı)</div>
            </div>
            <div class="stat-card">
                <div class="label">👥 Test Edilen Hesap</div>
                <div class="val" id="stat-accs">--</div>
                <div class="sub">Eşzamanlı denenmiş hesap</div>
            </div>
            <div class="stat-card">
                <div class="label">📡 Soket Durumu</div>
                <div class="val" id="stat-ws" style="color: #38bdf8;">--</div>
                <div class="sub">Gamblit WS bağlantısı</div>
            </div>
        </div>

        <!-- Custom Code Test Bar -->
        <div style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 14px; padding: 14px 18px; margin-bottom: 24px;">
            <form action="/test" method="GET" style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <span style="font-size: 13px; font-weight: 700; color: var(--text-main); white-space: nowrap;">🎯 İstediğin Gerçek Kodu Gir:</span>
                <input type="text" name="code" id="custom-test-code" placeholder="Örn: Gerçek bir drop kodu..." style="flex: 1; min-width: 200px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.12); color: #fff; padding: 9px 14px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-size: 13px; outline: none;">
                <label style="display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--text-muted); cursor: pointer; user-select: none;">
                    <input type="checkbox" name="solve" value="1" style="accent-color: #10b981;"> Token Çöz (11 Kredi)
                </label>
                <button type="submit" style="background: linear-gradient(135deg, #0284c7 0%, #6366f1 100%); color: white; border: none; padding: 9px 18px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; box-shadow: 0 4px 14px rgba(2, 132, 199, 0.3);">🚀 Bu Kodla Test Et</button>
            </form>
        </div>

        <div class="section-title">
            📋 Hesap Bazlı Sunucu Yanıtları
        </div>

        <div class="results-table-card">
            <table>
                <thead>
                    <tr>
                        <th>Hesap</th>
                        <th>Seviye</th>
                        <th>Kod</th>
                        <th>Gamblit Sunucu Mesajı</th>
                        <th>Durum</th>
                        <th>Gecikme</th>
                    </tr>
                </thead>
                <tbody id="results-body">
                    <tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">Sonuçlar yükleniyor...</td></tr>
                </tbody>
            </table>
        </div>

        <div class="info-box">
            💡 <strong>Nasıl Yorumlanmalı?</strong> Bu test, Gamblit WebSocket sunucusuna <code>ClaimPromoCode</code> istek paketi fırlatarak yapılmıştır. Kod eski olduğu için sunucunun <em>"Code expired"</em> veya <em>"Invalid"</em> cevabı dönmesi; <strong>WebSocket bağlantınızın açık olduğunu, oturumunuzun aktif olduğunu ve sunucunun botunuzun isteklerine milisaniyeler içinde cevap verdiğini</strong> kesin olarak kanıtlar!
        </div>

        <div class="section-title" style="margin-top: 28px;">
            💻 Dönen Ham JSON Yanıtı (Full API & WebSocket Response)
        </div>

        <div style="background: rgba(10, 15, 24, 0.95); border: 1px solid var(--card-border); border-radius: 14px; padding: 18px 20px; position: relative; margin-bottom: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="font-size: 11.5px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px;">RAW JSON RESPONSE</span>
                <button onclick="copyRawJson()" style="background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: #f1f5f9; font-size: 11.5px; font-weight: 700; padding: 5px 12px; border-radius: 6px; cursor: pointer;">📋 Kopyala</button>
            </div>
            <pre id="raw-json-box" style="font-family: 'JetBrains Mono', monospace; font-size: 12px; line-height: 1.5; color: #38bdf8; overflow-x: auto; max-height: 420px; white-space: pre-wrap; word-break: break-all; margin: 0;"></pre>
        </div>
    </div>

    <script>
        function copyRawJson() {
            const text = document.getElementById('raw-json-box').innerText;
            navigator.clipboard.writeText(text).then(() => {
                alert("📋 Ham JSON panoya kopyalandı!");
            });
        }

        async function loadSonuc() {
            try {
                const res = await fetch('/api/sonuc');
                const data = await res.json();
                if (!data || data.status === 'none') {
                    document.getElementById('stat-code').innerText = 'Test Yok';
                    document.getElementById('results-body').innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 40px; color: #94a3b8;">Henüz test çalıştırılmadı. <a href="/test" style="color: #38bdf8; font-weight: 700;">Buraya tıklayarak ilk testi yapabilirsiniz.</a></td></tr>';
                    document.getElementById('raw-json-box').innerText = '{}';
                    return;
                }

                document.getElementById('stat-code').innerText = data.code || '--';
                document.getElementById('stat-time').innerText = 'Saat: ' + (data.tested_at || '--');
                const latVal = data.server_latency_ms !== undefined ? data.server_latency_ms : (data.total_latency_ms || 0);
                document.getElementById('stat-lat').innerText = latVal.toFixed(1) + ' ms';
                if (data.captcha_solve_time_sec && data.captcha_solve_time_sec > 0) {
                    document.getElementById('stat-lat-sub').innerText = `Soket: ${latVal.toFixed(1)}ms • Token çözme: ${data.captcha_solve_time_sec}s`;
                } else {
                    document.getElementById('stat-lat-sub').innerText = 'WebSocket RTT süresi (Soket hızı)';
                }
                document.getElementById('stat-accs').innerText = (data.accounts_count || 0) + ' Hesap';
                document.getElementById('stat-ws').innerText = data.ws_connected ? '✅ Aktif' : '❌ Bağlı Değil';

                document.getElementById('raw-json-box').innerText = JSON.stringify(data, null, 2);

                const tbody = document.getElementById('results-body');
                if (!data.accounts || data.accounts.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 30px; color: #94a3b8;">Hesap sonucu bulunamadı.</td></tr>';
                    return;
                }

                let rows = '';
                for (const a of data.accounts) {
                    const badgeClass = `badge-${a.badge_type || 'info'}`;
                    rows += `
                        <tr>
                            <td><strong>${a.account_name || 'Hesap'}</strong><div style="font-size: 11px; color: #64748b;">${a.username || ''}</div></td>
                            <td><span style="font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #38bdf8;">LVL ${a.level || 1}</span></td>
                            <td><code style="font-family: 'JetBrains Mono', monospace; font-weight: 700; background: rgba(255,255,255,0.06); padding: 3px 8px; border-radius: 4px; color: #c084fc;">${a.code || '--'}</code></td>
                            <td>${a.message || '--'}</td>
                            <td><span class="badge ${badgeClass}">${a.badge_text || a.status}</span></td>
                            <td style="font-family: 'JetBrains Mono', monospace; font-weight: 700;">${(a.latency_ms || 0).toFixed(1)} ms</td>
                        </tr>
                    `;
                }
                tbody.innerHTML = rows;
            } catch(e) {
                console.error("Sonuç yükleme hatası:", e);
            }
        }
        loadSonuc();
    </script>
</body>
</html>
"""

LOGS_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gamblit Auto-Redeemer Pro - Canlı Konsol & Loglar</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #07090e;
            --card-bg: rgba(16, 22, 34, 0.85);
            --border: #1a2332;
            --accent: #38bdf8;
            --green: #10b981;
            --red: #f43f5e;
            --yellow: #f59e0b;
            --purple: #a855f7;
            --text-dim: #64748b;
            --text-bright: #f8fafc;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--bg);
            color: var(--text-bright);
            padding: 24px 20px;
            max-width: 1300px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 12px;
        }
        .header-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .logo {
            font-size: 26px;
            background: rgba(56, 189, 248, 0.1);
            padding: 8px 12px;
            border-radius: 12px;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }
        .nav-links {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .nav-btn {
            color: #94a3b8;
            text-decoration: none;
            font-size: 13px;
            font-weight: 700;
            padding: 8px 14px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            transition: all 0.2s;
        }
        .nav-btn:hover {
            color: white;
            background: rgba(255, 255, 255, 0.08);
        }
        .controls {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
        }
        .search-box {
            background: #0d131f;
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: white;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            font-family: 'JetBrains Mono', monospace;
            width: 320px;
            max-width: 100%;
        }
        .search-box:focus {
            outline: none;
            border-color: var(--accent);
        }
        .btn {
            background: #0284c7;
            color: white;
            border: none;
            padding: 10px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: 0.2s;
        }
        .btn:hover { background: #0369a1; }
        .btn-green { background: #10b981; }
        .btn-green:hover { background: #059669; }
        .log-container {
            background: #04060a;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 16px;
            height: calc(100vh - 220px);
            min-height: 500px;
            overflow-y: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12.5px;
            line-height: 1.6;
            box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.8);
        }
        .log-line {
            padding: 3px 6px;
            border-radius: 4px;
            margin-bottom: 2px;
            white-space: pre-wrap;
            word-break: break-all;
            display: flex;
            gap: 8px;
        }
        .log-line:hover {
            background: rgba(255, 255, 255, 0.04);
        }
        .log-info { color: #94a3b8; }
        .log-success { color: #34d399; font-weight: 600; }
        .log-warning { color: #fbbf24; }
        .log-error { color: #f87171; font-weight: 600; }
        .badge-live {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 6px;
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            font-size: 12px;
            font-weight: 700;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.85); }
        }
    </style>
</head>
<body>
    <header>
        <div class="header-title">
            <div class="logo">📜</div>
            <div>
                <h1 style="font-size: 20px; font-weight: 800;">Gamblit Auto-Redeemer Pro — Tüm Loglar & Canlı Konsol</h1>
                <div style="font-size: 12px; color: #64748b; margin-top: 2px;">Tüm drop yakalamaları, WebSocket paketleri ve hCaptcha çözümleri</div>
            </div>
        </div>
        <div class="nav-links">
            <span class="badge-live"><span class="dot"></span> CANLI YAYIN</span>
            <a href="/" class="nav-btn">⚡ Ana Panel</a>
            <a href="/durum" class="nav-btn">📊 Durum</a>
            <a href="/cc" class="nav-btn" style="color: #ec4899;">🍪 /cc</a>
            <a href="/yardim" class="nav-btn" style="color: #c084fc;">📚 Yardım</a>
            <a href="/test" class="nav-btn">🧪 Test Et</a>
        </div>
    </header>

    <div class="controls">
        <div style="display: flex; gap: 10px; align-items: center;">
            <input type="text" id="filter-input" class="search-box" placeholder="🔍 Loglarda ara (kod, seviye, hata)..." oninput="filterLogs()">
            <label style="display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: #94a3b8; cursor: pointer; user-select: none;">
                <input type="checkbox" id="autoscroll-chk" checked> Otomatik Aşağı Kaydır
            </label>
        </div>
        <div style="display: flex; gap: 10px; align-items: center;">
            <span id="log-count" style="font-size: 12px; color: #64748b; font-family: 'JetBrains Mono', monospace;">0 Satır</span>
            <button class="btn" onclick="fetchLogs(true)">🔄 Yenile</button>
            <button class="btn btn-green" onclick="downloadLogs()">💾 Logları İndir (.txt)</button>
        </div>
    </div>

    <div id="log-box" class="log-container">
        <div style="color: #64748b; text-align: center; padding: 40px;">Loglar yükleniyor...</div>
    </div>

    <script>
        let rawLogs = [];
        let isFetching = false;

        function renderLogs(logs) {
            const container = document.getElementById('log-box');
            const search = document.getElementById('filter-input').value.toLowerCase();
            const autoscroll = document.getElementById('autoscroll-chk').checked;

            let filtered = logs;
            if (search) {
                filtered = logs.filter(l => l.toLowerCase().includes(search));
            }

            document.getElementById('log-count').innerText = `${filtered.length} / ${logs.length} Satır`;

            if (filtered.length === 0) {
                container.innerHTML = '<div style="color: #64748b; text-align: center; padding: 40px;">Eşleşen log bulunamadı.</div>';
                return;
            }

            let html = '';
            for (const line of filtered) {
                let cls = 'log-info';
                if (line.includes('SUCCESS') || line.includes('BAŞARIYLA') || line.includes('🎉') || line.includes('Claimed')) {
                    cls = 'log-success';
                } else if (line.includes('WARNING') || line.includes('RATE_LIMIT') || line.includes('RATE_LIMITED') || line.includes('INVALID_CAPTCHA') || line.includes('⚠️')) {
                    cls = 'log-warning';
                } else if (line.includes('ERROR') || line.includes('CRITICAL') || line.includes('failed') || line.includes('❌')) {
                    cls = 'log-error';
                }
                html += `<div class="log-line ${cls}">${escapeHtml(line)}</div>`;
            }
            container.innerHTML = html;

            if (autoscroll) {
                container.scrollTop = container.scrollHeight;
            }
        }

        function escapeHtml(str) {
            return str
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        function filterLogs() {
            renderLogs(rawLogs);
        }

        async function fetchLogs(manual = false) {
            if (isFetching && !manual) return;
            isFetching = true;
            try {
                const res = await fetch('/api/logs?limit=2000');
                if (res.ok) {
                    const data = await res.json();
                    rawLogs = data.logs || [];
                    renderLogs(rawLogs);
                }
            } catch(e) {
                console.error('Log çekme hatası:', e);
            } finally {
                isFetching = false;
            }
        }

        function downloadLogs() {
            const blob = new Blob([rawLogs.join('\\n')], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `gamblit_logs_${new Date().toISOString().slice(0,19).replace(/:/g, '-')}.txt`;
            a.click();
            URL.revokeObjectURL(url);
        }

        fetchLogs(true);
        setInterval(() => fetchLogs(false), 3000);
    </script>
</body>
</html>
"""

CAPTCHA_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gamblit Auto-Redeemer Pro - Captcha & API Havuzu</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #07090e;
            --card-bg: rgba(16, 22, 34, 0.85);
            --border: #1a2332;
            --accent: #38bdf8;
            --green: #10b981;
            --red: #f43f5e;
            --yellow: #f59e0b;
            --purple: #a855f7;
            --text-dim: #64748b;
            --text-bright: #f8fafc;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--bg);
            color: var(--text-bright);
            padding: 24px 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 12px;
        }
        .header-title { display: flex; align-items: center; gap: 12px; }
        .logo {
            font-size: 26px;
            background: rgba(245, 158, 11, 0.1);
            padding: 8px 12px;
            border-radius: 12px;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }
        .nav-links { display: flex; gap: 10px; align-items: center; }
        .nav-btn {
            color: #94a3b8;
            text-decoration: none;
            font-size: 13px;
            font-weight: 700;
            padding: 8px 14px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            transition: all 0.2s;
        }
        .nav-btn:hover { color: white; background: rgba(255, 255, 255, 0.08); }
        .grid-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
            background: linear-gradient(90deg, #f59e0b, #38bdf8);
        }
        .stat-val {
            font-size: 28px;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            margin: 6px 0;
            color: #f8fafc;
        }
        .stat-label { font-size: 12px; color: #94a3b8; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; }
        .stat-sub { font-size: 12px; color: #64748b; margin-top: 4px; }
        
        .section-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 24px;
        }
        .section-title {
            font-size: 16px;
            font-weight: 800;
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 16px;
            color: #f8fafc;
        }
        table { width: 100%; border-collapse: collapse; margin-top: 8px; }
        th, td { padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px; }
        th { color: #64748b; font-size: 11px; text-transform: uppercase; font-weight: 700; letter-spacing: 0.6px; }
        tr:hover td { background: rgba(255, 255, 255, 0.02); }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }
        .badge-success { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
        .badge-warning { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
        .badge-danger { background: rgba(244, 63, 94, 0.15); color: #f87171; border: 1px solid rgba(244, 63, 94, 0.3); }
        .badge-info { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }
        
        .token-item {
            background: #090d14;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 14px 16px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }
        .token-code {
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: #c084fc;
            background: rgba(168, 85, 247, 0.1);
            padding: 4px 8px;
            border-radius: 6px;
        }
        .btn {
            background: #0284c7;
            color: white;
            border: none;
            padding: 9px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            transition: 0.2s;
        }
        .btn:hover { background: #0369a1; }
        .btn-green { background: #10b981; }
        .btn-green:hover { background: #059669; }
    </style>
</head>
<body>
    <header>
        <div class="header-title">
            <div class="logo">🛡️</div>
            <div>
                <h1 style="font-size: 20px; font-weight: 800;">Gamblit Auto-Redeemer Pro — Captcha & API Havuzu</h1>
                <div style="font-size: 12px; color: #64748b; margin-top: 2px;">Canlı hCaptcha tokenları, NoneCap API anahtarları ve kredi durumları</div>
            </div>
        </div>
        <div class="nav-links">
            <a href="/" class="nav-btn">⚡ Ana Panel</a>
            <a href="/durum" class="nav-btn">📊 Durum</a>
            <a href="/logs" class="nav-btn">📜 Loglar</a>
            <a href="/test" class="nav-btn">🧪 Test Et</a>
            <a href="/cc" class="nav-btn" style="color: #ec4899;">🍪 Çerez Ayrıştırıcı (/cc)</a>
            <a href="/yardim" class="nav-btn" style="color: #c084fc;">📚 Yardım (/yardım)</a>
        </div>
    </header>

    <div class="grid-stats">
        <div class="stat-card">
            <div class="stat-label">🎯 Hazır Token Havuzu</div>
            <div id="stat-tokens" class="stat-val" style="color: #34d399;">0 / 0</div>
            <div id="stat-tokens-sub" class="stat-sub">Sıfır gecikmeli (0ms) hazır bekleyen token</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">💳 Toplam NoneCap Kredisi</div>
            <div id="stat-credits" class="stat-val" style="color: #38bdf8;">0</div>
            <div id="stat-credits-sub" class="stat-sub">Tüm API anahtarlarındaki toplam bakiye</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">🔑 Aktif API Anahtarı</div>
            <div id="stat-keys" class="stat-val" style="color: #fbbf24;">0 Adet</div>
            <div id="stat-keys-sub" class="stat-sub">Otomatik rotasyonlu NoneCap havuzu</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">⏳ Zamanlayıcı Durumu</div>
            <div id="stat-sched" class="stat-val" style="font-size: 20px; color: #c084fc;">Uykuda</div>
            <div id="stat-sched-sub" class="stat-sub">20:30 - 20:45 (Drop Aralığı)</div>
        </div>
    </div>

    <div class="section-card">
        <div class="section-title">
            <span>⚡ Havuzdaki Sıcak Tokenlar (0ms Yanıt İçin Hazır)</span>
            <button class="btn btn-green" style="margin-left: auto; font-size: 12px; padding: 6px 12px;" onclick="solveNow()">⚡ 1 Çözüm Yap</button>
        </div>
        <div id="tokens-list">
            <div style="color: #64748b; text-align: center; padding: 20px;">Yükleniyor...</div>
        </div>
    </div>

    <div class="section-card">
        <div class="section-title">
            <span>🔑 Tanımlı NoneCap API Anahtarları & Kredi Kullanımları</span>
            <div style="margin-left: auto; display: flex; gap: 8px;">
                <button id="btn-test-all" class="btn btn-green" style="font-size: 12px; padding: 6px 12px;" onclick="testAllKeys()">🧪 Hepsinden 1 Çözüm Test Et</button>
                <button class="btn" style="font-size: 12px; padding: 6px 12px;" onclick="fetchData()">🔄 Tazele</button>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Anahtar Adı</th>
                    <th>API Key (Önizleme)</th>
                    <th>Yapılan Çözüm</th>
                    <th>Harcanan Kredi</th>
                    <th>Kalan Kredi</th>
                    <th>Durum</th>
                </tr>
            </thead>
            <tbody id="keys-tbody">
                <tr><td colspan="7" style="text-align: center; color: #64748b; padding: 20px;">Yükleniyor...</td></tr>
            </tbody>
        </table>
    </div>

    <script>
        async function fetchData(forceRefresh = false) {
            try {
                const url = forceRefresh ? '/api/captcha/status?refresh=1' : '/api/captcha/status';
                const res = await fetch(url);
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    console.error("Status error:", err);
                    return;
                }
                const d = await res.json();
                
                document.getElementById('stat-tokens').innerText = `${d.valid_token_count || 0} / ${d.target_pool_size || 1} Token`;
                document.getElementById('stat-credits').innerText = (Number(d.total_remaining_credits || 0)).toLocaleString('tr-TR') + ' Kredi';
                document.getElementById('stat-keys').innerText = (Number(d.total_keys_count || 0)) + ' Adet';
                
                if (d.schedule) {
                    const c = d.schedule.countdown || {};
                    document.getElementById('stat-sched').innerText = c.is_active ? '🔥 AKTİF' : '⏳ Uykuda';
                    document.getElementById('stat-sched-sub').innerText = `${d.schedule.start || '20:30'} - ${d.schedule.end || '20:45'} (${c.countdown_text || ''})`;
                }

                // Render ready tokens
                const tBox = document.getElementById('tokens-list');
                if (!d.ready_tokens || d.ready_tokens.length === 0) {
                    tBox.innerHTML = '<div style="color: #64748b; text-align: center; padding: 20px;">Şu an havuzda hazır token yok (Zamanlayıcı uykuda veya token tüketildi).</div>';
                } else {
                    let tHtml = '';
                    d.ready_tokens.forEach((t, i) => {
                        tHtml += `
                            <div class="token-item">
                                <div style="display: flex; align-items: center; gap: 10px;">
                                    <span style="font-weight: 700; color: #38bdf8;">Token #${i+1}</span>
                                    <span class="token-code">${t.preview || ''}</span>
                                </div>
                                <div style="display: flex; gap: 12px; align-items: center; font-size: 12.5px;">
                                    <span style="color: #94a3b8;">Yaş: <strong>${t.age_sec || 0} sn</strong></span>
                                    <span style="color: #34d399; font-weight: 700;">Kalan Süre: ${t.remaining_ttl_sec || 0} sn</span>
                                    <span class="badge ${t.is_fresh ? 'badge-success' : 'badge-warning'}">${t.is_fresh ? 'TAZE' : 'GEÇERLİ'}</span>
                                </div>
                            </div>
                        `;
                    });
                    tBox.innerHTML = tHtml;
                }

                // Render keys table
                const tbody = document.getElementById('keys-tbody');
                if (!d.keys || d.keys.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #64748b; padding: 20px;">Tanımlı NoneCap API anahtarı bulunamadı.</td></tr>';
                } else {
                    let kHtml = '';
                    d.keys.forEach(k => {
                        const remStr = (Number(k.remaining_credits || 0)).toLocaleString('tr-TR');
                        kHtml += `
                            <tr>
                                <td style="font-family: 'JetBrains Mono', monospace; font-weight: 700;">#${k.index || 1}</td>
                                <td><strong>${k.name || ''}</strong></td>
                                <td><code style="font-family: 'JetBrains Mono', monospace; color: #94a3b8; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;">${k.key_preview || ''}</code></td>
                                <td style="font-family: 'JetBrains Mono', monospace;">${k.solves || 0} Çözüm</td>
                                <td style="font-family: 'JetBrains Mono', monospace; color: #f87171;">-${k.charged_credits || 0} Kredi</td>
                                <td style="font-family: 'JetBrains Mono', monospace; font-weight: 800; color: #34d399;">${remStr} Kredi</td>
                                <td><span class="badge badge-${k.badge || 'info'}">${k.status || 'AKTİF'}</span></td>
                            </tr>
                        `;
                    });
                    tbody.innerHTML = kHtml;
                }
            } catch(e) {
                console.error("Captcha veri hatası:", e);
                const tbody = document.getElementById('keys-tbody');
                if (tbody && tbody.innerHTML.includes('Yükleniyor...')) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #f87171; padding: 20px;">Veri alınamadı: ' + e + '</td></tr>';
                }
            }
        }

        async function solveNow() {
            try {
                const res = await fetch('/api/captcha/solve', { method: 'POST' });
                if (res.ok) {
                    fetchData(true);
                } else {
                    const err = await res.json();
                    alert("Çözüm başarısız: " + (err.error || "Hata"));
                }
            } catch(e) {
                alert("İstek hatası: " + e);
            }
        }

        async function testAllKeys() {
            const btn = document.getElementById('btn-test-all');
            if (btn) {
                btn.disabled = true;
                btn.innerText = '⏳ Test Ediliyor...';
            }
            try {
                const res = await fetch('/api/captcha/test-all', { method: 'POST' });
                const d = await res.json();
                if (d.status === 'ok') {
                    let msg = '=== TÜM ANAHTARLARIN TEST SONUÇLARI ===\n\n';
                    d.results.forEach(r => {
                        msg += `[Anahtar #${r.index}] (${r.key_preview}): ${r.message}\n`;
                    });
                    alert(msg);
                    fetchData(true);
                } else {
                    alert('Test hatası: ' + (d.error || 'Bilinmeyen hata'));
                }
            } catch(e) {
                alert('İstek hatası: ' + e);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = '🧪 Hepsinden 1 Çözüm Test Et';
                }
            }
        }

        fetchData();
        setInterval(() => fetchData(false), 4000);
    </script>
</body>
</html>
"""

COOKIE_CONVERTER_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gamblit Çerez Ayrıştırıcı & Formatlayıcı (/cc)</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #07090e;
            --bg-surface: #0c1017;
            --card-bg: rgba(16, 22, 34, 0.85);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-hover: rgba(23, 32, 48, 0.95);
            --accent: #38bdf8;
            --pink: #ec4899;
            --green: #10b981;
            --red: #f43f5e;
            --yellow: #f59e0b;
            --purple: #a855f7;
            --text-dim: #64748b;
            --text: #94a3b8;
            --text-bright: #f8fafc;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--bg);
            background-image: 
                radial-gradient(at 0% 0%, rgba(236, 72, 153, 0.07) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(56, 189, 248, 0.07) 0px, transparent 50%),
                radial-gradient(at 50% 100%, rgba(16, 185, 129, 0.04) 0px, transparent 60%);
            background-attachment: fixed;
            color: var(--text);
            padding: 24px 20px 80px 20px;
            max-width: 1200px;
            margin: auto;
            -webkit-font-smoothing: antialiased;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(12, 16, 23, 0.7);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 18px 24px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }

        .header-title { display: flex; align-items: center; gap: 14px; }
        .logo {
            width: 44px; height: 44px;
            background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%);
            border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            font-size: 22px;
            box-shadow: 0 0 20px rgba(236, 72, 153, 0.35);
        }

        .nav-links { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .nav-btn {
            color: #94a3b8;
            text-decoration: none;
            font-size: 13px;
            font-weight: 700;
            padding: 7px 13px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            transition: all 0.2s;
        }
        .nav-btn:hover {
            color: #fff;
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
        }
        .nav-btn-active {
            color: #ec4899;
            background: rgba(236, 72, 153, 0.12);
            border-color: rgba(236, 72, 153, 0.3);
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
            backdrop-filter: blur(12px);
            margin-bottom: 20px;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            flex-wrap: wrap;
            gap: 12px;
        }

        .card-title {
            font-size: 15px;
            font-weight: 700;
            color: var(--text-bright);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .badge-count {
            display: inline-flex;
            align-items: center;
            padding: 3px 9px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent);
            border: 1px solid rgba(56, 189, 248, 0.3);
        }

        .guide-banner {
            background: linear-gradient(135deg, rgba(168, 85, 247, 0.15) 0%, rgba(56, 189, 248, 0.15) 100%);
            border: 1px solid rgba(168, 85, 247, 0.35);
            border-radius: 14px;
            padding: 16px 20px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 14px;
        }

        .guide-stepper {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 14px;
            margin-bottom: 22px;
        }

        .step-card {
            background: rgba(12, 16, 23, 0.65);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 12px;
            padding: 16px;
            transition: all 0.2s;
        }
        .step-card:hover {
            border-color: rgba(236, 72, 153, 0.3);
            transform: translateY(-2px);
        }

        .step-tag {
            font-size: 11px;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 6px;
            display: inline-block;
            margin-bottom: 10px;
        }

        kbd {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 4px;
            padding: 2px 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: #f8fafc;
        }

        textarea {
            width: 100%;
            height: 140px;
            background: #090d14;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12.5px;
            color: var(--text-bright);
            resize: vertical;
            outline: none;
            transition: all 0.2s;
        }

        textarea:focus {
            border-color: var(--pink);
            box-shadow: 0 0 0 3px rgba(236, 72, 153, 0.2);
        }

        .action-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 14px;
            flex-wrap: wrap;
            gap: 10px;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 18px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
        }

        .btn-primary {
            background: linear-gradient(135deg, #ec4899 0%, #db2777 100%);
            color: white;
            box-shadow: 0 4px 14px rgba(236, 72, 153, 0.35);
        }
        .btn-primary:hover {
            opacity: 0.92;
            transform: translateY(-1px);
        }

        .btn-green {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);
        }
        .btn-green:hover {
            opacity: 0.92;
            transform: translateY(-1px);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.06);
            color: var(--text);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.1);
            color: white;
        }

        .btn-test {
            background: rgba(168, 85, 247, 0.15);
            color: #c084fc;
            border: 1px solid rgba(168, 85, 247, 0.35);
        }
        .btn-test:hover {
            background: rgba(168, 85, 247, 0.25);
            color: #fff;
        }

        .tokens-wrap {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 14px;
        }

        .token-tag {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11.5px;
            padding: 4px 10px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #cbd5e1;
        }

        .token-tag.critical {
            background: rgba(16, 185, 129, 0.15);
            border-color: rgba(16, 185, 129, 0.35);
            color: #34d399;
            font-weight: 700;
        }

        .token-tag.missing {
            background: rgba(244, 63, 94, 0.12);
            border-color: rgba(244, 63, 94, 0.25);
            color: #fb7185;
        }

        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #10b981;
            color: #ffffff;
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 13.5px;
            font-weight: 700;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            opacity: 0;
            transform: translateY(15px);
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
            pointer-events: none;
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .toast.show {
            opacity: 1;
            transform: translateY(0);
        }
        .toast.info { background: #0284c7; }
        .toast.error { background: #e11d48; }
    </style>
</head>
<body>
    <header>
        <div class="header-title">
            <div class="logo">🍪</div>
            <div>
                <h1 style="font-size: 20px; font-weight: 800; color: #f8fafc;">Gamblit Çerez Ayrıştırıcı & Formatlayıcı</h1>
                <div style="font-size: 12px; color: #64748b; margin-top: 2px;">Ctrl+A DevTools Çerez Yapıştırıcı & Panel Uyumlu Tek Satır Çevirici</div>
            </div>
        </div>
        <div class="nav-links">
            <a href="/" class="nav-btn">⚡ Ana Panel</a>
            <a href="/durum" class="nav-btn">📊 Durum</a>
            <a href="/yardim" class="nav-btn" style="color: #a855f7;">📚 Yardım Kılavuzu</a>
            <a href="/captcha" class="nav-btn">🛡️ Captcha</a>
            <a href="/logs" class="nav-btn">📜 Loglar</a>
            <a href="/test" class="nav-btn">🧪 Test Et</a>
            <a href="/cc" class="nav-btn nav-btn-active">🍪 /cc</a>
        </div>
    </header>

    <!-- Acemiler İçin Rehber Yönlendirmesi -->
    <div class="guide-banner">
        <div style="display: flex; align-items: center; gap: 14px;">
            <span style="font-size: 30px;">📖</span>
            <div>
                <strong style="color: #f8fafc; font-size: 14.5px; display: block;">İlk kez mi yapıyorsunuz? Hiç dert etmeyin!</strong>
                <span style="color: #cbd5e1; font-size: 12.5px;">Adım adım anlatımlı, görsel acemi kılavuzumuz için yardım sayfasını açabilirsiniz.</span>
            </div>
        </div>
        <a href="/yardim#cerez-rehberi" style="background: #a855f7; color: white; padding: 9px 18px; border-radius: 9px; font-weight: 800; text-decoration: none; font-size: 13px; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 4px 14px rgba(168, 85, 247, 0.4);">
            📚 Adım Adım Kurulum Rehberi (/yardım) ➔
        </a>
    </div>

    <!-- 4 Basit Adımda Görsel Kılavuz -->
    <div class="guide-stepper">
        <div class="step-card">
            <span class="step-tag" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8;">1. ADIM</span>
            <strong style="color: #f8fafc; font-size: 13.5px; display: block; margin-bottom: 6px;">🌐 Giriş Yap</strong>
            <p style="font-size: 12px; color: #94a3b8; line-height: 1.5; margin: 0;">Tarayıcında <code>gamblit.net</code> sitesini aç ve hesabına giriş yap.</p>
        </div>

        <div class="step-card">
            <span class="step-tag" style="background: rgba(236, 72, 153, 0.15); color: #ec4899;">2. ADIM</span>
            <strong style="color: #f8fafc; font-size: 13.5px; display: block; margin-bottom: 6px;">⌨️ F12 Tuşuna Bas</strong>
            <p style="font-size: 12px; color: #94a3b8; line-height: 1.5; margin: 0;">Klavyeden <kbd>F12</kbd> tuşuna bas (veya sayfaya sağ tık ➔ <b>İncele</b> de).</p>
        </div>

        <div class="step-card">
            <span class="step-tag" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24;">3. ADIM</span>
            <strong style="color: #f8fafc; font-size: 13.5px; display: block; margin-bottom: 6px;">📑 Application ➔ Cookies</strong>
            <p style="font-size: 12px; color: #94a3b8; line-height: 1.5; margin: 0;">Üstten <b>Application</b> ➔ Soldan <b>Cookies</b> ➔ <code>gamblit.net</code> tıkla.</p>
        </div>

        <div class="step-card">
            <span class="step-tag" style="background: rgba(16, 185, 129, 0.15); color: #34d399;">4. ADIM</span>
            <strong style="color: #f8fafc; font-size: 13.5px; display: block; margin-bottom: 6px;">📋 Ctrl+A, Ctrl+C Yap</strong>
            <p style="font-size: 12px; color: #94a3b8; line-height: 1.5; margin: 0;">Tablodan bir yere tıkla, <kbd>Ctrl+A</kbd> + <kbd>Ctrl+C</kbd> yap ve buraya yapıştır!</p>
        </div>
    </div>

    <div class="card">
        <div class="card-header">
            <div class="card-title">
                <span>📥 Ham Çerez Verisi (Ctrl+A DevTools veya Karışık Metin)</span>
                <span id="badge-in-count" class="badge-count" style="display:none;">0 Satır</span>
            </div>
            <div style="display: flex; gap: 8px;">
                <button class="btn btn-test" style="font-size: 12px; padding: 6px 12px;" onclick="fillSampleCookie()">🧪 Örnek Çerezle Dene</button>
                <button class="btn btn-secondary" style="font-size: 12px; padding: 6px 12px;" onclick="clearAll()">Temizle</button>
            </div>
        </div>
        <textarea id="raw-input" placeholder="DevTools'tan kopyaladığın çerez tablosunu veya herhangi bir metni buraya Ctrl+V ile yapıştır..."></textarea>
        <div class="action-bar">
            <span style="font-size: 12px; color: #64748b;">Yapıştırıldığı an arka planda temizlenir, formata sokulur ve panoya kopyalanır.</span>
            <button class="btn btn-primary" onclick="processCookies(true)">⚡ Şimdi Ayrıştır</button>
        </div>
    </div>

    <div class="card">
        <div class="card-header">
            <div class="card-title">
                <span>📤 Panele Uygun Tek Satır Çerez (sid=...; cf_clearance=...)</span>
                <span id="badge-out-count" class="badge-count">0 Çerez</span>
            </div>
            <div style="display: flex; gap: 8px;">
                <button id="btn-import" class="btn btn-green" style="font-size: 12px; padding: 6px 12px;" onclick="importToActiveAccount()">⚡ Aktif Hesaba 1-Tıkla Aktar</button>
                <button id="btn-copy" class="btn btn-primary" style="font-size: 12px; padding: 6px 12px;" onclick="copyOutput()">📋 Panoya Kopyala</button>
            </div>
        </div>
        <textarea id="clean-output" readonly placeholder="Ayrıştırılmış temiz çerez burada tek satır olarak belirecek ve otomatik kopyalanacaktır..."></textarea>
        
        <div style="margin-top: 16px;">
            <div style="font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">Algılanan Çerezler</div>
            <div class="tokens-wrap" id="tokens-list">
                <span class="token-tag missing">Henüz çerez yapıştırılmadı</span>
            </div>
        </div>
    </div>

    <div id="toast" class="toast">✔ Panoya Kopyalandı!</div>

    <script>
        const IGNORED_KEYS = new Set([
            'name', 'value', 'domain', 'path', 'expires', 'expires / max-age', 'size',
            'httponly', 'secure', 'samesite', 'priority', 'partition key site', 'key'
        ]);

        const CRITICAL_KEYS = ['sid', 'cf_clearance', '_vid_t', '_iidt', '__cf_bm'];

        const rawInput = document.getElementById('raw-input');
        const cleanOutput = document.getElementById('clean-output');
        const badgeInCount = document.getElementById('badge-in-count');
        const badgeOutCount = document.getElementById('badge-out-count');
        const tokensList = document.getElementById('tokens-list');
        const toastEl = document.getElementById('toast');

        let toastTimer = null;
        function showToast(text, type = 'success') {
            if (toastTimer) clearTimeout(toastTimer);
            toastEl.textContent = text;
            toastEl.className = 'toast show';
            if (type === 'info') toastEl.classList.add('info');
            if (type === 'error') toastEl.classList.add('error');
            toastTimer = setTimeout(() => {
                toastEl.className = 'toast';
            }, 3000);
        }

        function parseRawCookies(rawText) {
            const cookies = {};
            if (!rawText || !rawText.trim()) return cookies;

            const lines = rawText.split(/\r?\n/);
            let tabLineFound = false;

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;

                if (trimmed.includes('\t')) {
                    const cols = trimmed.split('\t').map(c => c.trim()).filter(Boolean);
                    if (cols.length >= 2) {
                        const name = cols[0];
                        const val = cols[1];
                        if (!IGNORED_KEYS.has(name.toLowerCase()) && !IGNORED_KEYS.has(val.toLowerCase())) {
                            cookies[name] = val;
                            tabLineFound = true;
                        }
                    }
                }
            }

            if (tabLineFound && Object.keys(cookies).length > 0) {
                return cookies;
            }

            const semicolonParts = rawText.split(';');
            for (const part of semicolonParts) {
                const trimmed = part.trim();
                if (!trimmed) continue;
                const eqIdx = trimmed.indexOf('=');
                if (eqIdx > 0) {
                    const name = trimmed.substring(0, eqIdx).trim();
                    const val = trimmed.substring(eqIdx + 1).trim();
                    if (!IGNORED_KEYS.has(name.toLowerCase())) {
                        cookies[name] = val;
                    }
                }
            }

            return cookies;
        }

        function formatCookieString(cookies) {
            const pairs = [];
            for (const [k, v] of Object.entries(cookies)) {
                pairs.push(`${k}=${v}`);
            }
            return pairs.join('; ');
        }

        function updateUI(cookies, shouldAutoCopy = false) {
            const keys = Object.keys(cookies);
            const total = keys.length;

            badgeOutCount.textContent = `${total} Çerez`;

            if (total === 0) {
                cleanOutput.value = '';
                tokensList.innerHTML = '<span class="token-tag missing">Henüz geçerli çerez bulunamadı</span>';
                return;
            }

            const formatted = formatCookieString(cookies);
            cleanOutput.value = formatted;

            let tagsHtml = '';
            for (const k of keys) {
                const isCrit = CRITICAL_KEYS.includes(k);
                tagsHtml += `<span class="token-tag ${isCrit ? 'critical' : ''}">${isCrit ? '⭐ ' : ''}${k}</span>`;
            }
            tokensList.innerHTML = tagsHtml;

            if (shouldAutoCopy && formatted) {
                navigator.clipboard.writeText(formatted).then(() => {
                    showToast('✔ Otomatik Ayrıştırıldı ve Panoya Kopyalandı!', 'success');
                }).catch(() => {
                    showToast('✔ Ayrıştırıldı (Panoya manuel kopyala)', 'info');
                });
            }
        }

        function processCookies(autoCopy = false) {
            const text = rawInput.value;
            const cookies = parseRawCookies(text);
            updateUI(cookies, autoCopy);
        }

        function fillSampleCookie() {
            rawInput.value = "Name\tValue\tDomain\tPath\tExpires\tsid\ts%3AzWfH79jK9qLx0_DemoSession123456.987654321\t.gamblit.net\t/\t2026-10-01T20:00:00.000Z\tcf_clearance\tabc123xyz_CloudflareTokenBypass_987\t.gamblit.net\t/\t2026-10-01T20:00:00.000Z\t_vid_t\txjK08zL11\t.gamblit.net\t/\t2026-10-01T20:00:00.000Z";
            processCookies(true);
            showToast('🧪 Örnek çerez yüklendi ve dönüştürüldü!', 'success');
        }

        rawInput.addEventListener('paste', () => {
            setTimeout(() => {
                processCookies(true);
            }, 50);
        });

        rawInput.addEventListener('input', () => {
            processCookies(false);
        });

        function copyOutput() {
            const text = cleanOutput.value;
            if (!text) {
                showToast('Kopyalanacak çerez yok!', 'error');
                return;
            }
            navigator.clipboard.writeText(text).then(() => {
                showToast('✔ Panoya Kopyalandı!', 'success');
            }).catch(() => {
                cleanOutput.select();
                document.execCommand('copy');
                showToast('✔ Seçildi ve Kopyalandı!', 'success');
            });
        }

        function clearAll() {
            rawInput.value = '';
            cleanOutput.value = '';
            badgeInCount.style.display = 'none';
            badgeOutCount.textContent = '0 Çerez';
            tokensList.innerHTML = '<span class="token-tag missing">Henüz çerez yapıştırılmadı</span>';
            showToast('Temizlendi', 'info');
        }

        async function importToActiveAccount() {
            const text = cleanOutput.value;
            if (!text) {
                showToast('Önce çerez yapıştırın!', 'error');
                return;
            }
            const btn = document.getElementById('btn-import');
            btn.disabled = true;
            btn.innerText = '⏳ Aktarılıyor...';
            try {
                const res = await fetch('/api/auth/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cookies: text })
                });
                const d = await res.json();
                if (d.status === 'ok') {
                    showToast(`✔ Aktif hesaba uygulandı! Kullanıcı: ${d.username || 'Giriş yapıldı'}`, 'success');
                } else {
                    showToast('Hata: ' + (d.error || 'Bilinmeyen hata'), 'error');
                }
            } catch(e) {
                showToast('İstek hatası: ' + e, 'error');
            } finally {
                btn.disabled = false;
                btn.innerText = '⚡ Aktif Hesaba 1-Tıkla Aktar';
            }
        }
    </script>
</body>
</html>
"""

YARDIM_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gamblit Auto-Redeemer Pro — Kullanım & Başlangıç Rehberi</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #07090e;
            --bg-surface: #0c1017;
            --card-bg: rgba(16, 22, 34, 0.85);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-hover: rgba(23, 32, 48, 0.95);
            --accent: #38bdf8;
            --purple: #a855f7;
            --pink: #ec4899;
            --green: #10b981;
            --yellow: #f59e0b;
            --red: #f43f5e;
            --text: #94a3b8;
            --text-bright: #f8fafc;
            --text-dim: #64748b;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--bg);
            background-image: 
                radial-gradient(at 0% 0%, rgba(168, 85, 247, 0.08) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(56, 189, 248, 0.08) 0px, transparent 50%),
                radial-gradient(at 50% 100%, rgba(16, 185, 129, 0.05) 0px, transparent 60%);
            background-attachment: fixed;
            color: var(--text);
            padding: 24px 20px 80px 20px;
            max-width: 1200px;
            margin: auto;
            -webkit-font-smoothing: antialiased;
            line-height: 1.6;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(12, 16, 23, 0.75);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 18px 24px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }

        .header-title { display: flex; align-items: center; gap: 14px; }
        .logo {
            width: 46px; height: 46px;
            background: linear-gradient(135deg, #a855f7 0%, #38bdf8 100%);
            border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            font-size: 24px;
            box-shadow: 0 0 20px rgba(168, 85, 247, 0.4);
            flex-shrink: 0;
        }

        .nav-links { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .nav-btn {
            color: #94a3b8;
            text-decoration: none;
            font-size: 13px;
            font-weight: 700;
            padding: 7px 13px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            transition: all 0.2s;
        }
        .nav-btn:hover {
            color: #fff;
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
        }
        .nav-btn-active {
            color: #a855f7;
            background: rgba(168, 85, 247, 0.12);
            border-color: rgba(168, 85, 247, 0.35);
        }

        .hero {
            background: linear-gradient(135deg, rgba(168, 85, 247, 0.12) 0%, rgba(56, 189, 248, 0.1) 100%);
            border: 1px solid rgba(168, 85, 247, 0.3);
            border-radius: 20px;
            padding: 32px 28px;
            margin-bottom: 28px;
            position: relative;
            overflow: hidden;
        }

        .hero h1 {
            font-size: 26px;
            font-weight: 800;
            color: var(--text-bright);
            letter-spacing: -0.5px;
            margin-bottom: 10px;
        }

        .hero p {
            font-size: 15px;
            color: #cbd5e1;
            max-width: 850px;
            line-height: 1.65;
        }

        .highlights-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 14px;
            margin-top: 24px;
        }

        .highlight-item {
            background: rgba(12, 16, 23, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            padding: 14px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .highlight-icon {
            font-size: 24px;
            width: 40px; height: 40px;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.05);
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0;
        }

        .toc-bar {
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding-bottom: 10px;
            margin-bottom: 28px;
            scrollbar-width: none;
        }
        .toc-btn {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #cbd5e1;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            white-space: nowrap;
            transition: all 0.2s;
        }
        .toc-btn:hover {
            background: rgba(168, 85, 247, 0.15);
            border-color: rgba(168, 85, 247, 0.4);
            color: #fff;
        }

        .section-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 18px;
            padding: 28px;
            margin-bottom: 28px;
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
        }

        .section-title {
            font-size: 20px;
            font-weight: 800;
            color: var(--text-bright);
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .section-sub {
            font-size: 13.5px;
            color: var(--text-dim);
            margin-bottom: 22px;
        }

        .stepper-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 18px;
            margin-bottom: 10px;
        }

        .step-box {
            background: rgba(12, 16, 23, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 20px;
            position: relative;
            transition: all 0.2s;
        }
        .step-box:hover {
            border-color: rgba(168, 85, 247, 0.35);
            background: rgba(16, 22, 34, 0.9);
        }

        .step-num {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px; height: 32px;
            border-radius: 8px;
            background: rgba(168, 85, 247, 0.2);
            color: #c084fc;
            font-size: 14px;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            margin-bottom: 12px;
        }

        .step-box h3 {
            font-size: 15px;
            font-weight: 700;
            color: var(--text-bright);
            margin-bottom: 8px;
        }

        .step-box p {
            font-size: 13px;
            color: #94a3b8;
            line-height: 1.55;
        }

        .guide-step-row {
            display: flex;
            gap: 18px;
            padding: 20px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            align-items: flex-start;
        }
        .guide-step-row:last-child { border-bottom: none; }

        .circle-badge {
            width: 40px; height: 40px;
            border-radius: 50%;
            background: linear-gradient(135deg, #38bdf8 0%, #6366f1 100%);
            display: flex; align-items: center; justify-content: center;
            font-size: 16px;
            font-weight: 800;
            color: white;
            flex-shrink: 0;
            box-shadow: 0 0 14px rgba(56, 189, 248, 0.35);
        }

        .guide-step-content { flex: 1; }
        .guide-step-content h4 {
            font-size: 15.5px;
            font-weight: 700;
            color: var(--text-bright);
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .guide-step-content p {
            font-size: 13.5px;
            color: #cbd5e1;
            line-height: 1.6;
            margin-bottom: 8px;
        }

        kbd {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 5px;
            padding: 2px 7px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: #f8fafc;
            font-weight: 600;
        }

        code {
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.25);
            border-radius: 5px;
            padding: 2px 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: #38bdf8;
        }

        .tip-callout {
            background: rgba(16, 185, 129, 0.08);
            border-left: 4px solid #10b981;
            border-radius: 0 10px 10px 0;
            padding: 12px 16px;
            margin-top: 10px;
            font-size: 13px;
            color: #a7f3d0;
        }

        .warning-callout {
            background: rgba(244, 63, 94, 0.08);
            border-left: 4px solid #f43f5e;
            border-radius: 0 10px 10px 0;
            padding: 12px 16px;
            margin-top: 10px;
            font-size: 13px;
            color: #fca5a5;
        }

        .faq-item {
            border: 1px solid rgba(255, 255, 255, 0.06);
            background: rgba(12, 16, 23, 0.6);
            border-radius: 12px;
            margin-bottom: 14px;
            overflow: hidden;
            transition: all 0.2s;
        }
        .faq-item:hover { border-color: rgba(255, 255, 255, 0.15); }

        .faq-question {
            padding: 18px 22px;
            font-size: 15px;
            font-weight: 700;
            color: var(--text-bright);
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            user-select: none;
        }
        .faq-question:hover { color: #38bdf8; }

        .faq-answer {
            padding: 0 22px 20px 22px;
            font-size: 13.5px;
            color: #94a3b8;
            line-height: 1.65;
            border-top: 1px solid rgba(255, 255, 255, 0.04);
            padding-top: 14px;
        }

        .action-banner {
            background: linear-gradient(135deg, rgba(236, 72, 153, 0.15) 0%, rgba(168, 85, 247, 0.15) 100%);
            border: 1px solid rgba(236, 72, 153, 0.35);
            border-radius: 18px;
            padding: 28px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 18px;
        }

        .btn-cta {
            background: linear-gradient(135deg, #ec4899 0%, #a855f7 100%);
            color: white;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 12px;
            font-weight: 800;
            font-size: 14px;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 6px 20px rgba(236, 72, 153, 0.4);
            transition: all 0.2s;
        }
        .btn-cta:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(236, 72, 153, 0.5);
            opacity: 0.95;
        }
    </style>
</head>
<body>
    <header>
        <div class="header-title">
            <div class="logo">📚</div>
            <div>
                <h1 style="font-size: 20px; font-weight: 800; color: #f8fafc;">Gamblit Auto-Redeemer Pro — Kullanım Kılavuzu</h1>
                <div style="font-size: 12px; color: #64748b; margin-top: 2px;">Sıfırdan Başlangıç, Çerez Alma, Çoklu Hesap ve Drop Rehberi</div>
            </div>
        </div>
        <div class="nav-links">
            <a href="/" class="nav-btn">⚡ Ana Panel</a>
            <a href="/durum" class="nav-btn">📊 Durum</a>
            <a href="/cc" class="nav-btn" style="color: #ec4899;">🍪 Çerez Ayrıştırıcı (/cc)</a>
            <a href="/captcha" class="nav-btn">🛡️ Captcha</a>
            <a href="/logs" class="nav-btn">📜 Loglar</a>
            <a href="/test" class="nav-btn">🧪 Test Et</a>
            <a href="/yardim" class="nav-btn nav-btn-active">📚 Yardım</a>
        </div>
    </header>

    <!-- Hero Bölümü -->
    <div class="hero">
        <h1>👋 Hoş Geldiniz! Gamblit Auto-Redeemer Pro Nedir?</h1>
        <p>
            Gamblit sitesinde her akşam saat <strong>20:30 - 20:45 (TR Saati)</strong> arasında promosyon kodları (drop) dağıtılır. 
            Bu sistem, kod paylaşıldığı salisede (yaklaşık <strong>25 milisaniye</strong> içinde) insan reflekslerinden 100 kat daha hızlı davranarak 
            tüm hesaplarınıza ödülü (Growtopia DL) yükler. Bilgisayarınızı açık tutmanıza gerek kalmadan bulut sunucuda 7/24 kesintisiz çalışır.
        </p>

        <div class="highlights-grid">
            <div class="highlight-item">
                <div class="highlight-icon">⚡</div>
                <div>
                    <strong style="color:#f8fafc; font-size:13.5px; display:block;">25ms Yanıt Hızı</strong>
                    <span style="font-size:12px; color:#94a3b8;">Canlı WebSocket & anında tetikleme</span>
                </div>
            </div>
            <div class="highlight-item">
                <div class="highlight-icon">☁️</div>
                <div>
                    <strong style="color:#f8fafc; font-size:13.5px; display:block;">7/24 Bulut Çalışma</strong>
                    <span style="font-size:12px; color:#94a3b8;">PC/telefon kapalıyken bile yakalar</span>
                </div>
            </div>
            <div class="highlight-item">
                <div class="highlight-icon">👥</div>
                <div>
                    <strong style="color:#f8fafc; font-size:13.5px; display:block;">Çoklu Hesap Desteği</strong>
                    <span style="font-size:12px; color:#94a3b8;">7+ hesapla aynı anda ödül kapma</span>
                </div>
            </div>
            <div class="highlight-item">
                <div class="highlight-icon">🛡️</div>
                <div>
                    <strong style="color:#f8fafc; font-size:13.5px; display:block;">Otomatik Captcha</strong>
                    <span style="font-size:12px; color:#94a3b8;">Yedekli NoneCap çözücü havuzu</span>
                </div>
            </div>
        </div>
    </div>

    <!-- Hızlı Bölüm Menüsü -->
    <div class="toc-bar">
        <a href="#hizli-baslangic" class="toc-btn">🚀 3 Adımda Hızlı Başlangıç</a>
        <a href="#cerez-rehberi" class="toc-btn">🍪 Adım Adım Çerez (Cookie) Alma</a>
        <a href="#coklu-hesap" class="toc-btn">👥 Çoklu Hesap Yönetimi</a>
        <a href="#drop-saatleri" class="toc-btn">⏰ Drop Saatleri & Uyku Modu</a>
        <a href="#sss" class="toc-btn">❓ Sıkça Sorulan Sorular (SSS)</a>
    </div>

    <!-- Bölüm 1: 3 Adımda Hızlı Başlangıç -->
    <div class="section-card" id="hizli-baslangic">
        <div class="section-title">
            <span>🚀 3 Adımda Sistemi Başlatın (Özet)</span>
        </div>
        <div class="section-sub">Sistemi hiç bilmeyen birisi bile bu 3 adımla 3 dakika içinde hazır olabilir.</div>

        <div class="stepper-grid">
            <div class="step-box">
                <div class="step-num">1</div>
                <h3>Çerezini Al</h3>
                <p><code>gamblit.net</code> sitesine tarayıcından giriş yap. <kbd>F12</kbd> tuşuna basıp çerez tablonu kopyala.</p>
            </div>
            <div class="step-box">
                <div class="step-num">2</div>
                <h3>/cc Sayfasına Yapıştır</h3>
                <p><a href="/cc" style="color: #ec4899; text-decoration: none; font-weight: 700;">/cc Çerez Ayrıştırıcı</a> sayfasına yapıştır. Sistem çerezini otomatik temizleyip panona kopyalar.</p>
            </div>
            <div class="step-box">
                <div class="step-num">3</div>
                <h3>Panele Ekle & Arkana Yaslan</h3>
                <p><a href="/" style="color: #38bdf8; text-decoration: none; font-weight: 700;">Ana Panel</a> üzerinden "Hesap Ekle" kısmına yapıştır. Akşam 20:30'da bot kodları senin yerine kapar!</p>
            </div>
        </div>
    </div>

    <!-- Bölüm 2: Adım Adım Resimli Çerez Alma Kılavuzu -->
    <div class="section-card" id="cerez-rehberi">
        <div class="section-title">
            <span>🍪 Adım Adım Çerez (Cookie) Nasıl Alınır?</span>
        </div>
        <div class="section-sub">Google Chrome, Microsoft Edge, Brave veya Opera tarayıcıları için adım adım anlatım:</div>

        <div class="guide-step-row">
            <div class="circle-badge">1</div>
            <div class="guide-step-content">
                <h4>Gamblit Sitesine Girin ve Oturum Açın</h4>
                <p>Tarayıcınızda <code>https://gamblit.net</code> adresine gidin. Kullanıcı adı ve şifrenizle hesabınıza başarılı bir şekilde giriş yapın.</p>
            </div>
        </div>

        <div class="guide-step-row">
            <div class="circle-badge">2</div>
            <div class="guide-step-content">
                <h4>Geliştirici Araçlarını (F12) Açın</h4>
                <p>Klavyenizden <kbd>F12</kbd> tuşuna basın. (Eğer dizüstü bilgisayarda çalışmazsa <kbd>Fn + F12</kbd> basın veya web sayfasında boş bir yere sağ tıklayıp <strong>İncele (Inspect)</strong> seçeneğine tıklayın).</p>
                <div class="tip-callout">💡 Tarayıcının sağında veya altında kodların olduğu bir geliştirici penceresi açılacaktır.</div>
            </div>
        </div>

        <div class="guide-step-row">
            <div class="circle-badge">3</div>
            <div class="guide-step-content">
                <h4>Application (Uygulama) Sekmesini Bulun</h4>
                <p>Açılan pencerenin en üst sekme çubuğunda <em>Elements, Console, Sources, Network, Application...</em> yazar. Buradan <strong>Application</strong> (Türkçe ise <strong>Uygulama</strong>) sekmesine tıklayın.</p>
                <div class="tip-callout">💡 Eğer "Application" görünmüyorsa, pencere dar olduğu için sağdaki küçük <strong><code>>></code></strong> simgesine tıklayın, açılan listeden "Application"ı seçin.</div>
            </div>
        </div>

        <div class="guide-step-row">
            <div class="circle-badge">4</div>
            <div class="guide-step-content">
                <h4>Cookies (Çerezler) ➔ gamblit.net Seçin</h4>
                <p>Sol menüdeki <strong>Storage (Depolama)</strong> başlığının altında <strong>Cookies (Çerezler)</strong> klasörünü göreceksiniz. Yanındaki oka tıklayın ve altından <code>https://gamblit.net</code> adresine tıklayın.</p>
            </div>
        </div>

        <div class="guide-step-row">
            <div class="circle-badge">5</div>
            <div class="guide-step-content">
                <h4>Ctrl+A ve Ctrl+C ile Hepsini Kopyalayın</h4>
                <p>Sağ tarafta <em>Name, Value, Domain...</em> sütunları olan bir çerez tablosu çıkacaktır. Bu tablodaki herhangi bir satıra bir kez tıklayın. Ardından klavyenizden <kbd>Ctrl + A</kbd> (tümünü seç) ve hemen ardından <kbd>Ctrl + C</kbd> (kopyala) yapın.</p>
            </div>
        </div>

        <div class="guide-step-row">
            <div class="circle-badge">6</div>
            <div class="guide-step-content">
                <h4>Sitemizdeki /cc Sayfasına Yapıştırın!</h4>
                <p>Sitemizin üst menüsündeki <a href="/cc" style="color: #ec4899; font-weight: 700;">🍪 Çerez Ayrıştırıcı (/cc)</a> sayfasına gidin. Giriş kutusuna <kbd>Ctrl + V</kbd> ile yapıştırın.</p>
                <div class="tip-callout">
                    ✨ <strong>Sihir Başlasın:</strong> Hiçbir butona basmanıza gerek kalmaz! Sistem tablodaki gereksiz verileri ayıklar, <code>sid=...; cf_clearance=...</code> formatına dönüştürür ve doğrudan panonuza kopyalar. İsterseniz <strong>"⚡ Aktif Hesaba 1-Tıkla Aktar"</strong> butonuna basarak doğrudan panele de yükleyebilirsiniz!
                </div>
            </div>
        </div>
    </div>

    <!-- Bölüm 3: Çoklu Hesap Yönetimi -->
    <div class="section-card" id="coklu-hesap">
        <div class="section-title">
            <span>👥 Çoklu Hesap (Multi-Account) Nasıl Eklenir?</span>
        </div>
        <div class="section-sub">Kazancınızı 7 katına kadar çıkarın. Sistem tüm hesaplara aynı anda kodu basar!</div>

        <div style="font-size: 14px; color: #cbd5e1; line-height: 1.7; margin-bottom: 20px;">
            Sistemimiz birden fazla Gamblit hesabını aynı anda yönetmek için özel olarak tasarlanmıştır. 
            Discord'a kod paylaşıldığı anda bot, her hesabın açık olan WebSocket soketi üzerinden AYNI ANDA istek atar. 
            Böylece 7 hesabınız varsa, 7 hesabınız birden 25-40 milisaniye içinde kodu yakalayıp DL'leri kazanır.
        </div>

        <div class="stepper-grid">
            <div class="step-box">
                <div class="step-num">A</div>
                <h3>Farklı Profil Açın</h3>
                <p>Chrome veya tarayıcınızda her Gamblit hesabı için ayrı bir kullanıcı profili (veya Gizli Sekme) açarak hesaplarınıza giriş yapın.</p>
            </div>
            <div class="step-box">
                <div class="step-num">B</div>
                <h3>Her Hesabın Çerezini Alın</h3>
                <p>Her hesabın profilinde <kbd>F12</kbd> ile çerezini alıp <a href="/cc" style="color: #ec4899; text-decoration: none; font-weight: 700;">/cc</a> sayfasında temizleyin.</p>
            </div>
            <div class="step-box">
                <div class="step-num">C</div>
                <h3>Panele Ekleyin</h3>
                <p><a href="/" style="color: #38bdf8; text-decoration: none; font-weight: 700;">Ana Panel</a>'deki <strong>👥 Çoklu Hesap Yönetimi</strong> alanından hesaba isim verip çerezini yapıştırın.</p>
            </div>
        </div>

        <div class="tip-callout" style="margin-top: 18px;">
            📊 Tüm hesaplarınızın online olup olmadığını, seviyelerini ve biriken DL bakiyelerini <a href="/durum" style="color: #34d399; font-weight: 800; text-decoration: none;">/durum (Canlı Durum)</a> sayfasından anlık izleyebilirsiniz.
        </div>
    </div>

    <!-- Bölüm 4: Drop Saatleri ve Akıllı Uyku Modu -->
    <div class="section-card" id="drop-saatleri">
        <div class="section-title">
            <span>⏰ Akşam Drop Saatleri (20:30) & Akıllı Uyku Modu</span>
        </div>
        <div class="section-sub">Bot gün boyunca ne yapar ve akşam drop anında nasıl davranır?</div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px;">
            <div style="background: rgba(12, 16, 23, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 18px;">
                <div style="color: #fbbf24; font-size: 12px; font-weight: 800; text-transform: uppercase; margin-bottom: 6px;">Gün Boyu</div>
                <h4 style="color: #f8fafc; font-size: 15px; margin-bottom: 8px;">⏳ Akıllı Uyku Modu</h4>
                <p style="font-size: 12.5px; color: #94a3b8; line-height: 1.55; margin: 0;">
                    Drop saatine saatler varken sistem kendini korumaya alır. Boş yere captcha kredisi veya sunucu kaynağı harcanmaz. Discord Gateway 0ms ile tetikte bekler.
                </p>
            </div>

            <div style="background: rgba(12, 16, 23, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 18px;">
                <div style="color: #38bdf8; font-size: 12px; font-weight: 800; text-transform: uppercase; margin-bottom: 6px;">Saat 20:15</div>
                <h4 style="color: #f8fafc; font-size: 15px; margin-bottom: 8px;">🛡️ Drop Öncesi Sağlık Raporu</h4>
                <p style="font-size: 12.5px; color: #94a3b8; line-height: 1.55; margin: 0;">
                    Sistem 20:15'te otomatik olarak tüm hesapların oturumunu, bakiyelerini ve NoneCap kredilerini tarar. Discord kanalınıza detaylı sağlık raporu atar.
                </p>
            </div>

            <div style="background: rgba(12, 16, 23, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 18px;">
                <div style="color: #a855f7; font-size: 12px; font-weight: 800; text-transform: uppercase; margin-bottom: 6px;">Saat 20:25 - 20:30</div>
                <h4 style="color: #f8fafc; font-size: 15px; margin-bottom: 8px;">🔥 Isınma & Token Hazırlığı</h4>
                <p style="font-size: 12.5px; color: #94a3b8; line-height: 1.55; margin: 0;">
                    Sistem hCaptcha çözücü havuzunu doldurur, tüm hesapların WebSocket soketlerini sıcak tutar ve kodun gelmesini beklemeye başlar.
                </p>
            </div>

            <div style="background: rgba(12, 16, 23, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 18px;">
                <div style="color: #10b981; font-size: 12px; font-weight: 800; text-transform: uppercase; margin-bottom: 6px;">Saat 20:30 - 20:45</div>
                <h4 style="color: #f8fafc; font-size: 15px; margin-bottom: 8px;">⚡ DROP ANI (25ms Avı)</h4>
                <p style="font-size: 12.5px; color: #94a3b8; line-height: 1.55; margin: 0;">
                    Discord'da kod yayınlandığı salisede bot kodu kapar, hazır tokenla birlikte soketten gönderir ve ödülü hesaba geçirir!
                </p>
            </div>
        </div>
    </div>

    <!-- Bölüm 5: SSS -->
    <div class="section-card" id="sss">
        <div class="section-title">
            <span>❓ Sıkça Sorulan Sorular (SSS)</span>
        </div>
        <div class="section-sub">Kullanıcıların en çok merak ettiği konuların yanıtları:</div>

        <div class="faq-item">
            <div class="faq-question">
                <span>1. Bilgisayarımı veya telefonumu açık tutmam gerekiyor mu?</span>
                <span>▼</span>
            </div>
            <div class="faq-answer">
                <strong>Kesinlikle HAYIR!</strong> Sistem Render bulut sunucularında 7 gün 24 saat kesintisiz çalışmaktadır. Bilgisayarınızı veya telefonunuzu tamamen kapatsanız bile bot drop saatinde çalışıp kodları sizin için yakalar.
            </div>
        </div>

        <div class="faq-item">
            <div class="faq-question">
                <span>2. Çerezimin süresi ne zaman biter? Çerez düşerse ne yapmalıyım?</span>
                <span>▼</span>
            </div>
            <div class="faq-answer">
                Gamblit oturum çerezleri ortalama <strong>2 hafta ile 1 ay</strong> arasında geçerliliğini korur. Eğer bir hesabın çerezi düşerse sistem Discord webhook'unuza anında <strong>"⚠️ Hesap Çevrimdışı!"</strong> uyarısı yollar. Tek yapmanız gereken o hesaba tarayıcıdan girip F12 ile yeni çerezinizi almak ve panele yapıştırmaktır.
            </div>
        </div>

        <div class="faq-item">
            <div class="faq-question">
                <span>3. Hesabım banlanır veya ceza alır mı?</span>
                <span>▼</span>
            </div>
            <div class="faq-answer">
                Sistem Gamblit'in resmi WebSocket protokolünü ve gerçek tarayıcı istek başlıklarını (headers) birebir taklit eder. Gamblit güvenlik duvarı botu gerçek bir kullanıcı gibi algılar. Bu nedenle ban riski yoktur.
            </div>
        </div>

        <div class="faq-item">
            <div class="faq-question">
                <span>4. Kazandığım DL'leri Growtopia'ya nasıl çekerim?</span>
                <span>▼</span>
            </div>
            <div class="faq-answer">
                <code>gamblit.net</code> web sitesine hesabınızla giriş yapın. Üst menüde yer alan bakiye butonuna tıklayıp <strong>Withdraw (Çekim)</strong> seçeneğini seçin. Growtopia oyunundaki <strong>GrowID</strong>'nizi ve içinde depo kutusu (Drop Box) bulunan <strong>Dünya (World)</strong> adınızı yazarak talep verin. Sistem saniyeler içinde DL'leri teslim eder.
            </div>
        </div>

        <div class="faq-item">
            <div class="faq-question">
                <span>5. NoneCap Captcha kredisi nedir ve ne işe yarar?</span>
                <span>▼</span>
            </div>
            <div class="faq-answer">
                Gamblit kod girilirken bot koruması olarak hCaptcha sorar. Sistem NoneCap yapay zeka havuzunu kullanarak bu captcha'ları arka planda otomatik çözer. Kredi durumunuzu <a href="/captcha" style="color: #fbbf24; text-decoration: none; font-weight: 700;">/captcha</a> sayfasından veya 15 dakikada bir Discord'a gelen durum raporundan takip edebilirsiniz.
            </div>
        </div>
    </div>

    <!-- Alt Eylem Bannerı -->
    <div class="action-banner">
        <div>
            <h3 style="font-size: 18px; font-weight: 800; color: #f8fafc; margin-bottom: 4px;">Hazır mısınız? Hemen Çerezinizi Ekleyin!</h3>
            <p style="font-size: 13.5px; color: #cbd5e1; margin: 0;">Çerez ayrıştırıcıya giderek 1 tıkla çerezinizi panele aktarabilir veya canlı durumunuzu kontrol edebilirsiniz.</p>
        </div>
        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <a href="/cc" class="btn-cta">🍪 Çerez Ayrıştırıcıyı Aç (/cc)</a>
            <a href="/durum" class="btn-cta" style="background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); box-shadow: 0 6px 20px rgba(2, 132, 199, 0.4);">📊 Canlı Durumu İzle (/durum)</a>
        </div>
    </div>
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
        self._last_test_result: Optional[Dict[str, Any]] = None
        self._latency_ping_task: Optional[asyncio.Task] = None
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
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/ping", self.handle_health)
        self.app.router.add_get("/durum", self.handle_durum)
        self.app.router.add_get("/api/durum", self.handle_durum_api)
        self.app.router.add_get("/test", self.handle_test_redeem)
        self.app.router.add_post("/api/test", self.handle_test_redeem_api)
        self.app.router.add_get("/sonuc", self.handle_sonuc)
        self.app.router.add_get("/api/sonuc", self.handle_sonuc_api)
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/config", self.handle_get_config)
        self.app.router.add_post("/api/config", self.handle_save_config)
        self.app.router.add_post("/api/redeem", self.handle_manual_redeem)
        self.app.router.add_post("/api/captcha", self.handle_inject_captcha)
        self.app.router.add_options("/api/captcha", self.handle_cors_preflight)
        self.app.router.add_post("/api/auth/import", self.handle_import_auth)
        self.app.router.add_options("/api/auth/import", self.handle_cors_preflight)
        self.app.router.add_post("/api/captcha/solve", self.handle_solve_now)
        self.app.router.add_post("/api/captcha/warmup", self.handle_warmup)
        self.app.router.add_get("/api/accounts", self.handle_get_accounts)
        self.app.router.add_post("/api/accounts", self.handle_add_account)
        self.app.router.add_post("/api/accounts/verify", self.handle_verify_all_accounts)
        self.app.router.add_delete("/api/accounts/{id}", self.handle_remove_account)
        self.app.router.add_post("/api/accounts/{id}/toggle", self.handle_toggle_account)
        self.app.router.add_post("/api/accounts/{id}/test", self.handle_test_account)
        self.app.router.add_post("/api/codes/clear", self.handle_clear_codes)
        self.app.router.add_get("/logs", self.handle_logs_page)
        self.app.router.add_get("/api/logs", self.handle_logs_api)
        self.app.router.add_get("/captcha", self.handle_captcha_page)
        self.app.router.add_get("/api/captcha/status", self.handle_captcha_status_api)
        self.app.router.add_post("/api/captcha/test-all", self.handle_test_all_keys)
        self.app.router.add_get("/cc", self.handle_cookie_converter_page)
        self.app.router.add_get("/cookie", self.handle_cookie_converter_page)
        self.app.router.add_get("/yardim", self.handle_yardim_page)
        self.app.router.add_get("/yardım", self.handle_yardim_page)
        self.app.router.add_get("/help", self.handle_yardim_page)

    async def handle_captcha_page(self, request: web.Request) -> web.Response:
        try:
            status_data = await self.captcha_pool.get_detailed_status()
            keys = status_data.get("keys", [])
            tokens = status_data.get("ready_tokens", [])

            if not keys:
                keys_html = '<tr><td colspan="7" style="text-align: center; color: #64748b; padding: 20px;">Tanımlı NoneCap API anahtarı bulunamadı.</td></tr>'
            else:
                rows = []
                for k in keys:
                    rem = f"{k.get('remaining_credits', 0):,}".replace(",", ".")
                    rows.append(f"""
                        <tr>
                            <td style="font-family: 'JetBrains Mono', monospace; font-weight: 700;">#{k.get('index', 1)}</td>
                            <td><strong>{k.get('name', '')}</strong></td>
                            <td><code style="font-family: 'JetBrains Mono', monospace; color: #94a3b8; background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;">{k.get('key_preview', '')}</code></td>
                            <td style="font-family: 'JetBrains Mono', monospace;">{k.get('solves', 0)} Çözüm</td>
                            <td style="font-family: 'JetBrains Mono', monospace; color: #f87171;">-{k.get('charged_credits', 0)} Kredi</td>
                            <td style="font-family: 'JetBrains Mono', monospace; font-weight: 800; color: #34d399;">{rem} Kredi</td>
                            <td><span class="badge badge-{k.get('badge', 'info')}">{k.get('status', 'AKTİF')}</span></td>
                        </tr>
                    """)
                keys_html = "".join(rows)

            if not tokens:
                tokens_html = '<div style="color: #64748b; text-align: center; padding: 20px;">Şu an havuzda hazır token yok (Zamanlayıcı uykuda veya token tüketildi).</div>'
            else:
                t_rows = []
                for i, t in enumerate(tokens, 1):
                    badge_cls = "badge-success" if t.get("is_fresh") else "badge-warning"
                    badge_lbl = "TAZE" if t.get("is_fresh") else "GEÇERLİ"
                    t_rows.append(f"""
                        <div class="token-item">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span style="font-weight: 700; color: #38bdf8;">Token #{i}</span>
                                <span class="token-code">{t.get('preview', '')}</span>
                            </div>
                            <div style="display: flex; gap: 12px; align-items: center; font-size: 12.5px;">
                                <span style="color: #94a3b8;">Yaş: <strong>{t.get('age_sec', 0)} sn</strong></span>
                                <span style="color: #34d399; font-weight: 700;">Kalan Süre: {t.get('remaining_ttl_sec', 0)} sn</span>
                                <span class="badge {badge_cls}">{badge_lbl}</span>
                            </div>
                        </div>
                    """)
                tokens_html = "".join(t_rows)

            total_creds = f"{status_data.get('total_remaining_credits', 0):,}".replace(",", ".")
            tokens_stat = f"{status_data.get('valid_token_count', 0)} / {status_data.get('target_pool_size', 1)} Token"
            keys_stat = f"{status_data.get('total_keys_count', 0)} Adet"

            rendered_html = CAPTCHA_HTML_TEMPLATE.replace(
                '<div id="stat-tokens" class="stat-val" style="color: #34d399;">0 / 0</div>',
                f'<div id="stat-tokens" class="stat-val" style="color: #34d399;">{tokens_stat}</div>'
            ).replace(
                '<div id="stat-credits" class="stat-val" style="color: #38bdf8;">0</div>',
                f'<div id="stat-credits" class="stat-val" style="color: #38bdf8;">{total_creds} Kredi</div>'
            ).replace(
                '<div id="stat-keys" class="stat-val" style="color: #fbbf24;">0 Adet</div>',
                f'<div id="stat-keys" class="stat-val" style="color: #fbbf24;">{keys_stat}</div>'
            ).replace(
                '<div id="tokens-list">\n            <div style="color: #64748b; text-align: center; padding: 20px;">Yükleniyor...</div>\n        </div>',
                f'<div id="tokens-list">\n            {tokens_html}\n        </div>'
            ).replace(
                '<tr><td colspan="7" style="text-align: center; color: #64748b; padding: 20px;">Yükleniyor...</td></tr>',
                keys_html
            )
            return web.Response(text=rendered_html, content_type="text/html")
        except Exception:
            return web.Response(text=CAPTCHA_HTML_TEMPLATE, content_type="text/html")

    async def handle_captcha_status_api(self, request: web.Request) -> web.Response:
        try:
            refresh = request.query.get("refresh", "0") in ("1", "true")
            status_data = await self.captcha_pool.get_detailed_status(force_refresh=refresh)
            return web.json_response(status_data)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_test_all_keys(self, request: web.Request) -> web.Response:
        try:
            results = await self.captcha_pool.test_all_keys()
            return web.json_response({"status": "ok", "results": results})
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)}, status=500)

    async def handle_logs_page(self, request: web.Request) -> web.Response:
        return web.Response(text=LOGS_HTML_TEMPLATE, content_type="text/html")

    async def handle_cookie_converter_page(self, request: web.Request) -> web.Response:
        return web.Response(text=COOKIE_CONVERTER_HTML_TEMPLATE, content_type="text/html")

    async def handle_yardim_page(self, request: web.Request) -> web.Response:
        return web.Response(text=YARDIM_HTML_TEMPLATE, content_type="text/html")

    async def handle_logs_api(self, request: web.Request) -> web.Response:
        limit = int(request.query.get("limit", 2000))
        lines = get_all_logs(log_file=self.config.log_file, max_lines=limit)
        return web.json_response({"logs": lines, "count": len(lines)})

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
        
        # Test connection and measure live pure latency
        if not acc.client._connected:
            await acc.client.connect_ws()
        profile = await acc.client.get_profile()
        latency_ms = await acc.client.measure_ws_latency()
        if profile and profile.is_authenticated:
            lat_str = f" | Gecikme: {latency_ms:.1f}ms" if latency_ms > 0 else ""
            return web.json_response({
                "status": "success",
                "message": f"✅ Bağlantı BAŞARILI: {profile.username} (Level {profile.level}, {profile.balance_dl} DL{lat_str})",
                "latency_ms": latency_ms,
                "account": acc.to_dict()
            })
        return web.json_response({
            "status": "failed",
            "message": "❌ Bağlantı kurulamadı. Çerezler geçersiz olabilir veya onay bekliyor.",
            "account": acc.to_dict()
        })

    async def handle_verify_all_accounts(self, request: web.Request) -> web.Response:
        if not self.account_manager:
            return web.json_response({"error": "Account manager not available"}, status=500)
        summary = await self.account_manager.verify_all()
        conn_cnt = summary.get("connected_accounts", 0)
        tot_cnt = summary.get("total_accounts", 0)
        return web.json_response({
            "status": "ok",
            "message": f"✅ {conn_cnt}/{tot_cnt} hesap doğrulandı ve bağlantıları tazelendi!",
            "summary": summary
        })

    async def handle_cors_preflight(self, request: web.Request) -> web.Response:
        return web.Response(status=200)

    async def handle_health(self, request: web.Request) -> web.Response:
        ws_conn = any(a.client._connected for a in self.account_manager.accounts.values() if a.enabled) if (self.account_manager and self.account_manager.accounts) else self.client._connected
        return web.json_response({
            "status": "ok",
            "uptime": "active",
            "time_tr": self.config.get_tr_now().strftime("%H:%M:%S"),
            "ws_connected": ws_conn,
        })

    async def handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=HTML_TEMPLATE, content_type="text/html")

    async def handle_durum(self, request: web.Request) -> web.Response:
        return web.Response(text=DURUM_HTML_TEMPLATE, content_type="text/html")

    async def handle_durum_api(self, request: web.Request) -> web.Response:
        summary = self.account_manager.get_summary() if self.account_manager else {
            "total_accounts": 0,
            "connected_accounts": 0,
            "total_dl": 0,
            "accounts": [],
        }
        balances = await self.captcha_pool.get_balances() if self.captcha_pool else {}
        nonecap_rem = balances.get("nonecap")
        nonecap_credits = 1300
        if nonecap_rem is not None:
            try:
                nonecap_credits = int(str(nonecap_rem).split()[0])
            except Exception:
                nonecap_credits = nonecap_rem

        raw_total = summary.get("total_dl", 0) or 0
        total_dl_val = round(float(raw_total) / 100.0, 2)
        avg_lat = self.metrics.summary().get("avg_latency_ms", 0.0) if self.metrics else 0.0

        return web.json_response({
            "total_accounts": summary.get("total_accounts", 0),
            "connected_accounts": summary.get("connected_accounts", 0),
            "total_dl": total_dl_val,
            "avg_latency_ms": avg_lat,
            "captcha": {
                "valid_tokens": self.captcha_pool.valid_token_count if self.captcha_pool else 0,
                "target_pool_size": self.captcha_pool.target_pool_size if self.captcha_pool else 1,
                "nonecap_remaining": nonecap_credits,
                "is_solving": self.captcha_pool.is_solving if self.captcha_pool else False,
            },
            "accounts": summary.get("accounts", []),
        })

    async def _get_test_code(self) -> str:
        # 0. Check TEST_CODE env var
        env_code = os.getenv("TEST_CODE") or os.getenv("TEST_PROMO_CODE")
        if env_code and env_code.strip():
            return env_code.strip()

        # 1. Check DB for the most recent code
        try:
            async with self.db._connection.cursor() as cursor:
                await cursor.execute("SELECT code FROM codes ORDER BY id DESC LIMIT 1")
                row = await cursor.fetchone()
                if row and row["code"]:
                    return row["code"]
        except Exception:
            pass

        # 2. Check Discord channel messages if token present
        if self.config.discord_token and self.config.discord_channel_id:
            try:
                import aiohttp
                token = self.config.discord_token
                auth_header = f"Bot {token}" if not token.startswith("Bot ") and "." in token and len(token) > 50 and not token.startswith("mfa.") else token
                headers = {
                    "Authorization": auth_header,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                }
                url = f"https://discord.com/api/v10/channels/{self.config.discord_channel_id}/messages?limit=25"
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                        if resp.status == 200:
                            msgs = await resp.json()
                            from app.parser import extract_level_codes, extract_code_from_text
                            for m in msgs:
                                content = m.get("content", "")
                                l_codes = extract_level_codes(content)
                                if l_codes:
                                    return l_codes[0][1]
                                c = extract_code_from_text(content)
                                if c:
                                    return c
            except Exception:
                pass

        # 3. Fallback known real drop code
        return "NIGHTDROP"

    async def run_redeem_test(self, test_code: Optional[str] = None, solve_captcha: bool = False) -> Dict[str, Any]:
        if not test_code:
            test_code = await self._get_test_code()

        results = []

        # Check if pool has a token, or solve one if requested
        captcha_tok = ""
        captcha_solve_sec = 0.0
        if self.captcha_pool:
            if self.captcha_pool.is_token_valid:
                captcha_tok = await self.captcha_pool.consume_token() or ""
            elif solve_captcha:
                t_c0 = time.time()
                captcha_tok = await self.captcha_pool.auto_solve_once() or ""
                captcha_solve_sec = round(time.time() - t_c0, 2)

        # Measure pure Gamblit WebSocket communication latency (RTT)
        t_socket_start = time.perf_counter()
        if self.account_manager and self.account_manager.accounts:
            results = await self.account_manager.redeem_all(
                code=test_code,
                captcha_token=captcha_tok,
            )
        else:
            lat = RedeemLatency(t0_discord_received=t_socket_start)
            res = await self.client.redeem_code(test_code, latency=lat, captcha_token=captcha_tok)
            results = [{
                "account_id": "acc_default",
                "account_name": "Ana Hesap",
                "username": self.client._profile.username if self.client._profile else "Ana Hesap",
                "level": self.client._profile.level if self.client._profile else 1,
                "code": test_code,
                "req_level": 0,
                "result": res,
            }]

        socket_lat_ms = (time.perf_counter() - t_socket_start) * 1000.0

        formatted_accs = []
        best_socket_lat = None
        for r in results:
            res_obj = r.get("result")
            status_val = res_obj.status.value if res_obj else "UNKNOWN"
            msg = res_obj.message if res_obj else "Yanıt yok"
            resp_data = res_obj.response_data if res_obj else {}
            
            # Exact WebSocket RTT recorded inside redeem_code()
            acc_lat = res_obj.latency.http_request_ms if (res_obj and res_obj.latency and res_obj.latency.http_request_ms > 0) else socket_lat_ms
            if best_socket_lat is None or acc_lat < best_socket_lat:
                best_socket_lat = acc_lat

            msg_upper = (str(msg) + " " + str(resp_data)).upper()
            is_success = (status_val.upper() == "SUCCESS") or (isinstance(resp_data, dict) and resp_data.get("success") is True)
            if is_success:
                badge_type = "success"
                badge_text = "🎉 Başarıyla Alındı!"
            elif "CAPTCHA" in msg_upper:
                badge_type = "purple"
                badge_text = "🛡️ Captcha İstendi (Token Gerekli)"
            elif "EXPIRED" in msg_upper or "SÜRESİ" in msg_upper:
                badge_type = "warning"
                badge_text = "ℹ️ Kodun Süresi Dolmuş"
            elif "ALREADY" in msg_upper or "ZATEN" in msg_upper:
                badge_type = "info"
                badge_text = "ℹ️ Zaten Alınmış"
            elif "INVALID_CODE" in msg_upper or "INVALID" in msg_upper or "GEÇERSİZ" in msg_upper:
                badge_type = "warning"
                badge_text = "❌ Geçersiz Kod"
            else:
                badge_type = "info"
                badge_text = f"● {status_val}"

            acc_id = r.get("account_id")
            lvl = r.get("level")
            if not lvl and self.account_manager and acc_id in self.account_manager.accounts:
                lvl = self.account_manager.accounts[acc_id].level

            formatted_accs.append({
                "account_id": acc_id,
                "account_name": r.get("account_name"),
                "username": r.get("username"),
                "level": lvl or 1,
                "code": r.get("code"),
                "status": status_val,
                "badge_type": badge_type,
                "badge_text": badge_text,
                "message": msg,
                "latency_ms": round(acc_lat, 2),
                "response_data": resp_data,
            })

        display_socket_latency_ms = round(best_socket_lat if best_socket_lat is not None else socket_lat_ms, 2)
        ws_conn = any(a.client._connected for a in self.account_manager.accounts.values() if a.enabled) if (self.account_manager and self.account_manager.accounts) else self.client._connected

        test_data = {
            "tested_at": self.config.get_tr_now().strftime("%H:%M:%S"),
            "code": test_code,
            "server_latency_ms": display_socket_latency_ms,
            "total_latency_ms": display_socket_latency_ms,
            "captcha_solve_time_sec": captcha_solve_sec,
            "captcha_token_used": bool(captcha_tok),
            "accounts_count": len(formatted_accs),
            "accounts": formatted_accs,
            "ws_connected": ws_conn,
        }

        self._last_test_result = test_data
        return test_data

    async def handle_test_redeem(self, request: web.Request) -> web.Response:
        custom_code = request.query.get("code", "").strip() or None
        should_solve = request.query.get("solve", "").lower() in ("1", "true", "yes")
        await self.run_redeem_test(test_code=custom_code, solve_captcha=should_solve)
        raise web.HTTPFound("/sonuc")

    async def handle_test_redeem_api(self, request: web.Request) -> web.Response:
        try:
            data = await request.json() if request.can_read_body else {}
        except Exception:
            data = {}
        code = data.get("code", "").strip() or None
        result = await self.run_redeem_test(test_code=code)
        return web.json_response(result)

    async def handle_sonuc(self, request: web.Request) -> web.Response:
        return web.Response(text=SONUC_HTML_TEMPLATE, content_type="text/html")

    async def handle_sonuc_api(self, request: web.Request) -> web.Response:
        return web.json_response(self._last_test_result or {"status": "none"})

    async def handle_status(self, request: web.Request) -> web.Response:
        profile = None
        if self.account_manager:
            for aid in ("acc_default", "acc_1"):
                if aid in self.account_manager.accounts:
                    p = self.account_manager.accounts[aid].client._profile
                    if p and p.is_authenticated:
                        profile = p
                        break
            if not profile:
                for acc in self.account_manager.accounts.values():
                    p = acc.client._profile
                    if p and p.is_authenticated:
                        profile = p
                        break
        if not profile:
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
            if self.captcha_pool.nonecap_backup_api_key:
                active_solver = "NoneCap (Ana + Yedek Korumalı)"
            else:
                active_solver = "NoneCap (1300 Bedava Kredi)"
        elif self.captcha_pool.nonecap_backup_api_key:
            active_solver = "NoneCap Yedek (Aktif)"
        elif self.captcha_pool.capsolver_api_key:
            active_solver = "CapSolver (Otomatik)"
        elif self.captcha_pool.twocaptcha_api_key:
            active_solver = "2Captcha (Otomatik)"

        discord_info = {
            "connected": self.gateway_listener.is_connected if self.gateway_listener else False,
            "user": self.gateway_listener.username if self.gateway_listener else "",
            "channel_id": str(self.config.discord_channel_id),
        }

        live_logs = get_recent_logs(limit=100)
        in_sched = self.config.is_in_schedule()

        is_any_authenticated = bool(profile and profile.is_authenticated)
        if not is_any_authenticated and self.account_manager:
            is_any_authenticated = any(a.client._profile and a.client._profile.is_authenticated for a in self.account_manager.accounts.values())

        return web.json_response({
            "authenticated": is_any_authenticated,
            "account": {
                "username": profile.username if profile else "",
                "balance_dl": profile.balance_dl if profile else 0,
                "level": profile.level if profile else 1,
            },
            "metrics": self.metrics.summary(),
            "stats": stats,
            "captcha": {
                "valid": self.captcha_pool.is_token_valid,
                "remaining": self.captcha_pool.remaining_seconds,
                "valid_count": self.captcha_pool.valid_token_count,
                "target_pool_size": self.captcha_pool.target_pool_size,
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
            "nonecap_backup_api_key": self.config.nonecap_backup_api_key,
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
        nonecap_backup_key = data.get("nonecap_backup_api_key", "").strip()
        capsolver_key = data.get("capsolver_api_key", "").strip()
        raw_cookies = data.get("raw_cookies")
        if raw_cookies is not None:
            self.config.raw_cookies = raw_cookies.strip()
        else:
            raw_cookies = self.config.raw_cookies
        sched_enabled = bool(data.get("schedule_enabled", True))
        sched_start = data.get("schedule_start", "20:25").strip()
        sched_end = data.get("schedule_end", "21:00").strip()


        # Update in-memory config
        self.config.discord_token = token
        self.config.discord_channel_id = int(channel_id or 0)
        self.config.discord_guild_id = int(guild_id or 0)
        self.config.nonecap_api_key = nonecap_key
        self.config.nonecap_backup_api_key = nonecap_backup_key
        self.config.capsolver_api_key = capsolver_key
        self.config.schedule_enabled = sched_enabled
        self.config.schedule_start = sched_start
        self.config.schedule_end = sched_end

        # Update captcha pool keys
        self.captcha_pool.nonecap_api_key = nonecap_key
        self.captcha_pool.nonecap_backup_api_key = nonecap_backup_key
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
NONECAP_BACKUP_API_KEY={nonecap_backup_key}
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

    async def handle_warmup(self, request: web.Request) -> web.Response:
        try:
            data = await request.json() if request.can_read_body else {}
        except Exception:
            data = {}
        count = int(data.get("count", 7) or 7)
        count = max(1, min(10, count))
        total = await self.captcha_pool.warm_up_pool(count=count)
        return web.json_response({
            "status": "ready",
            "valid_tokens": total,
            "message": f"Havuzda {total} adet sıcak token hazır bekliyor (0ms gecikme)."
        })

    async def handle_manual_redeem(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            raw_input = str(data.get("code", "")).strip()
            captcha_override = str(data.get("captcha", "")).strip()

            token = captcha_override or await self.captcha_pool.get_token()

            # Check if user pasted a multi-level drop message!
            level_codes = CodeParser.extract_level_codes(raw_input)
            if level_codes and self.account_manager and len(self.account_manager.accounts) > 0:
                results = await self.account_manager.redeem_drop(level_codes, captcha_pool=self.captcha_pool)
                summary_msgs = []
                best_status = "SUCCESS"
                for r_item in results:
                    acc_n = r_item.get("account_name", "Hesap")
                    c = r_item.get("code")
                    lvl = r_item.get("req_level")
                    res = r_item.get("result")
                    if res:
                        summary_msgs.append(f"[{acc_n}] Lvl {lvl}+ ({c}): {res.status.value} - {res.message}")
                        await self.db.update_redeem_result(res)
                        self.metrics.record_redeem(res)

                return web.json_response({
                    "code": f"MULTI-LEVEL DROP ({len(level_codes)} kod)",
                    "status": best_status,
                    "message": " | ".join(summary_msgs) if summary_msgs else "Hesaplar dropu işledi.",
                    "latency_ms": 0.0,
                    "response_data": {"drop_results": len(results)},
                })

            code = raw_input.upper()
            latency = RedeemLatency(t0_discord_received=time.time())

            if self.account_manager and len(self.account_manager.accounts) > 0:
                multi_results = await self.account_manager.redeem_all(code, captcha_token=token)
                result = None
                for res_entry in multi_results:
                    r = res_entry.get("result")
                    if r:
                        await self.db.update_redeem_result(r)
                        self.metrics.record_redeem(r)
                        if r.status == RedeemStatus.SUCCESS:
                            result = r
                if not result and multi_results:
                    result = multi_results[0].get("result")
                if not result:
                    result = await self.client.redeem_code(code, latency=latency, captcha_token=token)
            else:
                result = await self.client.redeem_code(code, latency=latency, captcha_token=token)
                await self.db.update_redeem_result(result)
                self.metrics.record_redeem(result)

            if not captcha_override and token:
                self.captcha_pool.invalidate()

            lat_ms = result.latency.http_request_ms if result.latency else 0.0
            return web.json_response({
                "code": result.code,
                "status": result.status.value,
                "message": result.message,
                "latency_ms": lat_ms,
                "response_data": result.response_data,
            })
        except Exception as e:
            return web.json_response({
                "code": locals().get("code", "ERROR"),
                "status": "ERROR",
                "message": f"Redeem işlemi sırasında hata oluştu: {e}",
                "latency_ms": 0.0,
                "response_data": {"error": str(e)}
            }, status=200)

    async def handle_inject_captcha(self, request: web.Request) -> web.Response:
        data = await request.json()
        token = str(data.get("token", "")).strip()
        if token:
            self.captcha_pool.set_token(token)
            return web.json_response({"status": "injected"})
        return web.json_response({"error": "Empty token"}, status=400)

    async def _latency_ping_loop(self):
        """
        Runs automatically every 10 minutes to measure pure WebSocket RTT latency.
        Completely free of captchas (0 credits used), updating the Performance card on the UI.
        """
        # Wait 10 seconds initially for WS connection to stabilize
        await asyncio.sleep(10)
        while True:
            try:
                if self.client and "gamblit" in self.config.gamblit_base_url:
                    lat_ms = await self.client.measure_ws_latency()
                    if lat_ms > 0 and self.metrics:
                        self.metrics.record_latency(lat_ms)
                        log.info(f"⏱️ [10dk Otomatik Soket Ölçümü] WebSocket gecikmesi güncellendi: {lat_ms:.1f} ms (0 Kredi)")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug(f"Otomatik ping ölçüm hatası: {e}")
            
            # Wait 10 minutes (600 seconds)
            await asyncio.sleep(600)

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
                if not self._latency_ping_task or self._latency_ping_task.done():
                    self._latency_ping_task = asyncio.create_task(self._latency_ping_loop(), name="LatencyPingLoop")
                return
            except OSError as e:
                # WinError 10048 (Windows) or 98 (Linux): Port already in use
                if getattr(e, "winerror", None) == 10048 or getattr(e, "errno", None) in (10048, 98):
                    continue
                raise
        raise OSError(f"Port 5050-5055 arası tüm portlar meşgul!")

    async def stop(self):
        if self._latency_ping_task:
            self._latency_ping_task.cancel()
            self._latency_ping_task = None
        if self.runner:
            await self.runner.cleanup()
