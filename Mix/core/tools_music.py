"""
RadioPlayerV3, Telegram Voice Chat Bot
Copyright (c) 2021  Asm Safone <https://github.com/AsmSafone>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>
"""

import asyncio
import os
import subprocess
from asyncio import sleep
from os import path
from random import randint
from signal import SIGINT
from typing import Optional

import wget
from pyrogram import emoji
from pyrogram.errors import *
from pyrogram.methods.messages.download_media import DEFAULT_DOWNLOAD_DIR
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.messages import GetFullChat
from pyrogram.raw.functions.phone import CreateGroupCall, EditGroupCallTitle
from pyrogram.raw.types import InputGroupCall, InputPeerChannel, InputPeerChat
from pyrogram.utils import MAX_CHANNEL_ID
from pytgcalls import GroupCallFactory
from pytgcalls.exceptions import GroupCallNotFoundError
from yt_dlp import YoutubeDL

from Mix import *

CALL_STATUS = {}
FFMPEG_PROCESSES = {}
RADIO = {6}
msg = {}
playlist = []


ydl_opts = {
    "format": "bestaudio[ext=m4a]",
    "geo-bypass": True,
    "nocheckcertificate": True,
    "verbose": True,
    "outtmpl": "downloads/%(id)s.%(ext)s",
}
ydl = YoutubeDL(ydl_opts)


async def get_group_call(c: nlx, m, err_msg: str = "") -> Optional[InputGroupCall]:
    em = Emojik()
    em.initialize()
    chat_peer = await c.resolve_peer(m)
    if isinstance(chat_peer, (InputPeerChannel, InputPeerChat)):
        if isinstance(chat_peer, InputPeerChannel):
            full_chat = (await c.invoke(GetFullChannel(channel=chat_peer))).full_chat
        elif isinstance(chat_peer, InputPeerChat):
            full_chat = (
                await c.invoke(GetFullChat(chat_id=chat_peer.chat_id))
            ).full_chat
        if full_chat is not None:
            return full_chat.call
    await m.reply_text(cgr("vc_1").format(em.gagal, err_msg))
    return False


vc = GroupCallFactory(
    nlx, GroupCallFactory.MTPROTO_CLIENT_TYPE.PYROGRAM
).get_file_group_call()


