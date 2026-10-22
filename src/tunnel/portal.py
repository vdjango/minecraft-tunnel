"""Public status and an authenticated, CSRF-protected operator console."""
import asyncio
import base64
from collections import OrderedDict, deque
import hashlib
import hmac
import html
import ipaddress
import json
import os
from pathlib import Path
import secrets
import tempfile
import time

from aiohttp import web

from .federation import identity
from .bandwidth import Bandwidth


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('密码需要 12–256 个字符')
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest


def verify_password(password, encoded):
    try:
        return hmac.compare_digest(password_hash(password, encoded.split(':')[0]), encoded)
    except (ValueError, TypeError, AttributeError):
        return False


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.node-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as target:
            json.dump(value, target, ensure_ascii=False, indent=2)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        # State files can contain administrator hashes, SMTP credentials, or
        # encrypted account material. Keep them private on Unix hosts.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Portal:
    def __init__(self, relay, federation, state_path):
        self.relay, self.federation = relay, federation
        self.path = Path(state_path)
        self.state = json.loads(self.path.read_text(encoding='utf-8'))
        self.started = time.monotonic()
        self.sessions = {}
        self.attempts = OrderedDict()
        self.login_lock = asyncio.Semaphore(2)
        self.node_action_lock = asyncio.Lock()
        self.runner = None
        self.federation.on_change = self.save
        self.relay.draining = self.state.get('draining', False)
        self.relay.capacity.configure(self.state.get('capacity', self.relay.capacity.policy))
        self.app = web.Application(client_max_size=8192, middlewares=[self.guard])
        self.bandwidth = Bandwidth()
        self.app.cleanup_ctx.append(self.bandwidth.lifecycle)
        self.app.add_routes([
            web.get('/', self.page), web.get('/admin', self.admin_page),
            web.get('/admin/{section:nodes|network|settings|users|history|mail}', self.admin_page),
            web.get('/developers', self.developers_page), web.get('/portal.css', self.asset),
            web.get('/console.css', self.asset), web.get('/developers.css', self.asset),
            web.get('/launcher-example.py', self.launcher_example),
            web.get('/protocol.md', self.protocol_document),
            web.get('/portal.js', self.asset), web.get('/admin.js', self.asset),
            web.get('/accounts.js', self.asset), web.get('/api/status', self.status),
            web.post('/api/login', self.login), web.post('/api/logout', self.logout),
            web.get('/api/admin', self.admin), web.post('/api/settings', self.settings),
            web.get('/api/federation/invite', self.invite),
            web.post('/api/federation/join', self.join),
            web.post('/api/federation/leave', self.leave),
            web.post('/api/federation/block', self.block),
            web.post('/api/profile', self.profile),
        ])
        from .accounts_web import AccountAPI
        self.account_api = AccountAPI(self)
        self.app.add_routes(self.account_api.routes)

    def save(self):
        self.state.update(name=self.federation.name, network_key=self.federation.network_key,
                          seeds=list(self.federation.seeds.values()), blocked=sorted(self.federation.blocked))
        atomic_json(self.path, self.state)

    @web.middleware
    async def guard(self, request, handler):
        # No forwarded headers are trusted. TLS terminates here or use an SSH
        # tunnel to loopback for administration.
        protected = request.path.startswith('/api/') and request.path != '/api/status'
        if protected and not request.secure and request.remote not in ('127.0.0.1', '::1'):
            raise web.HTTPForbidden(text='请使用 HTTPS 或 SSH 本地转发访问管理和授权功能。')
        try:
            if request.method == 'POST':
                origin = request.headers.get('Origin')
                if origin and origin != request.scheme + '://' + request.host:
                    raise web.HTTPForbidden(text='Origin rejected')
                if request.content_type != 'application/json':
                    raise web.HTTPUnsupportedMediaType()
                if not isinstance(await request.json(), dict):
                    raise ValueError('Expected an object')
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            response = web.json_response({'error': '输入无效，请检查后重试。'}, status=400)
        response.headers.update({
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; "
                                       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        if request.secure:
            response.headers['Strict-Transport-Security'] = 'max-age=86400'
        if isinstance(response, web.HTTPException):
            raise response
        return response

    async def page(self, request):
        return web.FileResponse(Path(__file__).with_name('web') / 'index.html')

    async def admin_page(self, request):
        section = request.match_info.get('section', 'nodes')
        selected = {'network': 'network-settings'}.get(section, section)
        page = (Path(__file__).with_name('web') / 'admin.html').read_text(encoding='utf-8')
        for name in ('nodes', 'network-settings', 'settings', 'users', 'history', 'mail'):
            if name != selected:
                page = page.replace('class="console-card" id="' + name + '"', 'class="console-card" hidden id="' + name + '"')
        return web.Response(text=page, content_type='text/html')

    async def developers_page(self, request):
        page = (Path(__file__).with_name('web') / 'developers.html').read_text(encoding='utf-8')
        from .runtime import protocol_path
        protocol = protocol_path().read_text(encoding='utf-8')
        return web.Response(text=page.replace('{{PROTOCOL}}', html.escape(protocol)), content_type='text/html')

    async def launcher_example(self, request):
        raise web.HTTPFound('/developers#examples')

    async def protocol_document(self, request):
        raise web.HTTPFound('/developers#protocol')

    async def asset(self, request):
        return web.FileResponse(Path(__file__).with_name('web') / request.path.lstrip('/'))

    def public_state(self):
        live = self.federation.live()
        return {'name': self.federation.name, 'id': self.federation.id,
                'status': 'maintenance' if self.relay.draining else 'online',
                'uptime_seconds': int(time.monotonic() - self.started),
                'rooms': len(self.relay.rooms), 'connections': len(self.relay.peers),
                'players': sum(self.relay.capacity.members(k) for k in self.relay.rooms),
                'game_players': sum(r.game_players or 0 for r in self.relay.rooms.values()
                                    if r.available and time.monotonic() - r.game_reported < 15),
                'game_counts_unknown': sum(r.game_players is None or time.monotonic() - r.game_reported >= 15
                                           for r in self.relay.rooms.values() if r.available),
                'capacity': self.relay.capacity.snapshot(),
                'bandwidth': self.bandwidth.snapshot(),
                'streams': len(self.relay.streams), 'max_rooms': self.relay.max_rooms,
                'max_connections': self.relay.max_connections, 'network_nodes': len(live),
                'public_join': self.state.get('public_join', False),
                'registration_open': self.state.get('registration_open', False),
                'email_verification': self.account_api.mail.required,
                'network_mode': 'federated' if self.federation.seeds else 'standalone',
                'heartbeat_interval': 2, 'heartbeat_timeout': 10,
                'fingerprint': self.federation.key.get_fingerprint(),
                'nodes': self.federation.health()}

    async def status(self, request):
        return web.json_response(self.public_state())

    def throttle(self, request):
        now = time.monotonic()
        source = request.remote or 'unknown'
        # Only explicitly configured proxies may supply a client address. A
        # direct client cannot evade limits by inventing forwarding headers.
        if source in self.state.get('trusted_proxy_ips', []):
            forwarded = request.headers.get('X-Real-IP', '')
            try:
                source = str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
        # Enrollment, email, login challenges and login are separate operations;
        # a normal registration must not exhaust its own subsequent login.
        key = (source, request.path)
        calls = self.attempts.setdefault(key, deque())
        self.attempts.move_to_end(key)
        while len(self.attempts) > 2048:
            self.attempts.popitem(last=False)
        while calls and calls[0] < now - 300:
            calls.popleft()
        if len(calls) >= 8:
            raise web.HTTPTooManyRequests(text='尝试过于频繁，请稍后重试。')
        calls.append(now)

    def session(self, request, write=False):
        now = time.monotonic()
        self.sessions = {k: v for k, v in self.sessions.items() if v['expires'] > now}
        session = self.sessions.get(request.cookies.get('node_session', ''))
        if not session:
            raise web.HTTPUnauthorized(text='请先登录管理员账户。')
        if write and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session['csrf']):
            raise web.HTTPForbidden(text='CSRF rejected')
        return session

    async def login(self, request):
        self.throttle(request)
        data = await request.json()
        if self.login_lock.locked():
            raise web.HTTPTooManyRequests(text='认证繁忙，请稍后重试。')
        async with self.login_lock:
            valid = await asyncio.to_thread(verify_password, data.get('password'), self.state['admin_hash'])
        if data.get('username') != self.state.get('admin_user', 'admin') or not valid:
            raise web.HTTPUnauthorized(text='用户名或密码错误。')
        if len(self.sessions) >= 64:
            self.sessions.pop(next(iter(self.sessions)))
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.sessions[token] = {'csrf': csrf, 'expires': time.monotonic() + 3600}
        response = web.json_response({'csrf': csrf})
        response.set_cookie('node_session', token, httponly=True, secure=request.secure,
                            samesite='Strict', max_age=3600, path='/')
        return response

    async def logout(self, request):
        self.session(request, True)
        self.sessions.pop(request.cookies.get('node_session', ''), None)
        response = web.json_response({'ok': True})
        response.del_cookie('node_session')
        return response

    async def admin(self, request):
        session = self.session(request)
        return web.json_response({'csrf': session['csrf'], 'name': self.federation.name,
                                  'public_join': self.state.get('public_join', False),
                                  'capacity': self.relay.capacity.snapshot(),
                                  'registration_open': self.state.get('registration_open', False),
                                  'accounts': [{'account': account, 'username': record['certificate']['username'],
                                                'home': record['certificate']['home'],
                                                'blocked': account in self.account_api.blocked}
                                               for account, record in self.account_api.store.records.items()],
                                  'draining': self.relay.draining,
                                  'node_id': self.federation.id,
                                  'peers': [dict(node, blocked=node['id'] in self.federation.blocked,
                                                 manageable=node['id'] in self.federation.seeds and not node['local'])
                                            for node in self.federation.health()],
                                  'node_decisions': list(reversed(self.state.get('node_decisions', [])[-20:]))})

    async def settings(self, request):
        self.session(request, True)
        data = await request.json()
        name, public_join, draining = data.get('name'), data.get('public_join'), data.get('draining')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Invalid name')
        if type(public_join) is not bool or type(draining) is not bool:
            raise ValueError('Invalid settings')
        registration = data.get('registration_open', self.state.get('registration_open', False))
        if type(registration) is not bool:
            raise ValueError('Invalid registration policy')
        from .capacity import policy
        next_capacity = policy(data.get('capacity', self.relay.capacity.policy))
        self.federation.name = name.strip()
        self.relay.capacity.configure(next_capacity)
        self.state['capacity'] = next_capacity
        self.state.update(public_join=public_join, draining=draining, registration_open=registration)
        self.relay.draining = draining
        self.save()
        return web.json_response({'ok': True})

    async def invite(self, request):
        self.session(request)
        return web.json_response(self.federation.invitation())

    async def join(self, request):
        self.session(request, True)
        self.federation.join(await request.json())
        return web.json_response({'ok': True})

    async def block(self, request):
        self.session(request, True)
        data = await request.json()
        node_id = data.get('id')
        if node_id == self.federation.id or node_id not in self.federation.seeds:
            raise ValueError('Unknown peer')
        if type(data.get('blocked')) is not bool:
            raise ValueError('Invalid block state')
        reason = data.get('reason')
        if (not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 300 or
                data.get('confirmation') != node_id):
            raise ValueError('Confirm the exact node ID and provide a reason')
        self.throttle(request)
        if self.login_lock.locked():
            raise web.HTTPTooManyRequests(text='认证繁忙，请稍后重试。')
        async with self.login_lock:
            valid = await asyncio.to_thread(verify_password, data.get('password'), self.state['admin_hash'])
        if not valid:
            raise web.HTTPUnauthorized(text='管理员密码错误。')
        async with self.node_action_lock:
            if (node_id in self.federation.blocked) == data['blocked']:
                raise web.HTTPConflict(text='节点状态已经改变，请刷新后重试。')
            name = self.federation.records.get(node_id, {}).get('body', {}).get('name', '已配置节点')
            if data['blocked']:
                self.federation.blocked.add(node_id)
                # This decision is local: no other operator receives an expulsion command.
                for peer in tuple(self.relay.peers):
                    if peer.role == 'federation' and peer.conn.get_extra_info('username') == 'federation:' + node_id:
                        peer.conn.close()
            else:
                self.federation.blocked.discard(node_id)
            self.state.setdefault('node_decisions', []).append({
                'at': int(time.time()), 'id': node_id, 'name': name,
                'action': 'isolate' if data['blocked'] else 'restore', 'reason': reason.strip()})
            self.state['node_decisions'] = self.state['node_decisions'][-100:]
            self.save()
        return web.json_response({'ok': True, 'scope': 'local'})

    async def leave(self, request):
        self.session(request, True)
        await self.federation.close()
        for peer in tuple(self.relay.peers):
            if peer.role == 'federation':
                peer.conn.close()
        self.federation.leave()
        self.federation.task = asyncio.create_task(self.federation.run())
        return web.json_response({'ok': True})

    async def profile(self, request):
        account = None
        try:
            account = self.account_api.session(request)['account']
        except web.HTTPUnauthorized:
            pass
        if not account and not self.state.get('public_join', False):
            session = self.sessions.get(request.cookies.get('node_session', ''))
            if not session or session['expires'] <= time.monotonic():
                self.throttle(request)
                data = await request.json()
                if self.login_lock.locked():
                    raise web.HTTPTooManyRequests(text='认证繁忙，请稍后重试。')
                async with self.login_lock:
                    valid = await asyncio.to_thread(verify_password, data.get('password'), self.state['access_hash'])
                if not valid:
                    raise web.HTTPUnauthorized(text='节点访问密码错误。')
        profile = dict(self.federation.profile)
        if account:
            profile['token'] = self.account_api.store.credential(account)
        code = 'buggnode1-' + base64.urlsafe_b64encode(
            json.dumps(profile, separators=(',', ':')).encode()).decode().rstrip('=')
        return web.json_response({'code': code, 'profile': profile,
                                  'fingerprint': self.federation.key.get_fingerprint()})

    async def start(self, host, port, ssl_context=None):
        self.federation.publish()
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, host, port, ssl_context=ssl_context)
        await site.start()
        return site

    async def close(self):
        if self.runner:
            await self.runner.cleanup()
