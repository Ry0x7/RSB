import requests
import logging
import interactions
import aiojobs
from datetime import datetime, timedelta
import asyncio
import dotenv
import os
import pymongo
import difflib
import re

dotenv.load_dotenv()

# Initialize the Discord bot
bot = interactions.Client(token=os.getenv('DISCORD_TOKEN'))

# Define API URLs
BASE_URL = 'https://gmgn.ai/defi/quotation/v1/rank/sol/pump'
SEARCH_API_BASE_URL = 'https://frontend-api.pump.fun/'
WALLET_COUNT_API_BASE_URL = 'https://gmgn.ai/defi/quotation/v1/tokens/tag_wallet_count/sol/'

# Connect to MongoDB
MONGO_URI = os.getenv('MONGO_URI')
mongo_client = pymongo.MongoClient(MONGO_URI)
db = mongo_client['crypto_bot']
coins_collection = db['coins']
sessions_collection = db['sessions']

# Store last data and seen coins/tickers
last_data = {"soaring": None, "new": None, "completing": None}
seen_coins = {}
seen_tickers = {}

# Set owner username for admin commands
owner_username = "chakazzz"

# Configure logging
logging.basicConfig(level=logging.INFO)

# Store running tasks and sent messages
running_tasks = {"soaring": {}, "new": {}, "completing": {}}
sent_messages = {"soaring": {}, "new": {}, "completing": {}}

# Store the last volume check for each coin
volume_check = {"soaring": {}, "new": {}, "completing": {}}

