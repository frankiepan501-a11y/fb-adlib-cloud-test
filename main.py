"""Minimal Playwright test: scrape Facebook Ad Library from Zeabur cloud IP.
Uses the EXACT same JS extraction logic as production fb_ad_library_scraper.py.
"""
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
            headless=False,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--autoplay-policy=no-user-gesture-required',
            ],
        )
        ctx = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
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
        # Stronger anti-bot signal detection (excludes captcha which appears in FB JS bundles)
        debug['has_challenge'] = any(
            k in body_html.lower() for k in
            ['cloudflare', 'just a moment', 'datadome',
             'access denied', 'unusual traffic']
        )
        debug['has_login_wall'] = (
            '请登录' in body_html or
            'log in to facebook' in body_html.lower() or
            'You must log in' in body_html
        )
        # Count scontent images on page for diagnosis
        debug['scontent_img_total'] = body_html.count('scontent')

        for _ in range(min(max_ads // 5 + 1, 5)):
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(2)

        # Production-equivalent JS extraction (1:1 with fb_ad_library_scraper.py)
        ads = page.evaluate("""(maxAds) => {
            const results = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
                acceptNode: (node) => node.textContent.includes('资料库编号')
                    ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT
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
                const idMatch = text.match(/资料库编号[：:]\\s*(\\d+)/);
                ad.id = idMatch ? idMatch[1] : '';
                const dateMatch = text.match(/(\\d{4}年\\d{1,2}月\\d{1,2}日)开始投放/);
                ad.startDate = dateMatch ? dateMatch[1] : '';
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                let advertiser = '';
                let bodyStart = -1;
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i] === '赞助内容' || lines[i] === 'Sponsored') {
                        for (let j = i - 1; j >= Math.max(i - 5, 0); j--) {
                            const c = lines[j];
                            if (c && c !== '​' && !c.includes('查看') && !c.includes('打开') &&
                                !c.includes('平台') && !c.includes('资料库') && !c.includes('投放') &&
                                !c.includes('条广告') && c.length > 1 && c.length < 100) {
                                advertiser = c; break;
                            }
                        }
                        bodyStart = i + 1; break;
                    }
                }
                ad.pageName = advertiser;
                ad.body = '';
                if (bodyStart > 0) {
                    const bodyLines = [];
                    for (let i = bodyStart; i < Math.min(bodyStart + 15, lines.length); i++) {
                        const line = lines[i];
                        if (!line || line === '​') continue;
                        if (line.includes('资料库编号')) break;
                        bodyLines.push(line);
                    }
                    ad.body = bodyLines.join('\\n');
                }
                // Image extraction (production logic)
                const containerImgs = container.querySelectorAll('img');
                ad.images = [];
                ad.imgs_diag = [];
                for (const img of containerImgs) {
                    ad.imgs_diag.push({
                        src_has_scontent: !!(img.src && img.src.includes('scontent')),
                        natural_width: img.naturalWidth,
                        complete: img.complete,
                        loading: img.loading,
                    });
                    if (img.src && img.src.includes('scontent') && img.naturalWidth > 80) {
                        ad.images.push(img.src);
                    }
                }
                const containerVids = container.querySelectorAll('video');
                ad.hasVideo = containerVids.length > 0;
                if (containerVids.length > 0) {
                    for (const vid of containerVids) {
                        if (vid.poster && vid.poster.includes('scontent')) ad.images.push(vid.poster);
                    }
                }
                if (ad.pageName || ad.body) results.push(ad);
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
