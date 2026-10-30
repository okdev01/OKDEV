// Execute the real worker class with an in-memory Durable Object runtime.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');
let now = 1700000000000;
class Socket {
  static READY_STATE_OPEN = 1;
  readyState = 1;
  sent = [];
  attachment = null;
  serializeAttachment(value) { this.attachment = structuredClone(value); }
  deserializeAttachment() { return structuredClone(this.attachment); }
  send(value) { this.sent.push(JSON.parse(value)); }
  close(code, reason) { this.readyState = 3; this.reason = reason; }
}
const code = stripTypeScriptTypes(fs.readFileSync(path.join(__dirname, '../relay-worker/src/room.ts'), 'utf8'))
  .replace(/import .*?from 'cloudflare:workers';/, '')
  .replace('export class PartyRoom', 'class PartyRoom') + '\nglobalThis.PartyRoom = PartyRoom;';
const sandbox = {
  DurableObject: class { constructor(ctx) { this.ctx = ctx; } },
  WebSocket: Socket,
  WebSocketPair: class { constructor() { this[0] = new Socket(); this[1] = new Socket(); } },
  WebSocketRequestResponsePair: class {},
  Response: class { constructor(body, init) { this.body = body; Object.assign(this, init); } },
  Date: { now: () => now }, URL, console: { log() {} },
};
vm.runInNewContext(code, sandbox);
function fixture() {
  const sockets = [];
  const ctx = { id: { toString: () => 'fixture' }, setWebSocketAutoResponse() {},
    acceptWebSocket(ws) { sockets.push(ws); }, getWebSockets: () => sockets,
    getWebSocketAutoResponseTimestamp: ws => ws.ping };
  return { sockets, room: new sandbox.PartyRoom(ctx, {}) };
}
async function run() {
  const { room, sockets } = fixture();
  for (let id = 1; id <= 10; id++) {
    assert.equal((await room.fetch({ url: 'https://fixture.invalid/' })).status, 101);
    await room.webSocketMessage(sockets.at(-1), JSON.stringify({ type: 'join', summoner_id: id }));
  }
  const old = sockets[0];
  assert.equal((await room.fetch({ url: 'https://fixture.invalid/' })).status, 101);
  const replacement = sockets.at(-1);
  await room.webSocketMessage(replacement, JSON.stringify({ type: 'join', summoner_id: 1 }));
  assert.equal(old.reason, 'replaced');
  assert.equal(room.getMembers().length, 10);
  assert.equal(replacement.readyState, 1);
  await room.fetch({ url: 'https://fixture.invalid/' });
  const newcomer = sockets.at(-1);
  await room.webSocketMessage(newcomer, JSON.stringify({ type: 'join', summoner_id: 11 }));
  assert.equal(newcomer.reason, 'room full');
  assert.equal(newcomer.sent.at(-1).code, 'ROOM_FULL');
  assert.equal(room.getMembers().length, 10);

  const pending = fixture();
  await pending.room.fetch({ url: 'https://fixture.invalid/' });
  await pending.room.fetch({ url: 'https://fixture.invalid/' });
  assert.equal((await pending.room.fetch({ url: 'https://fixture.invalid/' })).status, 429);
  now += 16000;
  // Pinging cannot extend the deadline before a valid join.
  pending.sockets[0].ping = { getTime: () => now };
  assert.equal((await pending.room.fetch({ url: 'https://fixture.invalid/' })).status, 101);
  assert.equal(pending.sockets[0].reason, 'stale');
  assert.equal(pending.sockets[1].reason, 'stale');
  await pending.room.webSocketMessage(pending.sockets.at(-1), 'null');
  await pending.room.webSocketMessage(pending.sockets.at(-1), '{"type":"join","summoner_id":0}');
  assert.equal(pending.sockets.at(-1).reason, 'invalid join');
  console.log('Relay worker: rejoin at capacity, member limit, pending limit, join expiry and malformed input PASS');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