def fetch_data(url):
    """Fetch data from the specified URL."""
    logging.info(f"Fetching data from URL: {url}")
    try:
        response = requests.get(url)
        logging.info(f"Received response with status code: {response.status_code}")
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Error fetching data from {url}: {response.status_code} {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Request exception occurred: {e}")
    return None

def get_time_since_creation(created_timestamp):
    """Calculate the time since the coin was created."""
    created_time = datetime.utcnowfromtimestamp(created_timestamp)
    now = datetime.utcnow()
    time_diff = now - created_time
    
    if time_diff < timedelta(minutes=1):
        return f"{time_diff.seconds}s"
    elif time_diff < timedelta(hours=1):
        return f"{time_diff.seconds // 60}m"
    elif time_diff < timedelta(days=1):
        return f"{time_diff.seconds // 3600}h"
    else:
        return f"{time_diff.days}d"

def calculate_percentage_change(original, current):
    """Calculate the percentage change between the original and current values."""
    if original == 0:
        return "N/A", ""
    change = ((current - original) / original) * 100
    trend_indicator = "🟢" if change > 0 else "🔴" if change < 0 else ""
    return f"{change:.2f}%", trend_indicator


def is_similar(a, b, threshold=0.5):  # Lowered threshold for similarity check
    """Check if two strings are similar based on a threshold."""
    similarity = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    #logging.info(f"Comparing '{a.lower()}' with '{b.lower()}' - Similarity: {similarity}")
    return similarity > threshold

def extract_telegram_links(text):
    """Extract Telegram links from the text."""
    links = re.findall(r'(https?://t\.me/[^\s]+)|(t\.me/[^\s]+)', text)
    formatted_links = {}
    for match in links:
        full_link = match[0] or f"https://{match[1]}"
        formatted_links[full_link] = full_link.split('t.me/')[1].strip().lower()
    #logging.info(f"Extracted links: {formatted_links}")
    return formatted_links

def fetch_telegram_links(address, symbol, name):
    """Fetch Telegram links from replies API and filter valid links."""
    url = f"{SEARCH_API_BASE_URL}replies/{address}"
    data = fetch_data(url)
    logging.info(f"Fetching Telegram links for address: {address}")
    if data:
        valid_links = set()
        for reply in data:
            #logging.info(f"Processing reply text: {reply['text']}")
            links = extract_telegram_links(reply['text'])
            for full_link, telegram_link in links.items():
                try:
                    #logging.info(f"Extracted Telegram link: {telegram_link}")
                    if any(sub in telegram_link for sub in ["cto"]) and \
                       not telegram_link.startswith('+') and \
                       telegram_link not in [
                            'officialctowportal',
                            'solanaportalcto'
                       ]:
                        if full_link not in valid_links:
                            valid_links.add(full_link)
                            #logging.info(f"Valid Telegram link found: {full_link}")
                except IndexError:
                    logging.error(f"Error processing link: {full_link}")
        return filter_telegram_links(list(valid_links), symbol.lower(), name.lower())
    logging.info("No valid data found for Telegram links.")
    return []

def filter_telegram_links(links, symbol, name):
    """Filter Telegram links that contain the coin symbol or name as a substring or are similar."""
    filtered_links = []
    for link in links:
        link_name = link.split('t.me/')[1].lower()
        if symbol in link_name or name in link_name or is_similar(link_name, symbol) or is_similar(link_name, name):
            filtered_links.append(link)
    #logging.info(f"Filtered Telegram links: {filtered_links}")
    return filtered_links

def fetch_wallet_counts(address):
    """Fetch wallet counts for the specified address."""
    url = f"{WALLET_COUNT_API_BASE_URL}{address}"
    data = fetch_data(url)
    if data and data['code'] == 0:
        return data['data']
    else:
        logging.error(f"No valid data returned for wallet counts of address {address}")
    return None

def format_large_number(value):
    """Format large numbers into shorthand notation."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def format_embed(item, updated=False, trend="", percentage_change="", trend_indicator=""):
    """Format the embed message for the coin."""
    top_10_holder_rate = float(item['top_10_holder_rate']) * 100 if item['top_10_holder_rate'] is not None else 0.0
    if top_10_holder_rate >= 40:
        return None

    embed_title = f"🪙 {item['name']} (${item['symbol']})"
    trendcoin = f"**{trend}** | `{percentage_change}{trend_indicator}`" if updated else ""

    embed = interactions.Embed(title=trendcoin, color=0x00ff00)
    embed.set_author(name=embed_title)

    logo_url = item['logo']
    if 'ipfs/' in item['logo']:
        ipfs_hash = item['logo'].split('ipfs/')[-1]
        logo_url = f"https://pump.mypinata.cloud/ipfs/{ipfs_hash}"
    embed.set_thumbnail(url=logo_url)

    social_links = get_social_links(item)
    wallet_counts = fetch_wallet_counts(item['address'])

    if wallet_counts and wallet_counts['sniper_wallets'] > 5:
        logging.info(f"Token {item['address']} has more than 5 sniper wallets. Skipping.")
        return None

    embed_fields = generate_embed_fields(item, wallet_counts, social_links)
    for field_name, field_value in embed_fields.items():
        embed.add_field(name=field_name, value=field_value, inline=False)

    embed.set_footer(text="Rodent Trader ∙ DYOR ∙ Last called: " + datetime.utcnow().strftime("%I:%M:%S %p"))
    return embed

def get_social_links(item):
    """Generate social media links for the embed."""
    twitter = item.get('twitter', '')
    website = item.get('website', '')
    telegram = item.get('telegram', '')
    twitter_link = f"**[X](https://x.com/{twitter})**" if twitter else ""
    website_link = f"**[Web]({website if website.startswith('http') else 'https://' + website})**" if website else ""
    telegram_link = f"**[TG]({telegram if telegram.startswith('http') else 'https://' + telegram})**" if telegram else ""

    return " **∙** ".join(filter(None, [telegram_link, twitter_link, website_link]))

def generate_embed_fields(item, wallet_counts, social_links):
    """Generate the fields for the embed."""
    coin_info = f"```{item['address']}```\n{social_links}\n💊 **[Pump](https://pump.fun/{item['address']})**\n\n"
    market_cap = int(float(item['usd_market_cap'])) if item.get('usd_market_cap') else 'N/A'
    created_time_since = get_time_since_creation(item['created_timestamp']) if item.get('created_timestamp') else 'N/A'
    top_10_holder_rate = float(item.get('top_10_holder_rate')) * 100 if item.get('top_10_holder_rate') is not None else 0.0
    progress = float(item.get('progress', 0.0) or 0.0) * 80
    holder_count = item.get('holder_count', 'N/A')
    volume_1m = int(float(item.get('volume_1m', 0.0) or 0.0))
    reply_count = item.get('reply_count', 'N/A')
    dex_paid = item.get('dexscr_update_link', 0) == 1 or item.get('dexscr_ad', 0) == 1
    dev_sold = "✅" if item.get('creator_close', False) else "❌"
    cto_flag = "✅" if item.get('cto_flag', 0) == 1 else "❌"
    rat_trader_amount_rate = float(item.get('rat_trader_amount_rate', 0.0)) * 100

    creator_balance = int(float(item.get('creator_balance', 0.00)))

    wallet_info = (
        f"🍼 **Fresh:** `{wallet_counts['fresh_wallets']}` 🔫 **Snipers:** `{wallet_counts['sniper_wallets']}\n"
    ) if wallet_counts else ""

    telegram_field_value = "No TG Found"
    if dev_sold == "✅":
        telegram_links = fetch_telegram_links(item['address'], item['symbol'], item['name'])
        telegram_field_value = " | ".join(telegram_links) if telegram_links else "No TG Found"
        logging.info(f"Telegram links for {item['name']} ({item['symbol']}): {telegram_field_value}")


    field_value = (
        f"💎 **FDV:** `${market_cap}` 🕰️ **Age:** `{created_time_since}`\n"
        f"📈 **Progress:** `{progress:.2f}%` \n🏆 **Top10**: `{top_10_holder_rate:.2f}%`\n"
        f"👥 **Holders:** `{holder_count}` 💬 **Rp**: `{reply_count}`\n"
        f"🫅 **Dev SolBal:** `{creator_balance}`\n"
        f"**Dex paid?:** {'✅' if dex_paid else '❌'} ∙ **Dev Sold?:** {dev_sold}\n"
        f"**CTO?:** {cto_flag} ∙ **Rat Trader:** `{rat_trader_amount_rate:.2f}%`\n"
        f"\n\n\n"
    )

    other_info = (
        f"👁️ **Seen At:**`${seen_coins[(item['name'], item['symbol'])]['called_mcap']}`\n"
        f"📊 **1m-Vol:** `${volume_1m}`\n"
        f"{wallet_info}"
    )

    quick_buy = (
        f"**[GmGn](https://gmgn.ai/sol/token/Sef3AuWIF_{item['address']})** ∙ "
        f"**[Photon](https://photon-sol.tinyastro.io/en/r/@rodent0x/{item['address']})** ∙ "
        f"**[Bull](https://bullx.io/terminal?chainId=1399811149&address={item['address']})** ∙ "
        f"**[PepeB](https://t.me/pepeboost_sol04_bot?start={item['address']})** ∙ "
        f"**[Troj](https://t.me/hector_trojanbot?start=r-j3rrycr3dits-{item['address']})**"
    )

    return {
        "Coin Data": coin_info + field_value,
        "Rug Check": other_info,
        "Quick Buy": quick_buy,
        "CTO TG": telegram_field_value
    }

async def send_or_update_embed(channel, item, task_type):
    """Send or update the embed message for the coin."""
    sent_messages_task = sent_messages[task_type]
    updated = item['address'] in sent_messages_task
    trend, percentage_change, trend_indicator = "", "", ""
    
    if updated:
        previous_mcap = seen_coins[(item['name'], item['symbol'])]['called_mcap']
        current_mcap = int(float(item['usd_market_cap']))
        percentage_change, trend_indicator = calculate_percentage_change(previous_mcap, current_mcap)
        trend = "Blasting! 🚀" if current_mcap > previous_mcap else "Dipping! 💥" if current_mcap < previous_mcap else ""
        seen_coins[(item['name'], item['symbol'])]['market_cap'] = current_mcap

    embed = format_embed(item, updated, trend, percentage_change, trend_indicator)
    if not embed:
        return

    try:
        if updated:
            message_id = sent_messages_task[item['address']]
            try:
                message = await channel.fetch_message(message_id)
                if message:
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
        
        # Update volume check
        volume_check[task_type][item['address']] = {
            "last_volume": int(float(item['volume_1m'])),
            "timestamp": datetime.utcnow()
        }

    except Exception as e:
        logging.error(f"Error in send_or_update_embed: {e}")

async def delete_old_messages(channel, valid_addresses, task_type):
    """Delete old messages that are no longer valid."""
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
    """Send coins information to the channel."""
    global last_data
    params = {
        "soaring": {
            'limit': '100',
            'orderby': 'usd_market_cap',
            'direction': 'desc',
            'soaring': 'true',
            'min_volume': '5000',
            'min_marketcap': '9000',
            'max_marketcap': '50000',
            'min_holder_count': '70',
            'max_created': '2h',
        },
        "new": {
            'limit': '100',
            'orderby': 'created_timestamp',
            'direction': 'asc',
            'new_creation': 'true',
            'min_marketcap': '3800',
            'max_marketcap': '9000',
            'min_holder_count': '4',
            'max_created': '5m',
        },
        "completing": {
            'limit': '100',
            'orderby': 'usd_market_cap',
            'direction': 'desc',
            'pump': 'true',
            'min_progress': '0.65',
            'max_created': '2h',
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
                
                # Check for duplicate tickers
                if item['symbol'] in seen_tickers and seen_tickers[item['symbol']] != item['address']:
                    logging.info(f"Skipping duplicate ticker: {item['symbol']}")
                    continue
                
                # Check for 1-minute volume below 1000
                volume_1m = int(float(item.get('volume_1m', 0.0) or 0.0))
                if volume_1m < 500:
                    logging.info(f"Skipping coin {item['name']} due to low 1-minute volume: {volume_1m}")
                    continue
                
                if coin_key not in seen_coins:
                    seen_coins[coin_key] = {
                        'address': item['address'],
                        'called_mcap': int(float(item['usd_market_cap'])),
                        'market_cap': int(float(item['usd_market_cap']))
                    }
                    seen_tickers[item['symbol']] = item['address']
                    coins_collection.update_one(
                        {'address': item['address']},
                        {'$set': {
                            'name': item['name'],
                            'symbol': item['symbol'],
                            'called_mcap': int(float(item['usd_market_cap'])),
                            'called_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                        }},
                        upsert=True
                    )
                else:
                    seen_coins[coin_key]['market_cap'] = int(float(item['usd_market_cap']))
                await send_or_update_embed(channel, item, task_type)
            await delete_old_messages(channel, valid_addresses, task_type)
            sessions_collection.update_one(
                {'channel_id': channel.id, 'task_type': task_type},
                {'$set': {'valid_addresses': list(valid_addresses)}},
                upsert=True
            )
    except Exception as e:
        logging.error(f"Error in send_coins: {e}")

def build_query_url(base_url, params):
    """Build query URL from the base URL and parameters."""
    query_url = f"{base_url}?"
    for key, value in params.items():
        query_url += f"{key}={value}&"
    return query_url.strip('&')

def fetch_current_market_cap(address):
    """Fetch the current market cap for the given address."""
    url = f"{SEARCH_API_BASE_URL}{address}"
    data = fetch_data(url)
    if data and 'data' in data and len(data['data']) > 0:
        return int(float(data['data'][0]['usd_market_cap']))
    else:
        logging.error(f"No valid data returned for address {address}")
    return None

async def check_volume_movement():
    """Check if the volume is moving for each coin."""
    while True:
        for task_type, addresses in volume_check.items():
            for address, data in list(addresses.items()):
                if datetime.utcnow() - data['timestamp'] >= timedelta(minutes=2):
                    current_volume = fetch_current_volume(address)
                    if int(float(current_volume)) == data['last_volume']:
                        logging.info(f"Removing {address} from {task_type} due to no volume movement.")
                        channel_id = [k for k, v in sent_messages[task_type].items() if v == address]
                        if channel_id:
                            channel_id = channel_id[0]
                            channel = await bot.fetch_channel(channel_id)
                            await delete_message(channel, address, task_type)
                    else:
                        volume_check[task_type][address]['last_volume'] = int(float(current_volume))
                        volume_check[task_type][address]['timestamp'] = datetime.utcnow()
        await asyncio.sleep(120)

def fetch_current_volume(address):
    """Fetch the current volume for the given address."""
    url = f"{SEARCH_API_BASE_URL}{address}"
    data = fetch_data(url)
    if data and 'data' in data and len(data['data']) > 0:
        return int(float(data['data'][0]['volume_1m']))
    else:
        logging.error(f"No valid data returned for address {address}")
    return None

async def delete_message(channel, address, task_type):
    """Delete a specific message from the channel."""
    try:
        message_id = sent_messages[task_type][address]
        message = await channel.fetch_message(message_id)
        if message:
            await message.delete()
        del sent_messages[task_type][address]
        del volume_check[task_type][address]
    except interactions.errors.NotFound:
        del sent_messages[task_type][address]
        del volume_check[task_type][address]

@bot.event
async def on_ready():
    """Event handler for when the bot is ready."""
    logging.info(f'Bot logged in as {bot.me.name}')
    await resume_sessions()
    asyncio.create_task(monitor_tasks())
    asyncio.create_task(check_volume_movement())

async def resume_sessions():
    """Resume active sessions from the database."""
    active_sessions = sessions_collection.find({})
    for session in active_sessions:
        channel = await bot.fetch_channel(session['channel_id'])
        task_type = session['task_type']
        valid_addresses = set(session['valid_addresses'])
        running_tasks[task_type][channel.id] = await aiojobs.create_scheduler().spawn(loop_send_coins(channel, task_type, valid_addresses))

async def admin_command(ctx):
    """Check if the user has admin permissions."""
    guild = await bot.fetch_guild(ctx.guild_id)
    member = await guild.fetch_member(ctx.author.id)
    return ctx.author.username == owner_username or member.permissions.has(interactions.Permissions.MANAGE_GUILD | interactions.Permissions.MANAGE_CHANNELS)

async def start_task(ctx, task_type):
    """Start a task to send coin information."""
    if not await admin_command(ctx):
        await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
        return
    if ctx.channel.id in running_tasks[task_type]:
        await ctx.send(f'Task {task_type.capitalize()} is already running in this channel.', ephemeral=True)
        return
    await ctx.send(f'Grabbing {task_type.capitalize()} Coins for the BAGSS! 👜', ephemeral=True)
    scheduler = await aiojobs.create_scheduler()
    task = await scheduler.spawn(loop_send_coins(ctx.channel, task_type))
    running_tasks[task_type][ctx.channel.id] = task
    await ctx.send(f'Started sending {task_type} coin information. 📈', ephemeral=True)

@interactions.slash_command(
    name="soaring",
    description="Start sending soaring coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD | interactions.Permissions.MANAGE_CHANNELS,
    dm_permission=False
)
async def soaring(ctx):
    await start_task(ctx, "soaring")

@interactions.slash_command(
    name="completing",
    description="Start sending completing coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD | interactions.Permissions.MANAGE_CHANNELS,
    dm_permission=False
)
async def completing(ctx):
    await start_task(ctx, "completing")

@interactions.slash_command(
    name="new",
    description="Start sending newly created coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD | interactions.Permissions.MANAGE_CHANNELS,
    dm_permission=False
)
async def new(ctx):
    await start_task(ctx, "new")

@interactions.slash_command(
    name="stop",
    description="Stop sending token information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD | interactions.Permissions.MANAGE_CHANNELS,
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
                
                # Delete all previous messages for this task type in this channel
                for address, message_id in list(sent_messages[task_type].items()):
                    try:
                        message = await ctx.channel.fetch_message(message_id)
                        if message.channel_id == ctx.channel.id:
                            await message.delete()
                            del sent_messages[task_type][address]
                    except interactions.errors.NotFound:
                        del sent_messages[task_type][address]
                break  # Only stop one task type

        if stopped_any:
            await ctx.send(f'Stopped sending {task_type} token information and deleted all previous messages in this channel. ❌', ephemeral=True)
        else:
            await ctx.send('No active tasks to stop in this channel. ❌', ephemeral=True)
    except Exception as e:
        logging.error(f"Error in stop command: {e}")


@interactions.slash_command(
    name="reboot",
    description="Reboot the coin information sending loops.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD | interactions.Permissions.MANAGE_CHANNELS,
    dm_permission=False
)
async def reboot(ctx):
    try:
        if not await admin_command(ctx):
            await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
            return
        stopped_any = False
        for task_type in ["soaring", "new", "completing"]:
            if ctx.channel.id in running_tasks[task_type]:
                await running_tasks[task_type][ctx.channel.id].close()
                del running_tasks[task_type][ctx.channel.id]
                scheduler = await aiojobs.create_scheduler()
                task = await scheduler.spawn(loop_send_coins(ctx.channel, task_type))
                running_tasks[task_type][ctx.channel.id] = task
                stopped_any = True
        if stopped_any:
            await ctx.send('Rebooted the coin information sending loops. 🔄', ephemeral=True)
        else:
            await ctx.send('No active tasks to reboot. ❌', ephemeral=True)
    except Exception as e:
        logging.error(f"Error in reboot command: {e}")

@interactions.slash_command(
    name="leaderboard",
    description="Show the leaderboard of coins with highest market caps."
)
async def leaderboard(ctx):
    try:
        coins = coins_collection.find({'called_mcap': {'$gte': 55000}})
        
        leaderboard_data = []
        for coin in coins:
            current_mcap = fetch_current_market_cap(coin['address'])
            if current_mcap and current_mcap >= 55000:
                leaderboard_data.append((coin['name'], coin['symbol'], current_mcap, coin['called_mcap'], coin['called_at']))
        
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
        await ctx.send(embeds=[embed])
    except Exception as e:
        logging.error(f"Error in leaderboard command: {e}")

async def loop_send_coins(channel, task_type, valid_addresses=None):
    """Loop to continuously send coin information."""
    while True:
        try:
            await send_coins(channel, task_type)
        except Exception as e:
            logging.error(f"Error in loop_send_coins for {task_type}: {e}")
        await asyncio.sleep(3)

async def monitor_tasks():
    """Monitor tasks to ensure they are running."""
    while True:
        for task_type in ["soaring", "new", "completing"]:
            for channel_id, task in list(running_tasks[task_type].items()):
                if task.done():
                    logging.warning(f"Task for channel {channel_id} has stopped. Restarting {task_type} task...")
                    channel = await bot.fetch_channel(channel_id)
                    new_task = await aiojobs.create_scheduler().spawn(loop_send_coins(channel, task_type))
                    running_tasks[task_type][channel_id] = new_task
        await asyncio.sleep(60)

bot.start()
