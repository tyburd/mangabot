import io
import sys
import traceback
import importlib
import logging

from pathlib import Path 
from pyrogram.enums import ParseMode
from bot import add_manga_options, bot, bot_ask, DB, filters, file_options, mangas, Subscription, LastChapter

MAX_MESSAGE_LENGTH = 4096

ALLOWED_USERS = 5591954930
def load_plugin(plugin_path: Path):
    plugin_name = plugin_path.stem
    if not plugin_name.startswith("__"):
        name = f"{plugin_path.parent.stem}.{plugin_name}" if plugin_path.parent.stem else plugin_name
        spec = importlib.util.spec_from_file_location(name, plugin_path)
        load = importlib.util.module_from_spec(spec)
        load.logger = logging.getLogger(plugin_name)
        spec.loader.exec_module(load)
        sys.modules[name] = load

def get_manga_url(url: str):
    for _, manga in mangas.items():
        if manga.get_url() == url:
            return manga.url
    else:
        return url

async def check_last_chapter(url: str):
    db = DB()
    for _, manga in mangas.items():
        if url in [manga.get_url(), manga.url]:
            if await db.get_subs_by_url(manga.url):
                if not await db.get(LastChapter, manga.url):
                    agen = manga.client.iter_chapters(manga.url, manga.name)
                    lc = await anext(agen)
                    await db.add(LastChapter(url=manga.url, chapter_url=lc.url))
            break

@bot.on_message(filters=filters.command("addsub") & filters.user(ALLOWED_USERS), group=1)
async def addsub_handler(client, message):
    q, a = await bot_ask(message, "Give me the manga url.")
    await q.delete()
    manga_url = get_manga_url(a.text)
    await check_last_chapter(manga_url)
        
    q, a = await bot_ask(message, "Give me the chat ID.")
    await q.delete()
    try:
        manga_chat = int(a.text)
    except ValueError:
        await a.reply_text("Chat ID should be an int.")
        return 
        
    try:
        tmp_msg = await bot.send_message(manga_chat, manga_url)
        await tmp_msg.delete()
    except BaseException:
        await a.reply_text("Bot couldn't send a message to the provided chat ID. Make sure that bot is added correctly!")
        return
        
    q, a = await bot_ask(message, 'Give me the file format for the chapters.\n\nYou can choose in ↓\n\n→<code>PDF</code>\n→<code>CBZ</code>\n→<code>BOTH</code>')
    await q.delete()
    file_mode = a.text.lower()
    output = file_options.get(file_mode, None)
    if output is None:
        await a.reply_text('Wrong File Format Option. You have to choose between the options i gave.')
        return 

    await add_manga_options(str(manga_chat), output)
        
    db = DB()
    sub = await db.get(Subscription, (manga_url, str(manga_chat)))
    if sub:
        await message.reply("Subscription already exists!")
        return
    
    await db.add(Subscription(url=manga_url, user_id=str(manga_chat)))

    await message.reply(f"<b>Added New Manga Subscription.</b>\n\n<b>›› Url →</b> <code>{manga_url}</code>\n<b>›› Chat →</b> <code>{manga_chat}</code>\n<b>›› File Mode →</b> <code>{file_mode.upper()}</code>")


@bot.on_message(filters=filters.command("rmsub") & filters.user(ALLOWED_USERS), group=1)
async def rmsub_handler(client, message):
    try:
        _, url, chat = message.text.split(" ")
    except ValueError:
        return 
    
    url = get_manga_url(url)
    db = DB()
    sub = await db.get(Subscription, (url, chat))
    if not sub:
        await message.reply_text("Subscription doesn't exist!")
        return
    await db.erase(sub)
    await message.reply_text("Removed the Subscription.")
    
    
@bot.on_message(filters=filters.command("eval") & filters.user(ALLOWED_USERS), group=1)
async def _(client, message):
    status_message = await message.reply_text("Processing ...")
    try:
        cmd = message.text.markdown.split(" ", maxsplit=1)[1]
    except:
        return await status_message.edit_text("Give code to evaluate...")

    reply_to_ = message
    if message.reply_to_message:
        reply_to_ = message.reply_to_message

    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    redirected_error = sys.stderr = io.StringIO()
    stdout, stderr, exc = None, None, None

    try:
        await aexec(cmd, client, message)
    except Exception:
        exc = traceback.format_exc()

    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr

    evaluation = ""
    if exc:
        evaluation = exc
    elif stderr:
        evaluation = stderr
    elif stdout:
        evaluation = stdout
    else:
        evaluation = "Success"

    final_output = "**EVAL**: "
    final_output += f"`{cmd}`\n\n"
    final_output += "**OUTPUT**:\n"
    final_output += f"`{evaluation.strip()}`\n"

    if len(final_output) > MAX_MESSAGE_LENGTH:
        with io.BytesIO(str.encode(evaluation)) as out_file:
            out_file.name = "eval.text"
            await reply_to_.reply_document(
                document=out_file,
                caption=f"`{cmd[: MAX_MESSAGE_LENGTH // 4 - 1]}`",
                disable_notification=True,
                parse_mode=ParseMode.MARKDOWN,
                quote=True,
            )
    else:
        await reply_to_.reply_text(final_output, parse_mode=ParseMode.MARKDOWN, quote=True)
    await status_message.delete()

async def aexec(code, client, message):
    exec(
        "async def __aexec(client, message): "
        + "\n m = message"
        + "\n chat = m.chat.id"
        + "\n reply = m.reply_to_message"
        + "".join(f"\n {l_}" for l_ in code.split("\n"))
    )
    return await locals()["__aexec"](client, message)
