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

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gamblit Auto-Redeemer Pro Paneli</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d1117;
            --card-bg: #161b22;
            --border: #30363d;
            --accent: #58a6ff;
            --green: #2ea043;
            --red: #f85149;
            --yellow: #d29922;
            --purple: #bc8cff;
            --text: #c9d1d9;
            --text-bright: #f0f6fc;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 24px;
            max-width: 1240px;
            margin: auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 12px;
        }
        h1 { font-size: 22px; color: var(--text-bright); display: flex; align-items: center; gap: 8px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 18px;
        }
        .card h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; margin-bottom: 12px; }
        .metric-val { font-size: 24px; font-weight: 700; color: var(--text-bright); }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-online { background: #23863622; color: #3fb950; border: 1px solid #238636; }
        .badge-offline { background: #da363322; color: #f85149; border: 1px solid #da3633; }
        .badge-purple { background: #bc8cff22; color: #bc8cff; border: 1px solid #bc8cff; }
        .badge-yellow { background: #d2992222; color: #d29922; border: 1px solid #d29922; }
        
        .progress-bar-container {
            width: 100%;
            height: 8px;
            background: #21262d;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
            margin-bottom: 14px;
        }
        .progress-bar {
            height: 100%;
            background: #2ea043;
            width: 0%;
            transition: width 0.5s linear, background-color 0.3s;
        }

        .form-group { margin-bottom: 14px; }
        label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 6px; color: #8b949e; }
        input, textarea {
            width: 100%;
            background: #0d1117;
            border: 1px solid var(--border);
            color: var(--text-bright);
            padding: 10px 12px;
            border-radius: 6px;
            font-size: 13px;
            font-family: 'JetBrains Mono', monospace;
        }
        input:focus, textarea:focus { outline: none; border-color: var(--accent); }
        button {
            background: #238636;
            color: white;
            border: none;
            padding: 10px 16px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            font-size: 13px;
            transition: opacity 0.2s;
        }
        button:hover { opacity: 0.9; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        button.btn-alt { background: #21262d; border: 1px solid var(--border); color: var(--text); }
        button.btn-alt:hover { background: #30363d; }
        button.btn-accent { background: #1f6feb; }
        button.btn-accent:hover { background: #388bfd; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 8px; }
        th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px; }
        th { color: #8b949e; font-size: 11px; text-transform: uppercase; }
        .code-cell { font-family: 'JetBrains Mono', monospace; font-weight: 600; color: var(--accent); }
        
        details summary {
            cursor: pointer;
            color: var(--accent);
            font-size: 13px;
            font-weight: 600;
            user-select: none;
            margin-top: 8px;
        }
        pre.code-box {
            background: #0d1117;
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px;
            font-size: 12px;
            font-family: 'JetBrains Mono', monospace;
            color: #7ee787;
            overflow-x: auto;
            margin-top: 8px;
            white-space: pre-wrap;
        }

        #toast {
            position: fixed; bottom: 20px; right: 20px;
            background: #1f6feb; color: white; padding: 12px 20px;
            border-radius: 6px; font-weight: 600; font-size: 13px;
            display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            z-index: 9999;
        }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>⚡ Gamblit Auto-Redeemer Pro</h1>
            <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">Ultra-Düşük Gecikmeli Kod Yakalayıcı & Otomatik hCaptcha Çözücü</div>
        </div>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
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
            <h2>💳 Çözücü Bakiyeleri</h2>
            <div style="font-size: 14px; margin-top: 6px;">
                CapSolver: <strong id="bal-capsolver" style="color: #7ee787;">--</strong> &bull;
                2Captcha: <strong id="bal-twocaptcha" style="color: #7ee787;">--</strong>
            </div>
            <div style="font-size: 12px; color: #8b949e; margin-top: 8px;">
                Otomatik havuz döngüsü: <strong id="loop-status" style="color: #d29922;">Pasif (API Anahtarı Yok)</strong>
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
                <span style="font-size: 12px; font-family: monospace;" id="captcha-timer-text">0 / 100 sn</span>
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

    <!-- Live Codes Table -->
    <div class="card" style="margin-bottom: 24px;">
        <h2>📜 Son İşlenen Kodlar & Sonuçları</h2>
        <table>
            <thead>
                <tr>
                    <th>Kod</th>
                    <th>Durum</th>
                    <th>Mesaj</th>
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
                    <label>DISCORD BOT TOKEN</label>
                    <input type="password" id="cfg-token" placeholder="Bot tokenini gir">
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
                    <label>CAPSOLVER API KEY (Otomatik Çözüm)</label>
                    <input type="password" id="cfg-capsolver" placeholder="CapSolver API anahtarın">
                </div>
                <div class="form-group">
                    <label>2CAPTCHA API KEY (Yedek Çözüm)</label>
                    <input type="password" id="cfg-twocaptcha" placeholder="2Captcha API anahtarın">
                </div>
            </div>
            <div class="form-group">
                <label>GAMBLIT ÇEREZLERİ (Cookie Header)</label>
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

                // Solver Badge & Balances
                const sBadge = document.getElementById('solver-badge');
                sBadge.innerText = 'Çözücü: ' + data.captcha.active_solver;
                if (data.captcha.active_solver.includes('CapSolver') || data.captcha.active_solver.includes('2Captcha')) {
                    sBadge.className = 'badge badge-online';
                    document.getElementById('loop-status').innerText = 'Aktif (Arkaplanda Sürekli Token Taze Tutulur)';
                    document.getElementById('loop-status').style.color = '#3fb950';
                } else {
                    sBadge.className = 'badge badge-purple';
                    document.getElementById('loop-status').innerText = 'Pasif (API Anahtarı Tanımlı Değil)';
                    document.getElementById('loop-status').style.color = '#d29922';
                }

                const bal = data.captcha.balances || {};
                document.getElementById('bal-capsolver').innerText = bal.capsolver !== null ? '$' + bal.capsolver : 'Bağlı Değil';
                document.getElementById('bal-twocaptcha').innerText = bal.twocaptcha !== null ? '$' + bal.twocaptcha : 'Bağlı Değil';

                // Account
                document.getElementById('acc-name').innerText = data.account.username || 'Giriş Yapılmadı';
                document.getElementById('acc-balance').innerText = data.account.balance_dl || 0;
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
                    const pct = Math.min(100, Math.round((rem / 100.0) * 100));
                    pBar.style.width = pct + '%';
                    pBar.style.backgroundColor = rem < 20 ? '#d29922' : '#2ea043';
                    tText.innerText = Math.round(rem) + ' / 100 sn';
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
                            accHtml += `<tr>
                                <td><strong>${a.name}</strong></td>
                                <td style="font-family: monospace;">${a.username || '--'}</td>
                                <td>${statusBadge}</td>
                                <td><strong style="color: #3fb950;">${a.balance_dl || 0}</strong> DL</td>
                                <td>Level ${a.level || 1}</td>
                                <td style="display: flex; gap: 6px;">
                                    ${toggleBtn}
                                    <button class="btn-alt" type="button" style="padding: 4px 8px; font-size: 11px; color: #f85149;" onclick="removeAccount('${a.id}')">🗑️ Sil</button>
                                </td>
                            </tr>`;
                        }
                    }
                    document.getElementById('accounts-tbody').innerHTML = accHtml;
                }
            } catch(e) {}
        }

        async function loadConfig() {
            try {
                const res = await fetch('/api/config');
                const data = await res.json();
                document.getElementById('cfg-token').value = data.discord_token || '';
                document.getElementById('cfg-channel').value = data.discord_channel_id || '';
                document.getElementById('cfg-guild').value = data.discord_guild_id || '';
                document.getElementById('cfg-capsolver').value = data.capsolver_api_key || '';
                document.getElementById('cfg-twocaptcha').value = data.twocaptcha_api_key || '';
                document.getElementById('cfg-cookies').value = data.raw_cookies || '';
            } catch(e) {}
        }

        document.getElementById('settings-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const body = {
                discord_token: document.getElementById('cfg-token').value,
                discord_channel_id: document.getElementById('cfg-channel').value,
                discord_guild_id: document.getElementById('cfg-guild').value,
                capsolver_api_key: document.getElementById('cfg-capsolver').value,
                twocaptcha_api_key: document.getElementById('cfg-twocaptcha').value,
                raw_cookies: document.getElementById('cfg-cookies').value
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

        function copySnippet() {
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
                if (res.ok) {
                    showToast('✅ Yeni hesap başarıyla eklendi ve bağlandı!');
                    document.getElementById('new-acc-name').value = '';
                    document.getElementById('new-acc-cookies').value = '';
                    toggleAddAccountModal();
                    refreshData();
                } else {
                    const err = await res.json();
                    showToast('Hata: ' + (err.error || 'Eklenemedi'), true);
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
        self.app.router.add_post("/api/captcha/solve", self.handle_solve_now)
        self.app.router.add_get("/api/accounts", self.handle_get_accounts)
        self.app.router.add_post("/api/accounts", self.handle_add_account)
        self.app.router.add_delete("/api/accounts/{id}", self.handle_remove_account)
        self.app.router.add_post("/api/accounts/{id}/toggle", self.handle_toggle_account)

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
        return web.json_response({"status": "added", "account": acc.to_dict()})

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
                    "SELECT code, status, latency_ms, processed_at, received_at FROM codes ORDER BY id DESC LIMIT 10"
                )
                rows = await cursor.fetchall()
                recent = [dict(r) for r in rows]
        except Exception:
            pass

        active_solver = "Manuel Mod"
        if self.captcha_pool.capsolver_api_key:
            active_solver = "CapSolver (Otomatik)"
        elif self.captcha_pool.twocaptcha_api_key:
            active_solver = "2Captcha (Otomatik)"

        discord_info = {
            "connected": self.gateway_listener.is_connected if self.gateway_listener else False,
            "user": self.gateway_listener.username if self.gateway_listener else "",
            "channel_id": str(self.config.discord_channel_id),
        }

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
            "discord": discord_info,
            "recent_codes": recent,
            "accounts": self.account_manager.get_summary() if self.account_manager else None,
        })

    async def handle_get_config(self, request: web.Request) -> web.Response:
        return web.json_response({
            "discord_token": self.config.discord_token,
            "discord_channel_id": str(self.config.discord_channel_id),
            "discord_guild_id": str(self.config.discord_guild_id),
            "capsolver_api_key": self.config.capsolver_api_key,
            "twocaptcha_api_key": self.config.twocaptcha_api_key,
            "raw_cookies": self.config.raw_cookies,
        })

    async def handle_save_config(self, request: web.Request) -> web.Response:
        data = await request.json()
        token = data.get("discord_token", "").strip()
        channel_id = data.get("discord_channel_id", "0").strip()
        guild_id = data.get("discord_guild_id", "0").strip()
        capsolver_key = data.get("capsolver_api_key", "").strip()
        twocaptcha_key = data.get("twocaptcha_api_key", "").strip()
        raw_cookies = data.get("raw_cookies", "").strip()

        # Update in-memory config
        self.config.discord_token = token
        self.config.discord_channel_id = int(channel_id or 0)
        self.config.discord_guild_id = int(guild_id or 0)
        self.config.capsolver_api_key = capsolver_key
        self.config.twocaptcha_api_key = twocaptcha_key
        self.config.raw_cookies = raw_cookies

        # Update captcha pool keys
        self.captcha_pool.capsolver_api_key = capsolver_key
        self.captcha_pool.twocaptcha_api_key = twocaptcha_key

        # Save to .env
        env_content = f"""# Gamblit Promo Code Auto-Redeemer Configuration
DISCORD_TOKEN={token}
DISCORD_GUILD_ID={guild_id or 0}
DISCORD_CHANNEL_ID={channel_id or 0}

GAMBLIT_BASE_URL={self.config.gamblit_base_url}
GAMBLIT_COOKIES={raw_cookies}
GAMBLIT_USER_AGENT={self.config.gamblit_user_agent}

CAPSOLVER_API_KEY={capsolver_key}
TWOCAPTCHA_API_KEY={twocaptcha_key}

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
        if capsolver_key or twocaptcha_key:
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
