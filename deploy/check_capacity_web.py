"""Verify capacity controls with real browser submissions on a local test node."""
import argparse
import asyncio
import json
from pathlib import Path

from aiohttp import ClientSession, Fingerprint
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from playwright.async_api import async_playwright


async def run(args):
    folder = args.directory.resolve()
    values = dict(line.split(': ', 1) for line in (folder / 'admin-credentials.txt').read_text(
        encoding='utf-8').splitlines() if ': ' in line)
    pin = Fingerprint(x509.load_pem_x509_certificate((folder / 'web-cert.pem').read_bytes()).fingerprint(hashes.SHA256()))
    url = f'https://127.0.0.1:{args.web_port}'
    args.output.mkdir(parents=True, exist_ok=True)
    async with ClientSession() as session:
        async with session.post(url + '/api/login', json=dict(username='admin', password=values['Admin password']), ssl=pin) as response:
            assert response.status == 200
            headers = {'Cookie':'node_session=' + response.cookies['node_session'].value,
                       'X-CSRF-Token':(await response.json())['csrf']}
        async with session.get(url + '/api/admin', headers=headers, ssl=pin) as response:
            before = await response.json()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, **({'executable_path':str(args.browser)} if args.browser else {}))
            errors = []
            try:
                context = await browser.new_context(ignore_https_errors=True, viewport={'width':1440,'height':1000})
                page = await context.new_page()
                page.on('pageerror', lambda error:errors.append(str(error)))
                await page.goto(url, wait_until='networkidle')
                await page.click('#open-admin')
                await page.wait_for_url('**/admin')
                await page.fill('#username','admin')
                await page.fill('#admin-password',values['Admin password'])
                await page.locator('#login-form button[type=submit]').click()
                await page.locator('#admin-panel').wait_for(state='visible')
                for name, value in [('max-rooms','8'),('room-capacity','6'),('bandwidth','1'),('reserve','35'),('player-budget','0.128')]:
                    await page.fill('#setting-' + name,value)
                async with page.expect_response(lambda r:r.url.endswith('/api/settings') and r.request.method=='POST') as saved:
                    await page.locator('#settings-form button[type=submit]').click()
                assert (await saved.value).status == 200
                async with session.get(url + '/api/status', ssl=pin) as response:
                    state = await response.json()
                assert state['capacity']['recommended_visitors'] == 4
                assert state['capacity']['room_capacity'] == 6
                assert state['max_rooms'] == 8
                await page.screenshot(path=str(args.output/'capacity-admin.png'))
                await page.set_viewport_size({'width':390,'height':844})
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert await page.locator('#admin-panel').evaluate('(e) => e.scrollWidth <= e.clientWidth')
                await page.screenshot(path=str(args.output/'capacity-admin-mobile.png'))
                await page.goto(url, wait_until='networkidle')
                assert '4 人' in await page.locator('#capacity-visitors').text_content()
                assert '35%' in await page.locator('#capacity-explanation').text_content()
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await page.screenshot(path=str(args.output/'capacity-public-mobile.png'))
                assert not errors, errors
                report = dict(passed=True, checks=['administrator form persists capacity','1 MB/s admits 4 budgeted visitors',
                    'public budget explanation','mobile administration and public page','no script errors'])
                (args.output/'capacity-browser-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                print(json.dumps(report,indent=2))
            finally:
                await browser.close()
                payload = {k:before[k] for k in ('name','public_join','draining','registration_open','capacity')}
                async with session.post(url + '/api/settings', json=payload, headers=headers, ssl=pin) as response:
                    assert response.status == 200, 'Failed to restore original test settings'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True,help='One local test node configuration folder')
    parser.add_argument('--web-port',type=int,required=True)
    parser.add_argument('--browser',type=Path)
    parser.add_argument('--output',type=Path,default=Path('../multiplayer-tests/capacity-web'))
    asyncio.run(run(parser.parse_args()))
