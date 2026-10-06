import asyncio
import json
import unittest
from unittest.mock import patch

import websockets

from scripts.check_party_relay import check


class RelayCheckTests(unittest.IsolatedAsyncioTestCase):
    async def run_check(self, pong="pong"):
        members = {}

        async def broadcast():
            payload = json.dumps({"type": "members", "members": list(members.values())})
            for socket in list(members):
                await socket.send(payload)

        async def handle(socket, path):
            try:
                async for raw in socket:
                    if raw == "ping":
                        await socket.send(pong)
                        continue
                    msg = json.loads(raw)
                    if msg["type"] == "join":
                        members[socket] = {"summoner_id": msg["summoner_id"], "summoner_name": msg["summoner_name"]}
                    elif msg["type"] == "skin":
                        members[socket]["skin"] = msg["skin"]
                    elif msg["type"] == "leave":
                        break
                    await broadcast()
            finally:
                members.pop(socket, None)
                for peer in list(members):
                    try:
                        await peer.send(json.dumps({"type": "members", "members": list(members.values())}))
                    except websockets.ConnectionClosed:
                        pass

        async with websockets.serve(handle, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            await asyncio.wait_for(check(f"ws://127.0.0.1:{port}"), timeout=15)

    async def test_bidirectional_check_passes(self):
        with patch("builtins.print") as output:
            await self.run_check()
        self.assertTrue(output.call_args.args[0].startswith("PASS:"))

    async def test_broken_keepalive_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "pong"):
            await self.run_check(pong="incorrect")
