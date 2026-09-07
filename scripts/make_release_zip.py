"""
One-click Release Packager for Gamblit Auto-Redeemer Pro.
Creates a clean, production-ready ZIP file ready to send to clients/buyers.
Excludes personal cookies (.env), virtualenv (.venv), and cache files.
"""
import os
import zipfile
from pathlib import Path

def create_release():
    root_dir = Path(__file__).resolve().parent.parent
    zip_filename = root_dir / "Gamblit_AutoRedeemer_Pro.zip"

    # Files & Folders to include
    include_files = [
        "BASLAT.bat",
        "START.bat",
        "KULLANIM_KILAVUZU.txt",
        "main.py",
        "requirements.txt",
        ".env.example",
        "Dockerfile",
        "docker-compose.yml",
        "gamblit-redeemer.service",
    ]

    include_dirs = [
        "app",
    ]

    exclude_extensions = {".pyc", ".pyo", ".pyd"}
    exclude_dirs = {"__pycache__", ".pytest_cache", ".venv", "tests", "scripts"}

    print(f"[*] Packaging clean release to: {zip_filename.name}...")
    with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add top-level files
        for fname in include_files:
            fpath = root_dir / fname
            if fpath.exists():
                zf.write(fpath, arcname=fname)
                print(f"  + Added: {fname}")

        # 2. Add app package
        for dname in include_dirs:
            dpath = root_dir / dname
            for dirpath, dirnames, filenames in os.walk(dpath):
                # Remove excluded dirs in-place
                dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                for f in filenames:
                    if any(f.endswith(ext) for ext in exclude_extensions):
                        continue
                    file_full_path = Path(dirpath) / f
                    arcname = file_full_path.relative_to(root_dir)
                    zf.write(file_full_path, arcname=str(arcname))
                    print(f"  + Added: {arcname}")

        # 3. Add empty data and logs directories
        zf.writestr("data/.gitkeep", "")
        zf.writestr("logs/.gitkeep", "")
        # Include clean .env template as .env default
        env_ex = (root_dir / ".env.example").read_text(encoding="utf-8")
        zf.writestr(".env", env_ex)
        print("  + Added: data/, logs/, .env (clean template)")

    size_mb = os.path.getsize(zip_filename) / (1024 * 1024)
    print(f"\n[OK] PAKET HAZIR! Dosya Boyutu: {size_mb:.2f} MB")
    print(f"Müşteriye direkt gönderebileceğin dosya: {zip_filename}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--copy-auth":
        import subprocess
        js = "fetch('http://localhost:5050/api/auth/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cookies:document.cookie})}).then(r=>r.json()).then(d=>alert(d.status==='ok'?'Giris Basarili: '+d.username:'Hata: '+d.error)).catch(e=>alert('Hata: '+e));"
        p = subprocess.Popen('clip', stdin=subprocess.PIPE, shell=True)
        p.communicate(input=js.encode('utf-8'))
        print("CLIP_COPIED")
    elif len(sys.argv) > 1 and sys.argv[1] == "--copy-token":
        import subprocess
        js = "(() => { const send = (t) => { if (!t) return; fetch('http://localhost:5050/api/captcha', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token: t}) }).then(() => { alert('Token Bota Aktarildi! Havuz Doldu.'); }).catch(e => alert('Hata: ' + e)); }; for (let i = 0; i < 5; i++) { try { const ex = hcaptcha.getResponse(i); if (ex) { send(ex); return; } } catch(e) {} } for (let i = 0; i < 5; i++) { try { hcaptcha.execute(i, { async: true }).then(res => { const t = (typeof res === 'object' && res ? res.response : res) || hcaptcha.getResponse(i); send(t); }); break; } catch(e) {} } })();"
        p = subprocess.Popen('clip', stdin=subprocess.PIPE, shell=True)
        p.communicate(input=js.encode('utf-8'))
        print("TOKEN_SNIPPET_COPIED")
    else:
        create_release()
