from typing import List

from telegraph.aio import Telegraph

from plugins import MangaChapter


async def img2tph(manga_chapter: MangaChapter, name: str):
    lines = []
    for img in manga_chapter.pictures:
        a_tag = f'<img src="{img}"/>'
        lines.append(a_tag)
    content = '\n'.join(lines)

    client = Telegraph()
    await client.create_account('TrashMangaBot')
    page = await client.create_page(name, author_name='TrashMangaBot', author_url='https://t.me/trashmangabot', html_content=content)
    return page['url'].replace('telegra.ph', 'te.legra.ph')
