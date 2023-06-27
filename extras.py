import asyncio
import importlib
import io
import logging
import sys
import traceback
from pathlib import Path

from bot import (ALLOWED_USERS, DB, LastChapter, MangaName, Subscription,
                 add_manga_options, bot, bot_ask, file_options, filters,
                 mangas)
from pyrogram.enums import ParseMode

MAX_MESSAGE_LENGTH = 4096


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
        if url in [manga.get_url(), manga.url]:
            return manga.url, manga
    else:
        return url, None


async def update_last_chapter(url: str, exist_check: bool = True):
    db = DB()
    LC = None
    for _, manga in mangas.items():
        if url in [manga.get_url(), manga.url]:
            if not (LC := await db.get(LastChapter, manga.url)) or not exist_check:
                agen = manga.client.iter_chapters(manga.url, manga.name)
                lc = await anext(agen, None)
                if lc is None:
                    return False
                if not LC:
                    LC = LastChapter(url=manga.url, chapter_url=lc.url)
                else:
                    LC.chapter_url = lc.url
                await db.add(LC)
                return lc.url
            break


def requires_card_or_api(url: str):
    sites_base = ["comick", "mangadex", "mangabuddy"]
    for s in sites_base:
        if s in url and "api" not in url:
            return True


@bot.on_message(filters=filters.command("addsub") &
                filters.user(ALLOWED_USERS), group=1)
async def addsub_handler(client, message):
    db = DB()
    q, a = await bot_ask(message, "Give me the manga URL.")
    manga_url, manga_card = get_manga_url(a.text)
    db_manga = await db.get(MangaName, manga_url)
    if not db_manga and not manga_card:
        return await a.reply("To subscribe to this manga, kindly perform a quick search in the relevant extension.")
    if not manga_card and requires_card_or_api(manga_url):
        return await a.reply("To subscribe to this manga, kindly perform a quick search in the relevant extension OR provide the correct (api) URL.")

    q, a = await bot_ask(message, "Do you want to forcefully update the LastChapter table?\n\n<i>Answer with Yes or No.</i>")
    exist_check = a.text.lower().strip() in ["y", "yes", "true"]
    lc_url = await update_last_chapter(manga_url, exist_check=not exist_check)
    if exist_check and lc_url:
        try:
            await q.edit(f"Updated the LastChapter → `{lc_url}`")
        except BaseException:
            pass
        await asyncio.sleep(1)
    else:
        await q.delete()

    q, a = await bot_ask(message, "Give me the chat ID.")
    try:
        manga_chat = int(a.text)
    except ValueError:
        await a.reply_text("Chat ID should be an integer.")
        return

    try:
        tmp_msg = await bot.send_message(manga_chat, manga_url)
        await tmp_msg.delete()
    except BaseException:
        await a.reply_text("Bot couldn't send a message to the provided chat ID. Make sure that the bot is added correctly!")
        return

    q, a = await bot_ask(
        message,
        "Give me the file format for the chapters.\n\nYou can choose from the following options:\n\n→ <code>PDF</code>\n→ <code>CBZ</code>\n→ <code>BOTH</code>",
    )
    file_mode = a.text.lower()
    output = file_options.get(file_mode, None)
    if output is None:
        await a.reply_text("Wrong file format option. You have to choose from the given options.")
        return

    await add_manga_options(str(manga_chat), output)

    q, a = await bot_ask(
        message,
        "Send a custom caption to set on new chapter files.\n\n<i>Reply with /skip to set no caption.</i>",
    )
    custom_caption = a.text.html.strip()
    if custom_caption.lower() in ["/skip", "none"]:
        custom_caption = None

    sub = await db.get(Subscription, (manga_url, str(manga_chat)))
    if sub:
        await message.reply("Subscription already exists!")
        return

    await db.add(Subscription(url=manga_url, user_id=str(manga_chat), custom_caption=custom_caption))

    text = "**Added New Manga Subscription.**"
    text += "\n"
    text += f"\n**›› URL →** `{manga_url}`"
    text += f"\n**›› Chat →** `{manga_chat}`"
    text += f"\n**›› File Mode →** `{file_mode.upper()}`"
    text += f"\n**›› Custom File Caption →** `{custom_caption}`" if custom_caption else ""
    await message.reply(text, parse_mode=ParseMode.MARKDOWN)

    if not db_manga:
        await db.add(MangaName(url=manga_url, name=manga_card.name))


@bot.on_message(filters=filters.command("rmsub") &
                filters.user(ALLOWED_USERS), group=1)
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
    await message.reply_text("Removed the subscription.")


@bot.on_message(filters=filters.command("eval") &
                filters.user(ALLOWED_USERS), group=1)
async def _(client, message):
    status_message = await message.reply_text("Processing ...")
    try:
        cmd = message.text.markdown.split(" ", maxsplit=1)[1]
    except BaseException:
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