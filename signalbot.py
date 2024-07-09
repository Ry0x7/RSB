import requests
import logging
import interactions
import aiojobs
from datetime import datetime, timedelta
import asyncio
import dotenv
import os
import sqlite3

dotenv.load_dotenv()

bot = interactions.Client(token=os.getenv('DISCORD_TOKEN'))

BASE_URL = 'https://gmgn.ai/defi/quotation/v1/rank/sol/pump'
SEARCH_API_BASE_URL = 'https://gmgn.ai/defi/quotation/v1/tokens/sol/search?q='
REPLY_API_BASE_URL = 'https://frontend-api.pump.fun/replies/'
USER_API_BASE_URL = 'https://frontend-api.pump.fun/users/'

last_data = {
    "soaring": None,
    "new": None,
    "completing": None
}
owner_username = "chakazzz"

logging.basicConfig(level=logging.INFO)

conn = sqlite3.connect('coins.db')
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS coins (
        address TEXT PRIMARY KEY,
        name TEXT,
        symbol TEXT,
        called_mcap INTEGER,
        called_at TEXT
    )
''')
conn.commit()

running_tasks = {
    "soaring": {},
    "new": {},
    "completing": {}
}
sent_messages = {
    "soaring": {},
    "new": {},
    "completing": {}
}

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

def fetch_user_data(user_id):
    url = f"{USER_API_BASE_URL}{user_id}"
    response = fetch_data(url)
    if response:
        return response
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
    message_time = datetime.utcfromtimestamp(timestamp / 1000)
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

def calculate_percentage_change(original, current):
    if original == 0:
        return "N/A", ""
    change = ((current - original) / original) * 100
    trend_indicator = "🟢" if change > 0 else "🔴" if change < 0 else ""
    return f"{change:.2f}%", trend_indicator

def format_embed(item, title, task_type, updated=False, trend="", percentage_change="", trend_indicator=""):
    if not item['address'].endswith('pump'):
        return None

    top_10_holder_rate = float(item['top_10_holder_rate']) * 100 if item['top_10_holder_rate'] is not None else 0.0
    if top_10_holder_rate >= 40:
        return None

    embed_title = title
    if updated:
        embed_title = f"{trend} {title}"

    coin_key = (item['name'], item['symbol'])
    is_duplicate = coin_key in seen_coins and seen_coins[coin_key] != item['address']
    if is_duplicate:
        embed_title += " (Duplicated Coin)"

    reply = fetch_replies(item['address'])
    cto_info = ""
    if reply:
        embed_title += " (CTO?)"
        user_data = fetch_user_data(reply['user'])
        if user_data and user_data['likes_received'] > 100 and user_data['mentions_received'] > 10 and user_data['followers'] > 10:
            cto_info = (
                f"**CTO Username (Verify First):** {user_data['username']}\n"
                f"[Profile](https://pump.fun/profile/{reply['user']})\n"
                f"**Sent:** {get_time_since_message(reply['timestamp'])}\n"
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
    created_time_since = get_time_since_creation(item['created_timestamp']) if item.get(['created_timestamp']) else 'N/A'
    holder_count = item.get('holder_count', 'N/A')
    volume_5m = f"{float(item.get('volume_5m', 0.0) or 0.0):.2f}"
    market_cap = int(item['usd_market_cap']) if item.get('usd_market_cap') else 'N/A'
    progress = float(item.get('progress', 0.0) or 0.0) * 100
    reply_count = item.get('reply_count', 'N/A')

    twitter = item.get('twitter', '')
    website = item.get('website', '')
    telegram = item.get('telegram', '')

    twitter_link = f"[X](https://x.com/{twitter})" if twitter else ""
    website_link = f"[Web]({website if website.startswith('http') else 'https://' + website})" if website else ""
    telegram_link = f"[TG]({telegram if telegram.startswith('http') else 'https://' + telegram})" if telegram else ""

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
        f"👁️ First seen at `${seen_coins[coin_key]['called_mcap']}` | `{percentage_change} {trend_indicator}`\n"
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

async def send_or_update_embed(channel, item, title, task_type):
    sent_messages_task = sent_messages[task_type]
    updated = item['address'] in sent_messages_task
    trend = ""
    percentage_change = ""
    trend_indicator = ""
    if updated:
        previous_mcap = seen_coins[(item['name'], item['symbol'])]['called_mcap']
        current_mcap = int(item['usd_market_cap'])
        percentage_change, trend_indicator = calculate_percentage_change(seen_coins[(item['name'], item['symbol'])]['called_mcap'], current_mcap)
        if current_mcap > previous_mcap:
            trend = "Uptrend 📈"
        elif current_mcap < previous_mcap:
            trend = "Downtrend 📉"
        seen_coins[(item['name'], item['symbol'])]['market_cap'] = current_mcap

    embed = format_embed(item, title, task_type, updated, trend, percentage_change, trend_indicator)
    if not embed:
        return
    
    try:
        if updated:
            message_id = sent_messages_task[item['address']]
            try:
                message = await channel.fetch_message(message_id)
                if message is not None:
                    await message.edit(embeds=[embed])
                else:
                    del sent_messages_task[item['address']]
                    message = await channel.send(embeds=[embed])
                    sent_messages_task[item['address']] = message.id
            except interactions.errors.NotFound:
                del sent_messages_task[item['address']]
                message = await channel.send(embeds=[embed])
                sent_messages_task[item['address']] = message.id
        else:
            message = await channel.send(embeds=[embed])
            sent_messages_task[item['address']] = message.id
    except Exception as e:
        logging.error(f"Error in send_or_update_embed: {e}")

async def delete_old_messages(channel, valid_addresses, task_type):
    sent_messages_task = sent_messages[task_type]
    for address, message_id in list(sent_messages_task.items()):
        if address not in valid_addresses:
            try:
                message = await channel.fetch_message(message_id)
                if message:
                    await message.delete()
                del sent_messages_task[address]
            except interactions.errors.NotFound:
                del sent_messages_task[address]

async def send_coins(channel, task_type):
    global last_data
    params = {
        "soaring": {
            'limit': '50',
            'orderby': 'progress',
            'direction': 'desc',
            'soaring': 'true',
            'min_marketcap': '9000',
            'max_marketcap': '30000',
            'filters[]': 'has_socials',
            'min_holder_count': '50',
        },
        "new": {
            'limit': '50',
            'orderby': 'usd_market_cap',
            'direction': 'desc',
            'new_creation': 'true',
            'filters[]': 'has_socials',
            'min_marketcap': '4000',
            'max_marketcap': '15000',
            'min_volume': '1000',
            'min_holder_count': '18',
        },
        "completing": {
            'limit': '50',
            'orderby': 'usd_market_cap',
            'direction': 'desc',
            'pump': 'true',
            'min_marketcap': '30000',
            'max_marketcap': '59000',
            'min_holder_count': '80',
            'filters[]': 'has_socials',
            'min_volume': '2000',
        }
    }
    try:
        url = build_query_url(BASE_URL, params[task_type])
        data = fetch_data(url)
        if data and data['data']['rank'] != last_data[task_type]:
            last_data[task_type] = data['data']['rank']
            valid_addresses = {item['address'] for item in data['data']['rank']}
            for item in data['data']['rank']:
                coin_key = (item['name'], item['symbol'])
                if coin_key not in seen_coins:
                    seen_coins[coin_key] = {
                        'address': item['address'],
                        'called_mcap': int(item['usd_market_cap']),
                        'market_cap': int(item['usd_market_cap'])
                    }
                    c.execute('INSERT OR REPLACE INTO coins (address, name, symbol, called_mcap, called_at) VALUES (?, ?, ?, ?, ?)', 
                              (item['address'], item['name'], item['symbol'], int(item['usd_market_cap']), datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
                    conn.commit()
                else:
                    seen_coins[coin_key]['market_cap'] = int(item['usd_market_cap'])
                await send_or_update_embed(channel, item, f"🚀 {task_type.capitalize()} Coin", task_type)
            await delete_old_messages(channel, valid_addresses, task_type)
    except Exception as e:
        logging.error(f"Error in send_coins: {e}")

def build_query_url(base_url, params):
    query_url = f"{base_url}?"
    for key, value in params.items():
        query_url += f"{key}={value}&"
    return query_url.strip('&')

def fetch_current_market_cap(address):
    url = f"{SEARCH_API_BASE_URL}{address}"
    data = fetch_data(url)
    if data and 'data' in data and len(data['data']) > 0:
        return int(data['data'][0]['usd_market_cap'])
    return None

@bot.event
async def on_ready():
    logging.info(f'Bot logged in as {bot.me.name}')
    asyncio.create_task(monitor_tasks())

async def admin_command(ctx):
    guild = await bot.fetch_guild(ctx.guild_id)
    member = await guild.fetch_member(ctx.author.id)
    return ctx.author.username == owner_username or member.permissions.has(interactions.Permissions.MANAGE_GUILD)

async def start_task(ctx, task_type):
    if not await admin_command(ctx):
        await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
        return
    await ctx.send(f'Grabbing {task_type.capitalize()} Coins for the BAGSS! 👜', ephemeral=True)
    scheduler = await aiojobs.create_scheduler()
    task = await scheduler.spawn(loop_send_coins(ctx.channel, task_type))
    running_tasks[task_type][ctx.channel.id] = task
    await ctx.send(f'Started sending {task_type} coin information. 📈', ephemeral=True)

@interactions.slash_command(
    name="soaring",
    description="Start sending soaring coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def soaring(ctx):
    await start_task(ctx, "soaring")

@interactions.slash_command(
    name="completing",
    description="Start sending completing coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def completing(ctx):
    await start_task(ctx, "completing")

@interactions.slash_command(
    name="new",
    description="Start sending newly created coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def new(ctx):
    await start_task(ctx, "new")

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
        for task_type in ["soaring", "completing"]:
            task = await scheduler.spawn(loop_send_coins(ctx.channel, task_type))
            running_tasks[task_type][ctx.channel.id] = task
        await ctx.send('Rebooted the coin information sending loops. 🔄', ephemeral=True)
    except Exception as e:
        logging.error(f"Error in reboot command: {e}")

@interactions.slash_command(
    name="leaderboard",
    description="Show the leaderboard of coins with highest market caps."
)
async def leaderboard(ctx):
    try:
        c.execute("SELECT address, name, symbol, called_mcap, called_at FROM coins WHERE called_mcap >= 55000")
        rows = c.fetchall()
        
        leaderboard_data = []
        for row in rows:
            current_mcap = fetch_current_market_cap(row[0])
            if current_mcap and current_mcap >= 55000:
                leaderboard_data.append((row[1], row[2], current_mcap, row[3], row[4]))
        
        leaderboard_data.sort(key=lambda x: x[2], reverse=True)  # Sort by current market cap
        
        embed = interactions.Embed(
            title="Leaderboard of Coins with Highest Market Caps",
            color=0xFFD700
        )
        for rank, data in enumerate(leaderboard_data[:10], start=1):  # Limit to top 10
            embed.add_field(
                name=f"{rank}. {data[0]} ({data[1]})",
                value=f"Current MCAP: ${data[2]:,}\nCalled at ${data[3]:,} on {data[4]}",
                inline=False
            )
        await ctx.send(embeds=[embed], ephemeral=True)
    except Exception as e:
        logging.error(f"Error in leaderboard command: {e}")

async def loop_send_coins(channel, task_type):
    while True:
        try:
            await send_coins(channel, task_type)
        except Exception as e:
            logging.error(f"Error in loop_send_coins for {task_type}: {e}")
        await asyncio.sleep(4)

async def monitor_tasks():
    while True:
        for task_type in ["soaring", "new", "completing"]:
            for channel_id, task in list(running_tasks[task_type].items()):
                if task.done():
                    logging.warning(f"Task for channel {channel_id} has stopped. Restarting {task_type} task...")
                    channel = await bot.fetch_channel(channel_id)
                    scheduler = await aiojobs.create_scheduler()
                    new_task = await scheduler.spawn(loop_send_coins(channel, task_type))
                    running_tasks[task_type][channel_id] = new_task
        await asyncio.sleep(60)

bot.start()
