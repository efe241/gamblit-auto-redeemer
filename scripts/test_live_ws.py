"""
Test connecting to Gamblit's real WebSocket server (wss://ws.gamblit.net)
using the user's Cloudflare session cookies and MessagePack protocol.
"""
import asyncio
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

async def test_ws_connection():
    uri = "wss://ws.gamblit.net"
    cookies = cfg.parsed_cookies
    cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    
    headers = {
        "User-Agent": cfg.gamblit_user_agent,
        "Origin": "https://gamblit.net",
        "Cookie": cookie_header,
    }
    
    print(f"Connecting to {uri} with {len(cookies)} cookies...")
    try:
        async with websockets.connect(
            uri,
            additional_headers=headers,
            open_timeout=10.0,
            close_timeout=5.0,
            ping_interval=20,
        ) as ws:
            print("✅ WebSocket connection ESTABLISHED!")
            
            # Listen for initial packets (UserData, Info, etc.)
            for _ in range(5):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    if isinstance(msg, bytes):
                        unpacked = msgpack.unpackb(msg, raw=False)
                        packet_id = unpacked.get("ID")
                        print(f"Received Packet: ID={packet_id}")
                        if packet_id == "UserData":
                            print(f"🎉 USER AUTHENTICATED! Username: {unpacked.get('username')}, ID: {unpacked.get('id')}")
                            print(f"   Balances: {unpacked.get('balances')}")
                            return True
                    else:
                        print("Received text frame:", msg)
                except asyncio.TimeoutError:
                    print("Waiting timed out for packet.")
                    break
                    
    except Exception as e:
        print(f"❌ WebSocket connection error: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_ws_connection())
