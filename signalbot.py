import requests
import logging
import interactions
import aiojobs
from datetime import datetime, timedelta
import asyncio
import random

# Correct token and default_scope initialization
bot = interactions.Client(
    token="MTI1OTA5MjEwNzk0NDAwNTcwNA.GdiQza.BpS494-GNqNLsKkHAUvVWo6MM0UhABVmAf40Jk",
    default_scope=1259094394397790231
)

BASE_URL = 'https://gmgn.ai/defi/quotation/v1/rank/sol/pump'

last_soaring_data = None
last_new_data = None
owner_username = "chakazzz"

logging.basicConfig(level=logging.INFO)

# Dictionary to keep track of running tasks and sent messages
running_tasks = {}
sent_messages = {}
sent_coins = set()

def fetch_data(url):
    logging.info(f"Fetching data from URL: {url}")
    response = requests.get(url)
    logging.info(f"Received response with status code: {response.status_code}")
    if response.status_code == 200:
        return response.json()
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

def format_embed(item, title, updated=False):
    if not item['address'].endswith('pump'):
        return None

    embed_title = title
    if updated:
        embed_title = f"Updated {title}"

    embed = interactions.Embed(
        title=embed_title,
        color=0x00ff00
    )

    photon_link = f"https://photon-sol.tinyastro.io/en/r/@RickBurpBot/{item['address']}"
    bullx_link = f"https://bullx.io/terminal?chainId=1399811149&address={item['address']}&r=M7B0AY33YBS"
    solscan_dev_link = f"https://solscan.io/account/{item['creator']}"
    solscan_token_link = f"https://solscan.io/account/{item['address']}"
    dex_paid = item.get('dexscr_ad', 0) == 1
    dev_sold = "✅" if item.get('creator_close', False) else "❌"
    top_10_holder_rate = float(item['top_10_holder_rate']) * 100 if item['top_10_holder_rate'] is not None else 0.0
    created_time_since = get_time_since_creation(item['created_timestamp']) if item.get('created_timestamp') else 'N/A'
    creator_balance = f"{float(item.get('creator_balance', 0.0) or 0.0):.2f}"
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

    embed.add_field(
        name=f"{item['name']} [{item['symbol']}]",
        value=(
            f"---\n"
            f"💎 **MCAP:** `${market_cap}`  🕰️ **Created:** `{created_time_since}` 📊 **5-Min Volume:** `${volume_5m}`\n"
            f"👥 **Holders:** {holder_count}\n"
            f"💬 **Reply Count:** {reply_count}\n"
            f"🏆 **Top 10 Holders Rate:** `{top_10_holder_rate:.2f}%`\n"
            f"👤 **[Creator Address]({solscan_dev_link})** (Sol Balance: `{creator_balance}`)\n"
            f"💸 **Dexpaid:** {'✅' if dex_paid else '❌'}\n"
            f"🛠️ **Dev Sold?:** {dev_sold}\n"
            f"📈 **Bonding Curve Progress:** `{progress:.2f}%`\n"
            f"---\n"
            f"```{item['address']}```\n"
            f"[PHOTON: {item['address']}]({photon_link})\n"
            f"[BULLX: {item['address']}]({bullx_link})\n"
            f"{social_links}\n\n"
            f"Donations Accepted/Encouraged\n"
            f"`Rodent: 7w36xSwuJg4gLGPWje6iEyt9EY4vpgpYaew1BJgmn7bu`\n"
            f"For Business Inquiries: https://t.me/j3rrycr3dits\n"
        ),
        inline=False
    )
    return embed

async def send_or_update_embed(channel, item, title):
    embed = format_embed(item, title, updated=item['address'] in sent_messages)
    if not embed:
        return
    
    if item['address'] in sent_messages:
        message_id = sent_messages[item['address']]
        try:
            message = await channel.fetch_message(message_id)
            if message is not None:
                await message.edit(embeds=[embed])
            else:
                raise interactions.errors.NotFound
        except interactions.errors.NotFound:
            del sent_messages[item['address']]
            sent_coins.discard(item['address'])
            message = await channel.send(embeds=[embed])
            sent_messages[item['address']] = message.id
            sent_coins.add(item['address'])
    else:
        message = await channel.send(embeds=[embed])
        sent_messages[item['address']] = message.id
        sent_coins.add(item['address'])

