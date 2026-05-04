"""
End-to-end test: Server A verify -> JWT -> Server B WebSocket -> Anthropic response
"""
import asyncio
import json
import ssl
import httpx
import websockets

SERVER_A = "https://shopware.shopware-66108.orb.local"
SERVER_B_WS = "ws://localhost:8000"
SERVER_B_HTTP = "http://localhost:8000"

# Test user — use a real name/email from your Shopware DB or any name if strict validation is off
TEST_NAME = "Test User"
TEST_EMAIL = "test@example.com"


async def step1_get_jwt() -> str:
    print("\n=== STEP 1: Get JWT from Server A ===")
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(
            f"{SERVER_A}/voltimax/verify",
            json={"name": TEST_NAME, "email": TEST_EMAIL},
            timeout=10,
        )
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        print(f"  Response: {json.dumps(data, indent=2)}")

        if "token" not in data:
            raise RuntimeError(f"No token in response: {data}")

        print(f"  ✓ JWT issued")
        return data["token"]


async def step2_websocket_chat(token: str):
    print("\n=== STEP 2: Connect to Server B WebSocket ===")

    uri = f"{SERVER_B_WS}/ws/chat"
    print(f"  Connecting to {uri}...")

    async with websockets.connect(uri) as ws:
        print("  ✓ WebSocket connected")

        # Auth
        print("\n--- Auth ---")
        await ws.send(json.dumps({"type": "auth", "token": token}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        print(f"  Received: {json.dumps(msg, indent=2)}")

        if msg.get("type") != "auth_success":
            raise RuntimeError(f"Expected auth_success, got: {msg}")
        print(f"  ✓ Auth success. Topics: {[t['id'] for t in msg.get('topics', [])]}")

        # Select topic
        print("\n--- Select Topic ---")
        await ws.send(json.dumps({"type": "select_topic", "topic_id": "product_help"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        print(f"  Received: {msg.get('type')} — {msg.get('content', '')}")

        # Send a message
        print("\n--- Send Message ---")
        await ws.send(json.dumps({"type": "message", "content": "Hello! What products do you sell?"}))
        print("  Message sent. Waiting for response stream...")

        # Collect streamed response
        full_response = ""
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "typing":
                print("  [typing...]")
            elif mtype == "stream_start":
                print("  [stream started]")
            elif mtype == "stream_chunk":
                chunk = msg.get("content", "")
                full_response += chunk
                print(chunk, end="", flush=True)
            elif mtype == "stream_end":
                print("\n  [stream ended]")
                break
            elif mtype == "message":
                full_response = msg.get("content", "")
                print(f"  Full message: {full_response}")
                break
            elif mtype == "escalation":
                print(f"  [escalation triggered]: {msg.get('message')}")
                break
            elif mtype == "error":
                print(f"  [error]: {msg.get('message')}")
                break

        print(f"\n  ✓ AI Response received ({len(full_response)} chars)")
        print(f"\n  Response preview: {full_response[:200]}...")


async def main():
    print("=" * 60)
    print("  VoltimaxChat End-to-End Test")
    print("=" * 60)

    try:
        token = await step1_get_jwt()
        await step2_websocket_chat(token)
        print("\n" + "=" * 60)
        print("  ✓ ALL STEPS PASSED")
        print("=" * 60)
    except Exception as e:
        print(f"\n  ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
