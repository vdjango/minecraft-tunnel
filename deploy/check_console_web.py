"""Exercise the standalone console and local isolation on a disposable cluster."""
import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def run(args):
    folder = args.directory.resolve()
    values = dict(line.split(': ', 1) for line in (folder / 'admin-credentials.txt').read_text(
        encoding='utf-8').splitlines() if ': ' in line)
    url = f'https://127.0.0.1:{args.web_port}'
    args.output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True,
            **({'executable_path':str(args.browser)} if args.browser else {}))
        context = await browser.new_context(ignore_https_errors=True, viewport={'width':1440,'height':1000})
        page = await context.new_page()
        errors, dialogs = [], []
        page.on('pageerror', lambda error:errors.append(str(error)))
        page.on('dialog', lambda dialog:dialogs.append(dialog.type))
        target, changed = None, False
        csrf = ''
        try:
            await page.goto(url, wait_until='networkidle')
            await page.click('#open-admin')
            await page.wait_for_url('**/admin')
            assert await page.locator('dialog').count() == 0
            await page.fill('#admin-password', values['Admin password'])
            await page.locator('#login-form button[type=submit]').click()
            await page.locator('#admin-panel').wait_for(state='visible')
            state = await (await context.request.get(url + '/api/admin')).json()
            csrf = state['csrf']
            assert len(state['peers']) == 4
            target = next(n for n in state['peers'] if not n['local'] and not n['blocked'])
            row = page.locator('.admin-node').filter(has=page.locator('code', has_text=target['id']))
            await row.locator('button').click()
            await page.locator('#node-action-form').wait_for(state='visible')
            assert await page.locator('#action-node-id').text_content() == target['id']
            # A missing confirmation must stay on the form, without any server mutation.
            await page.locator('#action-submit').click()
            again = await (await context.request.get(url + '/api/admin')).json()
            assert not next(n for n in again['peers'] if n['id'] == target['id'])['blocked']
            await page.fill('#action-reason', 'Local browser isolation test')
            await page.fill('#action-confirmation', target['id'])
            await page.fill('#action-password', values['Admin password'])
            async with page.expect_response(lambda r:r.url.endswith('/api/federation/block') and r.request.method == 'POST') as action:
                await page.locator('#action-submit').click()
            assert (await action.value).status == 200
            changed = True
            await page.locator('#node-action-form').wait_for(state='hidden')
            await page.wait_for_function("document.querySelector('#node-history').textContent.includes('Local browser isolation test')")
            await row.locator('button').click()
            await page.fill('#action-reason', 'Restore after browser validation')
            await page.fill('#action-confirmation', target['id'])
            await page.fill('#action-password', values['Admin password'])
            async with page.expect_response(lambda r:r.url.endswith('/api/federation/block') and r.request.method == 'POST') as restored:
                await page.locator('#action-submit').click()
            assert (await restored.value).status == 200
            changed = False
            await page.locator('#node-action-form').wait_for(state='hidden')
            await page.reload(wait_until='networkidle')
            await page.locator('#admin-panel').wait_for(state='visible')
            await page.screenshot(path=str(args.output/'console-desktop.png'), full_page=True)
            await page.set_viewport_size({'width':390,'height':844})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(args.output/'console-mobile.png'), full_page=True)
            # Refreshing members must never overwrite unsaved settings.
            await page.goto(url + '/admin/settings', wait_until='networkidle')
            await page.fill('#setting-name','Unsubmitted browser edit')
            await page.wait_for_timeout(5200)
            assert await page.locator('#setting-name').input_value() == 'Unsubmitted browser edit'
            await page.goto(url + '/developers', wait_until='networkidle')
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert await page.locator('.docs-toc').is_visible()
            for link in await page.locator('.docs-toc a').all():
                assert await page.locator(await link.get_attribute('href')).count() == 1
            await page.locator('.docs-toc a[href="#examples"]').click()
            sample = page.locator('.docs-sample').filter(has_text='C / C++')
            await sample.locator('summary').click()
            assert await sample.locator('pre').is_visible()
            assert await page.locator('#quickstart').get_by_text('JSON-RPC 2.0').count() >= 1
            assert await page.locator('#rooms-api').get_by_text('room.join').count() >= 1
            assert await page.locator('.docs-sample').filter(has_text='C / C++').count() == 1
            assert await page.locator('.docs-sample').filter(has_text='Java').count() == 1
            assert await page.locator('.docs-sample').filter(has_text='C#').count() == 1
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(args.output/'developers-mobile.png'), full_page=True)
            await page.set_viewport_size({'width':1440,'height':1000})
            await page.evaluate('scrollTo(0, 0)')
            await page.screenshot(path=str(args.output/'developers-desktop.png'), full_page=True)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            async with page.expect_download() as download:
                await page.locator('a[href="/launcher-example.py"]').click()
            assert (await download.value).suggested_filename == 'launcher-example.py'
            await page.goto(url, wait_until='networkidle')
            assert await page.locator('#open-admin').is_visible()
            await page.click('#open-account')
            await page.locator('#account-login').wait_for(state='visible')
            assert not errors, errors
            assert not dialogs, dialogs
            report = {'passed':True,'checks':['standalone administration','four-node list',
                'confirmation and reauthentication','local isolation and restoration','persistent local history',
                'unsaved settings survive refresh','desktop and mobile developer docs',
                'document anchors and expandable language samples','downloadable example',
                'public account flow preserved','no script errors or popup confirmations']}
            (args.output/'console-browser-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report,indent=2))
        finally:
            if changed:
                response = await context.request.post(url + '/api/federation/block',
                    headers={'X-CSRF-Token':csrf}, data={'id':target['id'], 'blocked':False,
                        'confirmation':target['id'], 'reason':'Restore after failed browser validation',
                        'password':values['Admin password']})
                assert response.status == 200, 'Failed to restore the local test member'
            await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True, help='Disposable local node configuration folder')
    parser.add_argument('--web-port', type=int, required=True)
    parser.add_argument('--browser', type=Path)
    parser.add_argument('--output', type=Path, default=Path('../multiplayer-tests/console-web'))
    asyncio.run(run(parser.parse_args()))
