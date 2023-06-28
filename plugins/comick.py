import json
from dataclasses import dataclass
from typing import List, AsyncIterable
from urllib.parse import urlparse, urljoin, quote

from plugins.client import MangaClient, MangaCard, MangaChapter, LastChapter


@dataclass
class ComickMangaCard(MangaCard):
    slug: str

    def get_url(self):
        return f"https://comick.app/comic/{self.slug}"


@dataclass
class ComickMangaChapter(MangaChapter):
    slug: str

    def get_url(self):
        return f"{self.manga.get_url()}/{self.slug}"


class ComickClient(MangaClient):
    base_url = urlparse("https://api.comick.app/")
    search_url = urljoin(base_url.geturl(), "v1.0/search")
    search_param = "q"
    updates_url = "https://api.comick.app/chapter/?page=1&order=new&tachiyomi=true&accept_erotic_content=true"
    covers_url = urlparse("https://meo.comick.pictures/")

    pre_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0'
    }

    def __init__(self, *args, name="Comick", language=None, **kwargs):
        if language is None:
            language = "en"
        super().__init__(*args, name=f'{name}-{language}', headers=self.pre_headers, **kwargs)
        self.lang = language

    def mangas_from_page(self, page: bytes):
        data = json.loads(page.decode())

        names = []
        urls = []
        images = []
        slugs = []

        for card in data:
            names.append(card['title'])
            urls.append(f'{self.base_url.geturl()}comic/{card["hid"]}/chapters?lang={self.lang}')
            images.append(urljoin(self.covers_url.geturl(), card["md_covers"][0]["b2key"]) or card["covers_url"])
            slugs.append(card['slug'])

        return [ComickMangaCard(self, *tup) for tup in zip(names, urls, images, slugs)]

    def chapters_from_page(self, page: bytes, manga: MangaCard = None):
        data = json.loads(page.decode())

        texts = []
        links = []
        slugs = []

        for chapter in reversed(data['chapters']):
            title = f'Chapter {chapter["chap"]}' if chapter["chap"] else chapter["title"]
            if (not title and chapter["vol"]) or title in texts:
                continue
            link = f'{self.base_url.geturl()}chapter/{chapter["hid"]}?tachiyomi=true'
            slug = f'{chapter["hid"]}-chapter-{chapter["chap"]}-{chapter["lang"]}'

            texts.append(title)
            links.append(link)
            slugs.append(slug)
        
        texts.reverse()
        links.reverse()
        slugs.reverse()

        return list(map(lambda x: ComickMangaChapter(self, x[0], x[1], manga, [], x[2]), zip(texts, links, slugs)))

    async def pictures_from_chapters(self, content: bytes, response=None):
        data = json.loads(content.decode())

        if "message" in data:
            return []

        images_url = [image["url"] for image in data["chapter"]["images"]]

        return images_url

    async def search(self, query: str = "", page: int = 1) -> List[MangaCard]:
        query = quote(query)

        request_url = f'{self.search_url}?type=comic&page={page}&limit=20&minimum=1&tachiyomi=true&{self.search_param}={query}&t=false'

        content = await self.get_url(request_url)

        return self.mangas_from_page(content)

    async def get_chapters(self, manga_card: MangaCard, page: int = 1) -> List[MangaChapter]:
        request_url = f'{manga_card.url}&limit=100000'

        content = await self.get_url(request_url)

        return self.chapters_from_page(content, manga_card)[(page - 1) * 20:page * 20]

    async def iter_chapters(self, manga_url: str, manga_name) -> AsyncIterable[MangaChapter]:
        manga_card = MangaCard(self, manga_name, manga_url, '')

        request_url = f'{manga_card.url}&limit=100000'

        content = await self.get_url(request_url)

        for chapter in self.chapters_from_page(content, manga_card):
            yield chapter

    async def contains_url(self, url: str):
        return url.startswith(self.base_url.geturl())

    async def check_updated_urls(self, last_chapters: List[LastChapter]):
        content = await self.get_url(f'{self.updates_url}&lang={self.lang}')

        data = json.loads(content.decode())

        updates = {}
        for item in data:
            manga_id = item["md_comics"]["hid"]
            last_chapter = item["md_comics"]["last_chapter"]
            if last_chapter == item["chap"]:
                ch_id = item["hid"]
            else:
                content = await self.get_url(f'{self.base_url.geturl()}comic/{manga_id}/chapters?lang={self.lang}&chap={last_chapter}')
                chapter_item = json.loads(content.decode()).get("chapters", [])
                if chapter_item:
                    ch_id = chapter_item[-1]["hid"]
                else:
                    ch_id = item["hid"]
            if manga_id not in updates:
                updates[manga_id] = ch_id

        updated = []
        not_updated = []

        for lc in last_chapters:
            upd = False
            for manga_id, ch_id in updates.items():
                if manga_id in lc.url and not ch_id in lc.chapter_url:
                    upd = True
                    updated.append(lc.url)
                    break
            if not upd:
                not_updated.append(lc.url)

        return updated, not_updated

    async def get_cover(self, manga_card: MangaCard, *args, **kwargs):
        headers = {**self.pre_headers, 'Referer': self.base_url.geturl()}
        return await super(ComickClient, self).get_cover(manga_card, *args, headers=headers, **kwargs)

    async def get_picture(self, manga_chapter: MangaChapter, url, *args, **kwargs):
        headers = {**self.pre_headers, 'Referer': self.base_url.geturl()}
        return await super(ComickClient, self).get_picture(manga_chapter, url, *args, headers=headers, **kwargs)
