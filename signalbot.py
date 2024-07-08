import requests
import logging
import interactions
import aiojobs
from datetime import datetime, timedelta
import asyncio
import dotenv
import os

dotenv.load_dotenv()

# Correct token and default_scope initialization
bot = interactions.Client(token=os.getenv('DISCORD_TOKEN'))

BASE_URL = 'https://gmgn.ai/defi/quotation/v1/rank/sol/pump'
REPLY_API_BASE_URL = 'https://frontend-api.pump.fun/replies/'

last_soaring_data = None
last_new_data = None
last_completing_data = None
owner_username = "chakazzz"

logging.basicConfig(level=logging.INFO)

# Dictionary to keep track of running tasks and sent messages
running_tasks = {
    "soaring": {},
    "new": {},
    "completing": {}
    
}
sent_soaring_messages = {}
sent_new_messages = {}
sent_completing_messages = {}

seen_coins = {}

def fetch_data(url):
    logging.info(f"Fetching data from URL: {url}")
    response = requests.get(url)
    logging.info(f"Received response with status code: {response.status_code}")
    if response.status_code == 200:
        return response.json()
    return None

def fetch_replies(token_address):
    url = f"{REPLY_API_BASE_URL}{token_address}"
    response = fetch_data(url)
    if response and isinstance(response, list):
        latest_reply = None
        latest_timestamp = 0
        for reply in response:
            if any(keyword in reply['text'] for keyword in ["OFFICIAL CTO IS", "DEX ADS GETTING PAID BY CTO", "CTO IS HERE", "CTO"]):
                if reply['timestamp'] > latest_timestamp:
                    latest_reply = reply
                    latest_timestamp = reply['timestamp']
        return latest_reply
    return None

def get_time_since_creation(created_timestamp):
    created_time = datetime.utcfromtimestamp(created_timestamp)
    now = datetime.utcnow()
    time_diff = now - created_time
    
    if time_diff < timedelta(minutes=1):
        return f"{time_diff.seconds} seconds ago"
    elif time_diff < timedelta(hours=1):
        return f"{time_diff.seconds // 60} minutes ago"
    elif time_diff < timedelta(days=1):
        return f"{time_diff.seconds // 3600} hours ago"
    else:
        return f"{time_diff.days} days ago"

def get_time_since_message(timestamp):
    message_time = datetime.utcfromtimestamp(timestamp / 1000)  # Convert from milliseconds to seconds
    now = datetime.utcnow()
    time_diff = now - message_time
    
    if time_diff < timedelta(minutes=1):
        return f"{time_diff.seconds} seconds ago"
    elif time_diff < timedelta(hours=1):
        return f"{time_diff.seconds // 60} minutes ago"
    elif time_diff < timedelta(days=1):
        return f"{time_diff.seconds // 3600} hours ago"
    else:
        return f"{time_diff.days} days ago"

