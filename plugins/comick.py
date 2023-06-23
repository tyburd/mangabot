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
    
    pre_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0'
    }
    
    def __init__(self, *args, name="Comick", language=None, **kwargs):
        if language is None:
            language = "en"
        super().__init__(*args, name=f'{name}-{language}')
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
            
            images.append(card['cover_url'])
            
            slugs.append(card['slug'])
        
        return [ComickMangaCard(self, *tup) for tup in zip(names, urls, images, slugs)]
    
    def chapters_from_page(self, page: bytes, manga: MangaCard = None):
        data = json.loads(page.decode())
        
        texts = []
        links = []
        slugs = []
        
        for chapter in data['chapters']:
            if chapter['title']:
                texts.append(f'{chapter["chap"]} - {chapter["title"]}')
            else:
                texts.append(chapter["chap"])

            links.append(f'{self.base_url.geturl()}chapter/{chapter["hid"]}?tachiyomi=true')

            slugs.append(f'{chapter["hid"]}-chapter-{chapter["chap"]}-{chapter["lang"]}')

        return list(map(lambda x: ComickMangaChapter(self, x[0], x[1], manga, [], x[2]), zip(texts, links, slugs)))

    async def pictures_from_chapters(self, content: bytes, response=None):
        data = json.loads(content.decode())

        if "message" in data:
            return []

        images_url = [image["url"] for url in data["chapter"]["images"]]

        return images_url

    async def search(self, query: str = "", page: int = 1) -> List[MangaCard]:
        query = quote(query)

        request_url = f'{self.search_url}?type=comic&page={page}&limit=20&tachiyomi=true&{self.search_param}={query}&t=false'

        content = await self.get_url(request_url)

        return self.mangas_from_page(content)

    async def get_chapters(self, manga_card: MangaCard, page: int = 1, count: int = 20) -> List[MangaChapter]:

        request_url = f'{manga_card.url}&limit={count}&page={page}'

        content = await self.get_url(request_url)
        
        return self.chapters_from_page(content, manga_card)
    
    async def iter_chapters(self, manga_url: str, manga_name) -> AsyncIterable[MangaChapter]:
        manga_card = MangaCard(self, manga_name, manga_url, '')
        
        request_url = manga_url
        
        content = await self.get_url(request_url)
        
        for chapter in self.chapters_from_page(content, manga_card):
            yield chapter
    
    async def check_updated_urls(self, last_chapters: List[LastChapter]):
        
        content = await self.get_url(f'{self.updates_url}&lang={self.lang}')
        
        data = json.load(content.decode())
        
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
                    ch_id = chapter_item["hid"]
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

    async def get_url(self, url, *args, file_name=None, cache=False, req_content=True, method='get', data=None, **kwargs):
        if "headers" not in kwargs:
            kwargs["headers"] = self.pre_headers
        return await super(ComickClient, self).get_url(url, *args, file_name=file_name, cache=cache, req_content=req_content, method=method, **kwargs)

    async def get_cover(self, manga_card: MangaCard, *args, **kwargs):
        headers = {**self.pre_headers, 'Referer': self.base_url.geturl()}
        return await super(ComickClient, self).get_cover(manga_card, *args, headers=headers, **kwargs)

    async def get_picture(self, manga_chapter: MangaChapter, url, *args, **kwargs):
        headers = {**self.pre_headers, 'Referer': self.base_url.geturl()}
        return await super(ComickClient, self).get_picture(manga_chapter, url, *args, headers=headers, **kwargs)