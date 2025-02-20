# ---------------------------------------------------
# File Name: main.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram with user tracking.
# Author: Gagan (Modified)
# GitHub: https://github.com/devgaganin/
# Telegram: https://t.me/team_spy_pro
# YouTube: https://youtube.com/@dev_gagan
# Created: 2025-01-11
# Last Modified: 2025-02-20
# Version: 2.1.0
# License: MIT License
# ---------------------------------------------------

import time
import random
import string
import asyncio
from pyrogram import filters, Client
from devgagan import app, userrbot
from config import API_ID, API_HASH, FREEMIUM_LIMIT, PREMIUM_LIMIT, OWNER_ID, DEFAULT_SESSION
from devgagan.core.get_func import get_msg
from devgagan.core.func import *
from devgagan.core.mongo import db
from pyrogram.errors import FloodWait
from datetime import datetime, timedelta
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import subprocess
from devgagan.modules.shrink import is_user_verified

# Function to generate random names for temporary files
async def generate_random_name(length=8):
    return ''.join(random.choices(string.ascii_lowercase, k=length))

# Global dictionaries for tracking user states
users_loop = {}
interval_set = {}
batch_mode = {}

# Main function to process and upload files
async def process_and_upload_link(userbot, user_id, msg_id, link, retry_count, message):
    try:
        # Add user ID to dump message
        original_text = message.text if message.text else ""
        dump_msg = f"{original_text}\nUser ID: {user_id}\nLink: {link}"
        message.text = dump_msg
        
        await get_msg(userbot, user_id, msg_id, link, retry_count, message)
        await asyncio.sleep(15)
    finally:
        pass

# Function to check user intervals
async def check_interval(user_id, freecheck):
    if freecheck != 1 or await is_user_verified(user_id):
        return True, None

    now = datetime.now()

    if user_id in interval_set:
        cooldown_end = interval_set[user_id]
        if now < cooldown_end:
            remaining_time = (cooldown_end - now).seconds
            return False, f"Please wait {remaining_time} seconds(s) before sending another link. Alternatively, purchase premium for instant access.\n\n> Hey 👋 You can use /token to use the bot free for 3 hours without any time limit.\n\nUser ID: {user_id}"
        else:
            del interval_set[user_id]

    return True, None

# Function to set interval for users
async def set_interval(user_id, interval_minutes=45):
    now = datetime.now()
    interval_set[user_id] = now + timedelta(seconds=interval_minutes)

# Initialize userbot client
async def initialize_userbot(user_id):
    data = await db.get_data(user_id)
    if data and data.get("session"):
        try:
            device = 'iPhone 16 Pro'
            userbot = Client(
                "userbot",
                api_id=API_ID,
                api_hash=API_HASH,
                device_model=device,
                session_string=data.get("session")
            )
            await userbot.start()
            return userbot
        except Exception:
            await app.send_message(user_id, f"Login Expired re do login\nUser ID: {user_id}")
            return None
    else:
        if DEFAULT_SESSION:
            return userrbot
        else:
            return None

# Function to check if link is a normal Telegram link
async def is_normal_tg_link(link: str) -> bool:
    special_identifiers = ['t.me/+', 't.me/c/', 't.me/b/', 'tg://openmessage']
    return 't.me/' in link and not any(x in link for x in special_identifiers)

# Function to process special Telegram links
async def process_special_links(userbot, user_id, msg, link):
    if userbot is None:
        return await msg.edit_text(f"Try logging in to the bot and try again.\nUser ID: {user_id}")
    
    if 't.me/+' in link:
        result = await userbot_join(userbot, link)
        await msg.edit_text(f"{result}\nUser ID: {user_id}")
        return
        
    special_patterns = ['t.me/c/', 't.me/b/', '/s/', 'tg://openmessage']
    if any(sub in link for sub in special_patterns):
        msg.text = f"Processing special link...\nUser ID: {user_id}"  # Add user ID to message text
        await process_and_upload_link(userbot, user_id, msg.id, link, 0, msg)
        await set_interval(user_id, interval_minutes=45)
        return
        
    await msg.edit_text(f"Invalid link...\nUser ID: {user_id}")