def format_embed(item, title, updated=False):
    if not item['address'].endswith('pump'):
        return None

    top_10_holder_rate = float(item['top_10_holder_rate']) * 100 if item['top_10_holder_rate'] is not None else 0.0
    if top_10_holder_rate >= 40:
        return None

    embed_title = title
    if updated:
        embed_title = f"Updated {title}"

    coin_key = (item['name'], item['symbol'])
    is_duplicate = coin_key in seen_coins and seen_coins[coin_key] != item['address']
    if is_duplicate:
        embed_title += " (Duplicated Coin)"

    reply = fetch_replies(item['address'])
    cto_info = ""
    if reply:
        embed_title += " (Controlled by CTO?)"
        cto_telegram = ""
        if "OFFICIAL CTO IS" in reply['text']:
            parts = reply['text'].split("OFFICIAL CTO IS")
            if len(parts) > 1:
                cto_telegram = parts[1].split()[0]
        elif "CTO IS HERE" in reply['text']:
            parts = reply['text'].split("CTO IS HERE")
            if len(parts) > 1:
                cto_telegram = parts[1].split()[0]
        elif "CTO: " in reply['text']:
            parts = reply['text'].split("CTO: ")
            if len(parts) > 1:
                cto_telegram = parts[1].split()[0]
        pumpfun_profile = f"https://pump.fun/profile/{reply['user']}"
        time_since_message = get_time_since_message(reply['timestamp'])
        cto_info = (
            f"**CTO Telegram (Verify First):** {cto_telegram}\n"
            f"**CTO Lead:** [Profile]({pumpfun_profile})\n"
            f"**Sent last:** {time_since_message}\n"
        )

    embed = interactions.Embed(
        title=embed_title,
        color=0x00ff00
    )

    photon_link = f"https://photon-sol.tinyastro.io/en/r/@RickBurpBot/{item['address']}"
    bullx_link = f"https://bullx.io/terminal?chainId=1399811149&address={item['address']}&r=M7B0AY33YBS"
    solscan_dev_link = f"https://solscan.io/account/{item['creator']}"
    dex_ad = item.get('dexscr_ad', 0) == 1
    dex_paid = item.get('dexscr_update_link', 0) == 1
    dev_sold = "✅" if item.get('creator_close', False) else "❌"
    created_time_since = get_time_since_creation(item['created_timestamp']) if item.get('created_timestamp') else 'N/A'
    holder_count = item.get('holder_count', 'N/A')
    volume_5m = f"{float(item.get('volume_5m', 0.0) or 0.0):.2f}"
    market_cap = int(item['usd_market_cap']) if item.get('usd_market_cap') else 'N/A'
    progress = float(item.get('progress', 0.0) or 0.0) * 100
    reply_count = item.get('reply_count', 'N/A')

    twitter = item.get('twitter', '')
    website = item.get('website', '')
    telegram = item.get('telegram', '')

    twitter_link = f"[X](https://x.com/{twitter})" if twitter else ""
    website_link = f"[Web]({website})" if website else ""
    telegram_link = f"[TG](https://{telegram})" if telegram else ""

    social_links = " | ".join(filter(None, [telegram_link, twitter_link, website_link]))
    if social_links:
        social_links = f"SOCIALS = {social_links}"

    field_value = (
        f"{social_links}\n"
        f"👤 **[Creator Address]({solscan_dev_link})**\n"
        f"---\n"
        f"💎 **MCAP:** `${market_cap}`  🕰️ **Created:** `{created_time_since}`\n"
        f"👥 **Holders:** `{holder_count}` 💬 **Replies** `{reply_count}` 🏆 **Top 10** `{top_10_holder_rate:.2f}%`\n"
        f"💸 **Dexpaid:** {'✅' if dex_paid else '❌'} | 🛠️ **Dev Sold?:** {dev_sold}\n"
        f"📈 **Bonding Curve Progress:** `{progress:.2f}%`  📊 **5-Min Volume:** `${volume_5m}`\n"
        f"---\n"
        f"```{item['address']}```\n"
        f"[PHOTON: {item['address']}]({photon_link})\n"
        f"[BULLX: {item['address']}]({bullx_link})\n"
    )

    if reply:
        field_value += (
            f"---\n"
            f"{cto_info}"
        )

    if len(field_value) > 1024:
        logging.warning(f"Field value for {item['address']} exceeded 1024 characters. Truncating.")
        field_value = field_value[:1021] + "..."
        
    embed.add_field(
        name=f"{item['name']} ({item['symbol']})",
        value=field_value,
        inline=False
    )

    donation_message = (
        f"Donations Accepted/Encouraged\n"
        f"`Rodent: 7w36xSwuJg4gLGPWje6iEyt9EY4vpgpYaew1BJgmn7bu`\n"
        f"For Business Inquiries: https://t.me/j3rrycr3dits\n"
    )

    embed.add_field(
        name="Donations & Business Inquiries",
        value=donation_message,
        inline=False
    )

    return embed

async def send_or_update_embed(channel, item, title, sent_messages):
    updated = item['address'] in sent_messages
    embed = format_embed(item, title, updated)
    if not embed:
        return
    
    try:
        if updated:
            message_id = sent_messages[item['address']]
            try:
                message = await channel.fetch_message(message_id)
                if message is not None:
                    await message.edit(embeds=[embed])
                else:
                    del sent_messages[item['address']]
                    message = await channel.send(embeds=[embed])
                    sent_messages[item['address']] = message.id
            except interactions.errors.NotFound:
                del sent_messages[item['address']]
                message = await channel.send(embeds=[embed])
                sent_messages[item['address']] = message.id
        else:
            message = await channel.send(embeds=[embed])
            sent_messages[item['address']] = message.id
    except Exception as e:
        logging.error(f"Error in send_or_update_embed: {e}")

