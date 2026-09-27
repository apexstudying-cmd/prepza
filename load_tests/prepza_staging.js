import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep } from 'k6';

const BASE = (__ENV.BASE_URL || '').replace(/\/$/, '');
const COOKIE = __ENV.AUTH_COOKIE || '';
const CONVERSATION_ID = Number(__ENV.CONVERSATION_ID || 0);
const WS_SECONDS = Number(__ENV.WS_SECONDS || 30);

export const options = {
  scenarios: {
    http_burst: {
      executor: 'constant-vus',
      vus: Number(__ENV.HTTP_VUS || 25),
      duration: __ENV.HTTP_DURATION || '30s',
      exec: 'httpFlow',
    },
    realtime: {
      executor: 'constant-vus',
      vus: Number(__ENV.WS_VUS || 25),
      duration: __ENV.WS_DURATION || '30s',
      exec: 'socketFlow',
      startTime: '2s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<1500'],
    checks: ['rate>0.98'],
  },
};

function headers() {
  const h = {};
  if (COOKIE) h.Cookie = COOKIE;
  return h;
}

export function httpFlow() {
  const responses = http.batch([
    ['GET', `${BASE}/health`, null, { headers: headers(), tags: { flow: 'health' } }],
    ['GET', `${BASE}/chats`, null, { headers: headers(), tags: { flow: 'chat-list' } }],
    ['GET', `${BASE}/me`, null, { headers: headers(), tags: { flow: 'session' } }],
  ]);
  check(responses[0], { 'health 200': (r) => r.status === 200 });
  if (COOKIE) {
    check(responses[1], { 'chat list authenticated': (r) => [200, 304].includes(r.status) });
    check(responses[2], { 'session authenticated': (r) => [200, 304].includes(r.status) });
  }
  sleep(0.2);
}

export function socketFlow() {
  if (!COOKIE || !CONVERSATION_ID) return;
  const scheme = BASE.startsWith('https://') ? 'wss://' : 'ws://';
  const host = BASE.replace(/^https?:\/\//, '');
  const url = `${scheme}${host}/socket.io/?EIO=4&transport=websocket`;
  const params = { headers: { Cookie: COOKIE }, tags: { flow: 'socketio' } };

  const res = ws.connect(url, params, function (socket) {
    let joined = false;
    socket.on('open', function () {
      socket.send('40');
    });
    socket.on('message', function (data) {
      if (data === '2') {
        socket.send('3');
        return;
      }
      if (data.startsWith('40')) {
        socket.send(`42["join_chat",{"conversation_id":${CONVERSATION_ID}}]`);
        joined = true;
      }
      if (joined && data.startsWith('42')) {
        // Keep the connection alive without mutating chat state.
      }
    });
    socket.setTimeout(function () {
      socket.close();
    }, WS_SECONDS * 1000);
  });

  check(res, { 'Socket.IO websocket handshake': (r) => r && r.status === 101 });
}
