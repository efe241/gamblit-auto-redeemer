import asyncio
import base64
import msgpack
import websockets
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.config import cfg

async def test_flow():
    uri = "wss://ws.gamblit.net"
    cookies = cfg.parsed_cookies
    cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    
    headers = {
        "User-Agent": cfg.gamblit_user_agent,
        "Origin": "https://gamblit.net",
        "Cookie": cookie_header,
    }
    
    print("1. Connecting to wss://ws.gamblit.net...")
    async with websockets.connect(
        uri,
        additional_headers=headers,
        ping_interval=15,
        open_timeout=10,
    ) as ws:
        print("✅ Connected!")
        
        while True:
            raw = await ws.recv()
            if isinstance(raw, bytes):
                packet = msgpack.unpackb(raw, raw=False)
                p_id = packet.get("ID")
                print(f"<- Received: ID={p_id} | Data: {packet}")
                
                if p_id == "CHALLENGE":
                    print("2. Responding to CHALLENGE with PAT packet...")
                    pat_payload = {"token": "null"}
                    packed_pat = msgpack.packb(pat_payload)
                    b64_token = base64.b64encode(packed_pat).decode("utf-8")
                    
                    resp_packet = {"ID": "PAT", "token": b64_token}
                    await ws.send(msgpack.packb(resp_packet))
                    print("-> Sent PAT packet")
                    
                elif p_id == "PAT":
                    print("3. PAT accepted. Sending GetUserData...")
                    await ws.send(msgpack.packb({"ID": "GetUserData"}))
                    
                elif p_id == "UserData":
                    print("🎉 SUCCESS! Logged in as:", packet.get("username"))
                    print("   Balances:", packet.get("balances"))
                    print("   Level/XP:", packet.get("level"), packet.get("xp"))
                    
                    # Test ClaimPromoCode with empty string captcha and currency
                    print("\n4. Testing ClaimPromoCode with dummy code 'TEST_CODE_2026'...")
                    claim_packet = {"ID": "ClaimPromoCode", "code": "TEST_CODE_2026", "captcha": "", "currency": "wl"}
                    await ws.send(msgpack.packb(claim_packet))
                    
                elif p_id == "ClaimPromoCode":
                    print(f"🎯 ClaimPromoCode Server Response: {packet}")
                    break

if __name__ == "__main__":
    asyncio.run(test_flow())