async def delete_old_messages(channel, valid_addresses, sent_messages):
    for address, message_id in list(sent_messages.items()):
        if address not in valid_addresses:
            try:
                message = await channel.fetch_message(message_id)
                if message:
                    await message.delete()
                del sent_messages[address]
            except interactions.errors.NotFound:
                del sent_messages[address]

async def send_soaring_coins(channel):
    global last_soaring_data
    try:
        params = {
            'limit': '50',
            'orderby': 'progress',
            'direction': 'desc',
            'soaring': 'true',
            'min_marketcap': '9000',
            'max_marketcap': '30000',
            'filters[]': 'has_socials',
            'min_holder_count': '50',
        }
        url = build_query_url(BASE_URL, params)
        data = fetch_data(url)
        if data and data['data']['rank'] != last_soaring_data:
            last_soaring_data = data['data']['rank']
            valid_addresses = {item['address'] for item in data['data']['rank']}
            for item in data['data']['rank']:
                await send_or_update_embed(channel, item, "🚀 Soaring Coin", sent_soaring_messages)
                seen_coins[(item['name'], item['symbol'])] = item['address']
            await delete_old_messages(channel, valid_addresses, sent_soaring_messages)
    except Exception as e:
        logging.error(f"Error in send_soaring_coins: {e}")

async def send_completing_coins(channel):
    global last_completing_data
    try:
        params = {
            'limit': '50',
            'orderby': 'usd_market_cap',
            'direction': 'desc',
            'pump': 'true',
            'min_marketcap': '30000',
            'max_marketcap': '59000',
            'min_holder_count': '100',
            'filters[]': 'has_socials',
            'min_volume': '2000',
        }
        url = build_query_url(BASE_URL, params)
        data = fetch_data(url)
        if data and data['data']['rank'] != last_completing_data:
            last_completing_data = data['data']['rank']
            valid_addresses = {item['address'] for item in data['data']['rank']}
            for item in data['data']['rank']:
                await send_or_update_embed(channel, item, "🚀 BOUT TO RAY!", sent_completing_messages)
                seen_coins[(item['name'], item['symbol'])] = item['address']
            await delete_old_messages(channel, valid_addresses, sent_completing_messages)
    except Exception as e:
        logging.error(f"Error in send_completing_coins: {e}")

async def send_new_created_coins(channel):
    global last_new_data
    try:
        params = {
            'limit': '50',
            'orderby': 'usd_market_cap',
            'direction': 'desc',
            'new_creation': 'true',
            'filters[]': 'has_socials',
            'min_marketcap': '7000',
            'max_marketcap': '25000',
            'min_holder_count': '20',
        }
        url = build_query_url(BASE_URL, params)
        data = fetch_data(url)
        if data and data['data']['rank'] != last_new_data:
            last_new_data = data['data']['rank']
            valid_addresses = {item['address'] for item in data['data']['rank']}
            for item in data['data']['rank']:
                await send_or_update_embed(channel, item, "🌟 Newly Created Coin", sent_new_messages)
                seen_coins[(item['name'], item['symbol'])] = item['address']
            await delete_old_messages(channel, valid_addresses, sent_new_messages)
    except Exception as e:
        logging.error(f"Error in send_new_created_coins: {e}")

def build_query_url(base_url, params):
    query_url = f"{base_url}?"
    for key, value in params.items():
        query_url += f"{key}={value}&"
    return query_url.strip('&')

@bot.event
async def on_ready():
    logging.info(f'Bot logged in as {bot.me.name}')
    asyncio.create_task(monitor_tasks())  # Start the monitoring task

async def admin_command(ctx):
    guild = await bot.fetch_guild(ctx.guild_id)
    member = await guild.fetch_member(ctx.author.id)
    return ctx.author.username == owner_username or any(role.permissions & interactions.Permissions.MANAGE_GUILD for role in member.roles)

