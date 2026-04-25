# fb-adlib-cloud-test

Minimal Playwright + FastAPI service for testing whether a cloud IP can scrape Facebook Ad Library.

Deployed on Zeabur as a one-shot validation before migrating Meta Ads automation off Frankie's local PC.

```
GET /scrape?brand=Powkong&country=ALL&max_ads=10
Header: x-api-key: <API_KEY>
```
