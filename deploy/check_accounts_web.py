"""Exercise real WebCrypto and account forms on a disposable local four-node cluster.

Requires Playwright and Chromium/Edge. Opens registration on this local cluster.
"""
import argparse
import asyncio
import json
from pathlib import Path
import secrets
import sys

from aiohttp import ClientSession, Fingerprint
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'buggcraft/src/buggcraft'))
from hookup.nodes import decode_code, probe
from hookup.rooms import lookup_account


def records(directory):
    path = directory / 'accounts-replica.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []


async def run(args):
    base = args.directory.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    async with ClientSession() as session:
        for index, label in enumerate('ABCD'):
            folder = base / label
            values = dict(line.split(': ', 1) for line in (folder / 'admin-credentials.txt').read_text(
                encoding='utf-8').splitlines() if ': ' in line)
            pin = Fingerprint(x509.load_pem_x509_certificate((folder / 'web-cert.pem').read_bytes()).fingerprint(hashes.SHA256()))
            url = f'https://127.0.0.1:{args.web_port + index}'
            async with session.post(url + '/api/login', json=dict(username='admin', password=values['Admin password']), ssl=pin) as response:
                assert response.status == 200
                headers = {'Cookie': 'node_session=' + response.cookies['node_session'].value,
                           'X-CSRF-Token': (await response.json())['csrf']}
            async with session.get(url + '/api/admin', headers=headers, ssl=pin) as response:
                state = await response.json()
            async with session.post(url + '/api/settings', headers=headers, ssl=pin,
                json=dict(name=state['name'], public_join=state['public_join'], draining=False, registration_open=True)) as response:
                assert response.status == 200
            # This disposable cluster tests WebCrypto and routing without SMTP.
            async with session.post(url + '/api/admin/mail', headers=headers, ssl=pin,
                json=dict(host='smtp.example.com', port=465, username='', password='',
                          from_name='Browser test', required=False)) as response:
                assert response.status == 200
    errors, requests = [], []
    password = secrets.token_urlsafe(24)
    username = 'browser_' + secrets.token_hex(4)
    notes = 'private note ' + secrets.token_hex(12)
    async with async_playwright() as playwright:
        options = {'headless': True}
        if args.browser:
            options['executable_path'] = str(args.browser)
        browser = await playwright.chromium.launch(**options)
        try:
            context = await browser.new_context(ignore_https_errors=True, accept_downloads=True,
                                                viewport={'width': 1440, 'height': 1000})
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: requests.append(request.post_data or ''))
            await page.goto(f'https://127.0.0.1:{args.web_port}/', wait_until='networkidle')
            assert await page.locator('nav .developer-nav').is_visible()
            assert await page.locator('.entry-strip a[href="/developers"]').is_visible()
            assert await page.locator('#node-name-heading').text_content() != '社区联机节点'
            await page.locator('.entry-strip a').click()
            await page.wait_for_url('**/developers')
            assert '账号与个人接入码' in await page.locator('body').inner_text()
            await page.goto(f'https://127.0.0.1:{args.web_port}/', wait_until='networkidle')
            await page.click('#open-account')
            assert await page.locator('#account-login').is_visible()
            assert not await page.locator('#account-register').is_visible()
            await page.click('#show-register')
            assert not await page.locator('#account-login').is_visible()
            assert await page.locator('#register-copies').input_value() == '0'
            await page.fill('#register-name', username)
            await page.fill('#register-password', password)
            await page.fill('#register-confirm', password)
            await page.select_option('#register-copies', '1')
            async with page.expect_download():
                await page.locator('#account-register button[type=submit]').click()
            await page.locator('#account-panel').wait_for(state='visible')
            account = await page.locator('#account-current').text_content()
            assert len(account) == 65
            await page.fill('#account-nickname', '跨节点玩家')
            await page.fill('#account-notes', notes)
            await page.click('#account-save')
            await page.wait_for_function("() => document.querySelector('#account-feedback').textContent.includes('已按所选策略加密保存')")
            await page.screenshot(path=str(output / 'account-desktop.png'))
            async with asyncio.timeout(40):
                while True:
                    holders = [i for i, label in enumerate('ABCD') if any(
                        r['state']['account'] == account and r['state']['revision'] == 2 for r in records(base / label))]
                    if len(holders) == 2:
                        break
                    await asyncio.sleep(.25)
            # Log in at a node which deliberately has no durable encrypted copy.
            index = next(i for i in range(1, 4) if i not in holders)
            mobile = await browser.new_context(ignore_https_errors=True, viewport={'width': 390, 'height': 844})
            second = await mobile.new_page()
            second.on('pageerror', lambda error: errors.append(str(error)))
            second.on('request', lambda request: requests.append(request.post_data or ''))
            await second.goto(f'https://127.0.0.1:{args.web_port + index}/', wait_until='networkidle')
            assert await second.locator('nav .developer-nav').is_visible()
            assert await second.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await second.screenshot(path=str(output / 'home-mobile.png'), full_page=True)
            await second.click('#open-account')
            await second.fill('#account-id', username)
            await second.fill('#account-password', password)
            await second.locator('#account-login button[type=submit]').click()
            await second.locator('#account-panel').wait_for(state='visible')
            assert await second.locator('#account-nickname').input_value() == '跨节点玩家'
            assert await second.locator('#account-notes').input_value() == notes
            assert not any(r['state']['account'] == account for r in records(base / 'ABCD'[index]))
            assert await second.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await second.screenshot(path=str(output / 'account-mobile.png'))
            # Writes through a login-only node must reach the actual durable targets.
            await second.fill('#account-notes', notes + '-updated')
            await second.click('#account-save')
            await second.wait_for_function("() => document.querySelector('#account-feedback').textContent.includes('已按所选策略加密保存')")
            async with asyncio.timeout(40):
                while not all(any(r['state']['account'] == account and r['state']['revision'] == 3
                                 for r in records(base / 'ABCD'[i])) for i in holders):
                    await asyncio.sleep(.25)
            assert not any(r['state']['account'] == account for r in records(base / 'ABCD'[index]))
            await second.fill('#account-nickname', '尚未保存的昵称')
            await second.wait_for_function("() => document.querySelector('#account-backup-status').textContent.includes('2 / 2')", timeout=20000)
            assert await second.locator('#account-nickname').input_value() == '尚未保存的昵称'
            await second.click('#account-connect')
            await second.locator('#connect-result').wait_for(state='visible')
            code = await second.locator('#player-code').input_value()
            profile = decode_code(code)
            assert profile.token.startswith('acct1.')
            await probe(profile)
            assert await lookup_account(profile, username) == [{'account': account, 'username': username}]
            await second.locator('[data-close="connect-dialog"]').click()
            await second.click('#open-account')
            await second.click('#account-logout')
            await second.locator('#account-login').wait_for(state='visible')
            assert await second.locator('#player-code').input_value() == ''
            assert not await second.locator('#connect-result').is_visible()
            assert await second.locator('#account-notes').input_value() == ''
            assert all(password not in body and notes not in body for body in requests)
            for label in 'ABCD':
                replica = json.dumps(records(base / label))
                assert password not in replica and notes not in replica and 'PRIVATE KEY' not in replica
            assert not errors, errors
            report = dict(passed=True, checks=['separate login/register forms', 'default no backup',
                'WebCrypto encryption', 'username routing without durable local copy',
                'remote write reaches selected durable replicas', 'personal launcher code',
                'personal code accepted by launcher SDK and friend directory',
                'home developer entry visible on desktop/mobile',
                'logout clears page credentials and decrypted fields',
                'no cleartext password/settings in requests or replicas', 'desktop/mobile', 'no script errors'])
            (output / 'account-browser-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report, indent=2))
        finally:
            await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT / 'config/local-cluster')
    parser.add_argument('--web-port', type=int, default=18443)
    parser.add_argument('--browser', type=Path, help='Optional Chromium/Edge executable')
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'multiplayer-tests/node-web')
    asyncio.run(run(parser.parse_args()))