@interactions.slash_command(
    name="soaring",
    description="Start sending soaring coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def soaring(ctx):
    try:
        if not await admin_command(ctx):
            await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
            return
        await ctx.send('Grabbing Soaring Coins for the BAGSS! 👜', ephemeral=True)
        scheduler = await aiojobs.create_scheduler()
        task = await scheduler.spawn(loop_send_soaring_coins(ctx.channel))
        running_tasks["soaring"][ctx.channel.id] = task
        await ctx.send('Started sending soaring coin information. 📈', ephemeral=True)
    except Exception as e:
        logging.error(f"Error in soaring command: {e}")

@interactions.slash_command(
    name="completing",
    description="Start sending completing coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)

async def completing(ctx):
    try:
        if not await admin_command(ctx):
            await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
            return
        await ctx.send('Grabbing Completing Coins for the BAGSS! 👜', ephemeral=True)
        scheduler = await aiojobs.create_scheduler()
        task = await scheduler.spawn(loop_send_completing_coins(ctx.channel))
        running_tasks["completing"][ctx.channel.id] = task
        await ctx.send('Started sending completing coin information. 📈', ephemeral=True)
    except Exception as e:
        logging.error(f"Error in completing command: {e}")

@interactions.slash_command(
    name="new",
    description="Start sending newly created coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def new(ctx):
    try:
        if not await admin_command(ctx):
            await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
            return
        await ctx.send('Grabbing Newly Created Coins for the BAGSS! 👜', ephemeral=True)
        scheduler = await aiojobs.create_scheduler()
        task = await scheduler.spawn(loop_send_new_created_coins(ctx.channel))
        running_tasks["new"][ctx.channel.id] = task
        await ctx.send('Started sending newly created coin information. 📈', ephemeral=True)
    except Exception as e:
        logging.error(f"Error in new command: {e}")

@interactions.slash_command(
    name="stop",
    description="Stop sending token information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def stop(ctx):
    try:
        if not await admin_command(ctx):
            await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
            return
        stopped_any = False
        for task_type in ["soaring", "new", "completing"]:
            if ctx.channel.id in running_tasks[task_type]:
                await running_tasks[task_type][ctx.channel.id].close()
                del running_tasks[task_type][ctx.channel.id]
                stopped_any = True
        if stopped_any:
            await ctx.send('Stopped sending token information. ❌', ephemeral=True)
        else:
            await ctx.send('No active tasks to stop. ❌', ephemeral=True)
    except Exception as e:
        logging.error(f"Error in stop command: {e}")

@interactions.slash_command(
    name="reboot",
    description="Reboot the coin information sending loops.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def reboot(ctx):
    try:
        if not await admin_command(ctx):
            await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
            return
        for task_type in ["soaring", "new", "completing"]:
            if ctx.channel.id in running_tasks[task_type]:
                await running_tasks[task_type][ctx.channel.id].close()
                del running_tasks[task_type][ctx.channel.id]
        scheduler = await aiojobs.create_scheduler()
        task = await scheduler.spawn(loop_send_soaring_coins(ctx.channel))
        running_tasks["soaring"][ctx.channel.id] = task
        task = await scheduler.spawn(loop_send_completing_coins(ctx.channel))
        running_tasks["completing"][ctx.channel.id] = task
        await ctx.send('Rebooted the coin information sending loops. 🔄', ephemeral=True)
    except Exception as e:
        logging.error(f"Error in reboot command: {e}")

async def loop_send_soaring_coins(channel):
    while True:
        try:
            await send_soaring_coins(channel)
        except Exception as e:
            logging.error(f"Error in loop_send_soaring_coins: {e}")
        await asyncio.sleep(4)  # Wait for 4 seconds before sending the next update

async def loop_send_completing_coins(channel):
    while True:
        try:
            await send_completing_coins(channel)
        except Exception as e:
            logging.error(f"Error in loop_send_completing_coins: {e}")
        await asyncio.sleep(4)  # Wait for 4 seconds before sending the next update

async def loop_send_new_created_coins(channel):
    while True:
        try:
            await send_new_created_coins(channel)
        except Exception as e:
            logging.error(f"Error in loop_send_new_created_coins: {e}")
        await asyncio.sleep(4)  # Wait for 4 seconds before sending the next update

async def monitor_tasks():
    while True:
        for task_type in ["soaring", "new", "completing"]:
            for channel_id, task in list(running_tasks[task_type].items()):
                if task.done():
                    logging.warning(f"Task for channel {channel_id} has stopped. Restarting {task_type} task...")
                    channel = await bot.fetch_channel(channel_id)
                    scheduler = await aiojobs.create_scheduler()
                    if task_type == "soaring":
                        new_task = await scheduler.spawn(loop_send_soaring_coins(channel))
                    elif task_type == "new":
                        new_task = await scheduler.spawn(loop_send_new_created_coins(channel))
                    elif task_type == "completing":
                        new_task = await scheduler.spawn(loop_send_completing_coins(channel))
                    running_tasks[task_type][channel_id] = new_task
        await asyncio.sleep(60)  # Check every minute

bot.start()
