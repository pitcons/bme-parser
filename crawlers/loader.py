# encoding: utf-8
import re
import aiohttp
import asyncio
import async_timeout
from collections import defaultdict
import db
from lxml import etree
from aiocache import cached, RedisCache
from aiocache.serializers import PickleSerializer

cache = RedisCache(endpoint="127.0.0.1", port=6379, namespace="main")

BASE_URL = 'http://xn--90aw5c.xn--c1avg'
START_URL = BASE_URL + '/index.php/Указатель%20А-Я'


class BmeLoader:
    FETCH_TIMEOUT = 50
    ON_ERROR_SLEEP = 1

    def __init__(self):
        self.parser = etree.XMLParser(recover=True)
        self.fetch_sem = asyncio.Semaphore(1)

    def get_body(self, html):
        body = html[html.find('<body'):html.find('</body')]
        root = etree.fromstring(body, self.parser)
        return root

    def cast_url(self, url):
        if url.startswith('/'):
            return BASE_URL + url
        else:
            return url

    async def fetch(self, session, url):
        url = self.cast_url(url)
        data = await cache.get(url)
        if data:
            return data

        while True:
            async with self.fetch_sem:
                with async_timeout.timeout(self.FETCH_TIMEOUT):
                    async with session.get(url) as response:
                        html = await response.text()
                        if response.status == 200:
                            await cache.set(url, html)
                            return html
                        await asyncio.sleep(self.ON_ERROR_SLEEP)

    async def fetch_article(self, session, url, title):
        html = await self.fetch(session, url)
        article = db.Article(url=url, title=title, raw=html)
        article.save()
        print(title)

    async def fetch_tome(self, session, url):
        root = self.get_body(await self.fetch(session, url))
        await asyncio.wait([
            self.fetch_article(session, a.get('href'), a.get('title'))
            for a in root.xpath('//div[@class="mw-content-ltr"]//a')
        ])
        next_pages = root.xpath('//a[text()="следующие 200"]')
        if next_pages:
            await self.fetch_tome(session, next_pages[0].get('href'))

    async def run(self, loop):
        async with aiohttp.ClientSession(loop=loop) as session:
            body = self.get_body(await self.fetch(session, START_URL))
            await asyncio.wait([
                self.fetch_tome(session, a.get('href'))
                for a in body.xpath('//a')
                if a.get('title', '').startswith('Категория')
            ])


def bme3load():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(BmeLoader().run(loop))