class MixPlayer:
    def __init__(self, chat=None):
        self.group_call = vc

    async def send_playlist(self, m):
        if not playlist:
            pl = f"{emoji.NO_ENTRY} **Empty Playlist!**"
        else:
            pl = f"{emoji.PLAY_BUTTON} **Playlist**:\n" + "\n".join(
                [
                    f"**{i}**. **{x[1]}**\n  - **Requested By:** {x[4]}\n"
                    for i, x in enumerate(playlist)
                ]
            )
        if msg.get("playlist") is not None:
            await msg["playlist"].delete()
        msg["playlist"] = await self.send_text(m, pl)

    async def skip_current_playing(self, m):
        if not playlist:
            return
        if len(playlist) == 1:
            await self.start_radio(m)
            return
        download_dir = os.path.join(vc.workdir, DEFAULT_DOWNLOAD_DIR)
        vc.input_filename = os.path.join(download_dir, f"{playlist[1][1]}.raw")
        # remove old track from playlist
        old_track = playlist.pop(0)
        print(f"- START PLAYING: {playlist[0][1]}")
        await self.edit_title(m)
        await self.send_playlist(m)
        os.remove(os.path.join(download_dir, f"{old_track[1]}.raw"))
        if len(playlist) == 1:
            return
        await self.download_audio(playlist[1])

    async def send_text(self, m, text):
        message = await bot.send_message(
            m, text, disable_web_page_preview=True, disable_notification=True
        )
        return message

    async def download_audio(self, song):
        client = vc.client
        raw_file = os.path.join(client.workdir, DEFAULT_DOWNLOAD_DIR, f"{song[1]}.raw")
        # if os.path.exists(raw_file):
        # os.remove(raw_file)
        if not os.path.isfile(raw_file):
            # credits: https://t.me/c/1480232458/6825
            # os.mkfifo(raw_file)
            if song[3] == "telegram":
                original_file = await nlx.download_media(f"{song[2]}")
            elif song[3] == "youtube":
                url = song[2]
                try:
                    info = ydl.extract_info(url, False)
                    ydl.download([url])
                    original_file = path.join(
                        "downloads", f"{info['id']}.{info['ext']}"
                    )
                except Exception as e:
                    playlist.pop(1)
                    print(f"Unable To Download Due To {e} & Skipped!")
                    if len(playlist) == 1:
                        return
                    await self.download_audio(playlist[1])
                    return
            else:
                original_file = wget.download(song[2])
            if original_file.endswith(".wav"):
                os.rename(original_file, raw_file)
            else:
                ffmpeg.input(original_file).output(raw_file, format="wav").run(
                    overwrite_output=True
                )
            os.remove(original_file)

    async def start_radio(self, m):
        if vc.is_connected:
            playlist.clear()
        process = FFMPEG_PROCESSES.get(m)
        if process:
            try:
                process.send_signal(SIGINT)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                print(e)
            FFMPEG_PROCESSES[m] = ""
        station_stream_url = STREAM_URL
        try:
            RADIO.remove(0)
        except:
            pass
        try:
            RADIO.add(1)
        except:
            pass
        if os.path.exists(f"radio-{m}.raw"):
            os.remove(f"radio-{m}.raw")
        # credits: https://t.me/c/1480232458/6825
        os.mkfifo(f"radio-{m}.raw")
        vc.input_filename = f"radio-{m}.raw"
        if not vc.is_connected:
            await self.start_call(m)
        ffmpeg_log = open("ffmpeg.log", "w+")
        command = [
            "ffmpeg",
            "-y",
            "-i",
            station_stream_url,
            "-f",
            "s16le",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-acodec",
            "pcm_s16le",
            vc.input_filename,
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=ffmpeg_log,
            stderr=asyncio.subprocess.STDOUT,
        )

        FFMPEG_PROCESSES[m] = process
        await self.edit_title(m)
        await sleep(2)
        while True:
            if vc.is_connected:
                print("Succesfully Joined VC !")
                break
            else:
                print("Connecting, Please Wait ...")
                await self.start_call(m)
                await sleep(10)
                continue

    async def stop_radio(self, m):

        if vc:
            playlist.clear()
            vc.input_filename = ""
            try:
                RADIO.remove(1)
            except:
                pass
            try:
                RADIO.add(0)
            except:
                pass
        process = FFMPEG_PROCESSES.get(m)
        if process:
            try:
                process.send_signal(SIGINT)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                print(e)
            FFMPEG_PROCESSES[m] = ""

    async def start_call(self, m):
        try:
            await vc.start(m)
        except FloodWait as e:
            await sleep(e.x)
            if not vc.is_connected:
                await vc.start(m)
        except GroupCallNotFoundError:
            try:
                await nlx.invoke(
                    CreateGroupCall(
                        peer=(await nlx.resolve_peer(m)),
                        random_id=randint(10000, 999999999),
                    )
                )
                await vc.start(m)
            except Exception as e:
                print(e)
        except Exception as e:
            print(e)

    async def edit_title(self, m):
        if not playlist:
            title = "🎧 Mix-Music 🎶"
        else:
            pl = playlist[0]
            title = pl[1]
        if not (group_call := (await get_group_call(nlx, m, err_msg=", Kesalahan..."))):
            return
        try:
            await nlx.invoke(EditGroupCallTitle(call=group_call, title=title))
        except Exception as e:
            print("Error Occured On Changing VC Title:", e)


mixmus = MixPlayer()

# pytgcalls handlers


@mixmus.group_call.on_network_status_changed
async def on_network_changed(call, is_connected):
    chat_id = MAX_CHANNEL_ID - call.full_chat.id
    if is_connected:
        CALL_STATUS[chat_id] = True
    else:
        CALL_STATUS[chat_id] = False


@mixmus.group_call.on_playout_ended
async def playout_ended_handler(_, m):
    if not playlist:
        await mixmus.start_radio(m)
    else:
        await mixmus.skip_current_playing(m)