# Handler for single link processing
@app.on_message(
    filters.regex(r'https?://(?:www\.)?t\.me/[^\s]+|tg://openmessage\?user_id=\w+&message_id=\d+')
    & filters.private
)
async def single_link(_, message):
    user_id = message.chat.id

    if await subscribe(_, message) == 1 or user_id in batch_mode:
        return

    if users_loop.get(user_id, False):
        await message.reply(
            f"You already have an ongoing process. Please wait for it to finish or cancel it with /cancel.\nUser ID: {user_id}"
        )
        return

    if await chk_user(message, user_id) == 1 and FREEMIUM_LIMIT == 0 and user_id not in OWNER_ID and not await is_user_verified(user_id):
        await message.reply(f"Freemium service is currently not available. Upgrade to premium for access.\nUser ID: {user_id}")
        return

    can_proceed, response_message = await check_interval(user_id, await chk_user(message, user_id))
    if not can_proceed:
        await message.reply(response_message)
        return

    users_loop[user_id] = True
    link = message.text if "tg://openmessage" in message.text else get_link(message.text)
    msg = await message.reply(f"Processing...\nUser ID: {user_id}")
    userbot = await initialize_userbot(user_id)
    
    try:
        if await is_normal_tg_link(link):
            # Add user ID to message text before processing
            message.text = f"{message.text}\nUser ID: {user_id}"
            await process_and_upload_link(userbot, user_id, msg.id, link, 0, message)
            await set_interval(user_id, interval_minutes=45)
        else:
            await process_special_links(userbot, user_id, msg, link)
            
    except FloodWait as fw:
        await msg.edit_text(f'Try again after {fw.x} seconds due to floodwait from Telegram.\nUser ID: {user_id}')
    except Exception as e:
        await msg.edit_text(f"Link: `{link}`\n\n**Error:** {str(e)}\nUser ID: {user_id}")
    finally:
        users_loop[user_id] = False
        try:
            await msg.delete()
        except Exception:
            pass