async def delete_removed_coins(channel, current_coins):
    for address in list(sent_coins):
        if address not in current_coins:
            try:
                message_id = sent_messages[address]
                message = await channel.fetch_message(message_id)
                if message is not None:
                    await message.delete()
                del sent_messages[address]
                sent_coins.remove(address)
            except interactions.errors.NotFound:
                del sent_messages[address]
                sent_coins.remove(address)

async def send_coins(channel, params, title):
    url = build_query_url(BASE_URL, params)
    data = fetch_data(url)
    current_coins = set()
    if data:
        for item in data['data']['rank']:
            current_coins.add(item['address'])
            await send_or_update_embed(channel, item, title)
    await delete_removed_coins(channel, current_coins)

async def send_soaring_coins(channel):
    params = {
        'limit': '50',
        'orderby': 'created_timestamp',
        'direction': 'desc',
        'soaring': 'true',
        'min_marketcap': '5000',
        'max_marketcap': '25000',
        'min_holder_count': '25',
        'min_volume': '1000',
    }
    await send_coins(channel, params, "🚀 Soaring Coin")

async def send_new_created_coins(channel):
    params = {
        'limit': '50',
        'orderby': 'created_timestamp',
        'direction': 'desc',
        'new_creation': 'true',
        'max_marketcap': '10000',
        'min_holder_count': '15',
    }
    await send_coins(channel, params, "🌟 Newly Created Coin")

def build_query_url(base_url, params):
    query_url = f"{base_url}?"
    for key, value in params.items():
        query_url += f"{key}={value}&"
    return query_url.strip('&')

@bot.event
async def on_ready():
    logging.info(f'Bot logged in as {bot.me.name}')

@interactions.slash_command(
    name="soaring",
    description="Start sending soaring coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def soaring(ctx):
    if not await admin_command(ctx):
        await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
        return
    await ctx.send('Grabbing Soaring Coins for the BAGSS! 👜', ephemeral=True)
    scheduler = await aiojobs.create_scheduler()
    task = await scheduler.spawn(loop_send_soaring_coins(ctx.channel))
    running_tasks[ctx.channel.id] = task
    await ctx.send('Started sending soaring coin information. 📈', ephemeral=True)

@interactions.slash_command(
    name="new",
    description="Start sending newly created coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def new(ctx):
    if not await admin_command(ctx):
        await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
        return
    await ctx.send('Grabbing Newly Created Coins for the BAGSS! 👜', ephemeral=True)
    scheduler = await aiojobs.create_scheduler()
    task = await scheduler.spawn(loop_send_new_created_coins(ctx.channel))
    running_tasks[ctx.channel.id] = task
    await ctx.send('Started sending newly created coin information. 📈', ephemeral=True)

@interactions.slash_command(
    name="stop",
    description="Stop sending token information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def stop(ctx):
    if not await admin_command(ctx):
        await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
        return
    if ctx.channel.id in running_tasks:
        await running_tasks[ctx.channel.id].close()
        del running_tasks[ctx.channel.id]
        await ctx.send('Stopped sending token information. ❌', ephemeral=True)
    else:
        await ctx.send('No active tasks to stop. ❌', ephemeral=True)

@interactions.slash_command(
    name="reboot",
    description="Reboot the coin information sending loops.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def reboot(ctx):
    if not await admin_command(ctx):
        await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
        return
    if ctx.channel.id in running_tasks:
        await running_tasks[ctx.channel.id].close()
        del running_tasks[ctx.channel.id]
    scheduler = await aiojobs.create_scheduler()
    task = await scheduler.spawn(loop_send_soaring_coins(ctx.channel))
    running_tasks[ctx.channel.id] = task
    await ctx.send('Rebooted the coin information sending loops. 🔄', ephemeral=True)

async def loop_send_soaring_coins(channel):
    while True:
        await send_soaring_coins(channel)
        await asyncio.sleep(4)  # Wait for 4 seconds before sending the next update

async def loop_send_new_created_coins(channel):
    while True:
        await send_new_created_coins(channel)
        await asyncio.sleep(4)  # Wait for 4 seconds before sending the next update

async def monitor_tasks():
    while True:
        for channel_id, task in list(running_tasks.items()):
            if task.done():
                logging.warning(f"Task for channel {channel_id} has stopped. Restarting...")
                channel = await bot.fetch_channel(channel_id)
                scheduler = await aiojobs.create_scheduler()
                new_task = await scheduler.spawn(loop_send_soaring_coins(channel))
                running_tasks[channel_id] = new_task
        await asyncio.sleep(60)  # Check every minute

asyncio.create_task(monitor_tasks())
bot.start()