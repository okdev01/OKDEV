"""Check a deployed relay with two synthetic players, without starting League."""

import argparse
import asyncio
import json
import secrets
from urllib.parse import urlsplit

import websockets


async def wait_for_members(socket, predicate):
    async def receive():
        async for raw in socket:
            if raw == "pong":
                continue
            message = json.loads(raw)
            if message.get("type") == "members" and predicate(message["members"]):
                return message["members"]
        raise RuntimeError("Relay closed before the expected member update")

    return await asyncio.wait_for(receive(), timeout=10)


async def check(base_url):
    # A fresh room prevents the check from touching any real player's party.
    room = secrets.token_hex(16)
    url = f"{base_url.rstrip('/')}/room?key={room}&v=1.4.4&app=okdev&app_version=1.1.0"
    async with websockets.connect(url, open_timeout=10, max_size=65536) as first:
        await first.send(json.dumps({"type": "join", "summoner_id": 1, "summoner_name": "Relay test A"}))
        await wait_for_members(first, lambda members: len(members) == 1)
        async with websockets.connect(url, open_timeout=10, max_size=65536) as second:
            await second.send(json.dumps({"type": "join", "summoner_id": 2, "summoner_name": "Relay test B"}))
            for socket in (first, second):
                await wait_for_members(socket, lambda members: len(members) == 2)
            selections = {
                1: {"champion_id": 103, "skin_id": 103001, "rooms": [room], "sent_at": 1},
                2: {"champion_id": 99, "skin_id": 99001, "removed": [], "sent_at": 2},
            }
            for sid, socket in ((1, first), (2, second)):
                await socket.send(json.dumps({"type": "skin", "skin": selections[sid]}))
            for socket in (first, second):
                await wait_for_members(socket, lambda members: all(
                    any(m.get("summoner_id") == sid and m.get("skin") == skin for m in members)
                    for sid, skin in selections.items()
                ))
                await socket.send("ping")
                if await asyncio.wait_for(socket.recv(), timeout=10) != "pong":
                    raise RuntimeError("Expected literal pong reply")
            await second.send(json.dumps({"type": "leave"}))
            await wait_for_members(first, lambda members: [m["summoner_id"] for m in members] == [1])
    print("PASS: two players joined, both skins arrived unchanged, ping/pong and leave worked.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Relay base URL, e.g. wss://relay.example.com (no /room)")
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if (parsed.scheme not in ("ws", "wss") or not parsed.hostname
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        parser.error("Supply a ws:// or wss:// base URL without credentials, path or query")
    try:
        asyncio.run(check(args.url))
    except (OSError, RuntimeError, ValueError, asyncio.TimeoutError, websockets.WebSocketException) as error:
        parser.exit(1, f"FAIL: {error}\n")


if __name__ == "__main__":
    main()
