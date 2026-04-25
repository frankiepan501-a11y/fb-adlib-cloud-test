"""Minimal Playwright test: scrape Facebook Ad Library from Zeabur cloud IP."""
import os, time, json
from fastapi import FastAPI, HTTPException, Header
from playwright.sync_api import sync_playwright

API_KEY = os.environ.get('API_KEY', 'test-key')
app = FastAPI()


def scrape_ad_library(brand_name: str, country: str = 'ALL', max_ads: int = 10):
    url = (f'https://www.facebook.com/ads/library/?active_status=active&ad_type=all'
           f'&country={country}&q={brand_name}&search_type=keyword_exact_phrase')
    debug = {'url': url}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
        )
        ctx = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/130.0.0.0 Safari/537.36'),
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until='networkidle', timeout=45000)
        except Exception as e:
            debug['goto_warn'] = str(e)[:200]
        time.sleep(5)

        debug['title'] = page.title()
        body_html = page.content()
        debug['body_len'] = len(body_html)
        debug['has_challenge'] = any(
            k in body_html.lower() for k in
            ['cloudflare', 'just a moment', 'captcha', 'datadome',
             'access denied', 'unusual traffic']
        )
        debug['has_login_wall'] = '请登录' in body_html or 'log in to facebook' in body_html.lower() or 'You must log in' in body_html

        for _ in range(min(max_ads // 5 + 1, 5)):
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(2)

        ads = page.evaluate("""(maxAds) => {
            const results = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
                acceptNode: (node) => (
                    node.textContent.includes('资料库编号') ||
                    node.textContent.includes('Library ID')
                ) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT
            });
            const adNodes = [];
            while (walker.nextNode()) {
                let container = walker.currentNode.parentElement;
                for (let i = 0; i < 8; i++) {
                    if (container && container.parentElement) container = container.parentElement;
                }
                if (!adNodes.includes(container)) adNodes.push(container);
            }
            for (const container of adNodes.slice(0, maxAds)) {
                const text = container.innerText || '';
                const ad = {};
                const idMatch = text.match(/(?:资料库编号|Library ID)[：:]\\s*(\\d+)/);
                ad.id = idMatch ? idMatch[1] : '';
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                let advertiser = '';
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i] === '赞助内容' || lines[i] === 'Sponsored') {
                        for (let j = i - 1; j >= Math.max(i - 5, 0); j--) {
                            const c = lines[j];
                            if (c && c !== '​' && !c.includes('查看') && c.length > 1 && c.length < 100) {
                                advertiser = c; break;
                            }
                        }
                        break;
                    }
                }
                ad.pageName = advertiser;
                const imgs = container.querySelectorAll('img');
                ad.images = [];
                for (const img of imgs) {
                    if (img.src && img.src.includes('scontent') && img.naturalWidth > 80) {
                        ad.images.push(img.src);
                    }
                }
                ad.hasVideo = container.querySelectorAll('video').length > 0;
                if (ad.pageName || ad.id) results.push(ad);
            }
            return results;
        }""", max_ads)

        browser.close()

    debug['ads_count'] = len(ads)
    debug['ads'] = ads
    return debug


@app.get('/health')
def health():
    return {'ok': True}


@app.get('/scrape')
def scrape(brand: str, country: str = 'ALL', max_ads: int = 10,
           x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(403, 'invalid api key')
    try:
        return scrape_ad_library(brand, country, max_ads)
    except Exception as e:
        raise HTTPException(500, f'scrape failed: {e}')