# Handler for batch processing
@app.on_message(filters.command("batch") & filters.private)
async def batch_link(_, message):
    join = await subscribe(_, message)
    if join == 1:
        return

    user_id = message.chat.id
    if users_loop.get(user_id, False):
        await app.send_message(
            message.chat.id,
            f"You already have a batch process running. Please wait for it to complete.\nUser ID: {user_id}"
        )
        return

    freecheck = await chk_user(message, user_id)
    if freecheck == 1 and FREEMIUM_LIMIT == 0 and user_id not in OWNER_ID and not await is_user_verified(user_id):
        await message.reply(f"Freemium service is currently not available. Upgrade to premium for access.\nUser ID: {user_id}")
        return

    max_batch_size = FREEMIUM_LIMIT if freecheck == 1 else PREMIUM_LIMIT

    # Get start link
    for attempt in range(3):
        start = await app.ask(message.chat.id, f"Please send the start link.\n\n> Maximum tries 3\nUser ID: {user_id}")
        start_id = start.text.strip()
        s = start_id.split("/")[-1]
        if s.isdigit():
            cs = int(s)
            break
        await app.send_message(message.chat.id, f"Invalid link. Please send again ...\nUser ID: {user_id}")
    else:
        await app.send_message(message.chat.id, f"Maximum attempts exceeded. Try later.\nUser ID: {user_id}")
        return

    # Get number of messages
    for attempt in range(3):
        num_messages = await app.ask(
            message.chat.id,
            f"How many messages do you want to process?\n> Max limit {max_batch_size}\nUser ID: {user_id}"
        )
        try:
            cl = int(num_messages.text.strip())
            if 1 <= cl <= max_batch_size:
                break
            raise ValueError()
        except ValueError:
            await app.send_message(
                message.chat.id,
                f"Invalid number. Please enter a number between 1 and {max_batch_size}.\nUser ID: {user_id}"
            )
    else:
        await app.send_message(message.chat.id, f"Maximum attempts exceeded. Try later.\nUser ID: {user_id}")
        return

    can_proceed, response_message = await check_interval(user_id, freecheck)
    if not can_proceed:
        await message.reply(response_message)
        return

    join_button = InlineKeyboardButton("Join Channel", url="https://t.me/joinnexuz")
    keyboard = InlineKeyboardMarkup([[join_button]])
    pin_msg = await app.send_message(
        user_id,
        f"Batch process started ⚡\nUser ID: {user_id}\nProcessing: 0/{cl}\n\n**Powered by Team NEXUZ**",
        reply_markup=keyboard
    )
    await pin_msg.pin(both_sides=True)

    users_loop[user_id] = True
    try:
        normal_links_handled = False
        userbot = await initialize_userbot(user_id)
        
        # Handle normal links
        for i in range(cs, cs + cl):
            if user_id in users_loop and users_loop[user_id]:
                url = f"{'/'.join(start_id.split('/')[:-1])}/{i}"
                link = get_link(url)
                if 't.me/' in link and not any(x in link for x in ['t.me/b/', 't.me/c/', 'tg://openmessage']):
                    msg = await app.send_message(message.chat.id, f"Processing...\nUser ID: {user_id}")
                    message.text = f"Processing batch message {i-cs+1}/{cl}\nUser ID: {user_id}"  # Add user ID to message text
                    await process_and_upload_link(userbot, user_id, msg.id, link, 0, message)
                    await pin_msg.edit_text(
                        f"Batch process started ⚡\nUser ID: {user_id}\nProcessing: {i - cs + 1}/{cl}\n\n**__Powered by Team NEXUZ__**",
                        reply_markup=keyboard
                    )
                    normal_links_handled = True

        if normal_links_handled:
            await set_interval(user_id, interval_minutes=300)
            await pin_msg.edit_text(
                f"Batch completed successfully for {cl} messages 🎉\nUser ID: {user_id}\n\n**__Powered by Team NEXUZ__**",
                reply_markup=keyboard
            )
            await app.send_message(message.chat.id, f"Batch completed successfully! 🎉\nUser ID: {user_id}")
            return

        # Handle special links
        for i in range(cs, cs + cl):
            if not userbot:
                await app.send_message(message.chat.id, f"Login in bot first ...\nUser ID: {user_id}")
                users_loop[user_id] = False
                return
                
            if user_id in users_loop and users_loop[user_id]:
                url = f"{'/'.join(start_id.split('/')[:-1])}/{i}"
                link = get_link(url)
                if any(x in link for x in ['t.me/b/', 't.me/c/']):
                    msg = await app.send_message(message.chat.id, f"Processing...\nUser ID: {user_id}")
                    message.text = f"Processing batch message {i-cs+1}/{cl}\nUser ID: {user_id}"  # Add user ID to message text
                    await process_and_upload_link(userbot, user_id, msg.id, link, 0, message)
                    await pin_msg.edit_text(
                        f"Batch process started ⚡\nUser ID: {user_id}\nProcessing: {i - cs + 1}/{cl}\n\n**__Powered by Team NEXUZ__**",
                        reply_markup=keyboard
                    )

        await set_interval(user_id, interval_minutes=300)
        await pin_msg.edit_text(
            f"Batch completed successfully for {cl} messages 🎉\nUser ID: {user_id}\n\n**__Powered by Team NEXUZ__**",
            reply_markup=keyboard
        )
        await app.send_message(message.chat.id, f"Batch completed successfully! 🎉\nUser ID: {user_id}")

    except Exception as e:
        await app.send_message(message.chat.id, f"Error: {e}\nUser ID: {user_id}")
    finally:
        users_loop.pop(user_id, None)
        
# Handler for canceling batch processes
@app.on_message(filters.command("cancel"))
async def stop_batch(_, message):
    user_id = message.chat.id

    if user_id in users_loop and users_loop[user_id]:
        users_loop[user_id] = False
        await app.send_message(
            message.chat.id,
            f"Batch processing has been stopped successfully. You can start a new batch now if you want.\nUser ID: {user_id}"
        )
    elif user_id in users_loop and not users_loop[user_id]:
        await app.send_message(
            message.chat.id,
            f"The batch process was already stopped. No active batch to cancel.\nUser ID: {user_id}"
        )
    else:
        await app.send_message(
            message.chat.id,
            f"No active batch processing is running to cancel.\nUser ID: {user_id}"
)
