import aiohttp
import logging
import interactions
import aiojobs
from datetime import datetime, timezone, timedelta
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
TOP_BUYERS_API_BASE_URL = 'https://gmgn.ai/defi/quotation/v1/tokens/top_buyers/sol/'
FETCH_COIN_DATA = 'https://gmgn.ai/defi/quotation/v1/tokens/sol/'

# Connect to MongoDB
MONGO_URI = os.getenv('MONGO_URI')
mongo_client = pymongo.MongoClient(MONGO_URI)
db = mongo_client['crypto_bot']

# Store last data and seen coins/tickers
last_data = {}
seen_coins = {}
seen_tickers = {}

# Set owner username for admin commands
owner_username = "chakazzz"

# Configure logging
logging.basicConfig(level=logging.INFO)

# Store running tasks and sent messages
running_tasks = {}
sent_messages = {}

# Store the last volume check for each coin
volume_check = {}

# Maximum number of concurrent tasks
MAX_CONCURRENT_TASKS = 2

async def fetch_data(url):
    """Fetch data from the specified URL."""
    logging.info(f"Fetching data from URL: {url}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                logging.info(f"Received response with status code: {response.status}")
                if response.status == 200:
                    return await response.json()
                else:
                    logging.error(f"Error fetching data from {url}: {response.status} {await response.text()}")
    except aiohttp.ClientError as e:
        logging.error(f"Request exception occurred: {e}")
    return None

async def fetch_data_waf_bypass(url):
    """Fetch data from the specified URL with WAF bypass."""
    logging.info(f"Fetching data from URL with WAF bypass: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as response:
                logging.info(f"Received response with status code: {response.status}")
                if response.status == 200:
                    return await response.json()
                else:
                    logging.error(f"Error fetching data from {url}: {response.status} {await response.text()}")
    except aiohttp.ClientError as e:
        logging.error(f"Request exception occurred: {e}")
    return None

def get_time_since_creation(created_timestamp):
    """Calculate the time since the coin was created."""
    created_time = datetime.fromtimestamp(created_timestamp, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)  # Make 'now' timezone-aware
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

def calculate_profit_percentage(called_mcap, current_mcap):
    """Calculate the profit percentage based on the called and current market cap."""
    if called_mcap == 0:
        return "N/A"
    change = ((current_mcap - called_mcap) / called_mcap) * 100
    if change == -100:
        return "Loss trade🔴"
    elif change > 0:
        return f"{change:.2f}%🟢"
    elif change > 100:
        multiplier = change / 100
        return f"{multiplier:.2f}x🟢"
    else:
        return f"{change:.2f}%🔴"

def is_similar(a, b, threshold=0.4):
    """Check if two strings are similar based on a threshold."""
    similarity = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return similarity > threshold

def extract_telegram_links(text):
    """Extract Telegram links from the text."""
    links = re.findall(r'(https?://t\.me/[^\s]+)|(t\.me/[^\s]+)', text)
    formatted_links = {}
    for match in links:
        full_link = match[0] or f"https://{match[1]}"
        formatted_links[full_link] = full_link.split('t.me/')[1].strip().lower()
    return formatted_links

async def fetch_telegram_links(address, symbol, name):
    """Fetch Telegram links from replies API and filter valid links."""
    url = f"{SEARCH_API_BASE_URL}replies/{address}"
    data = await fetch_data_waf_bypass(url)
    logging.info(f"Fetching Telegram links for address: {address}")
    if data:
        valid_links = set()
        for reply in data:
            links = extract_telegram_links(reply['text'])
            # logging.info(f"Extracted Telegram links: {links}")
            for full_link, telegram_link in links.items():
                try:
                    if any(sub in telegram_link for sub in ["cto"]) and \
                        not telegram_link.startswith('+') and \
                        telegram_link not in [
                            'officialctowportal',
                            'solanaportalcto'
                        ]:
                        valid_links.add(full_link)
                except IndexError:
                    logging.error(f"Error processing link: {full_link}")
        return filter_telegram_links(list(valid_links), symbol.lower(), name.lower())
    elif data and data['code'] == 403:
        logging.error("Access to replies API is forbidden.")
        return None
    else:
        logging.info("No valid data found for Telegram links.")
        return []

def filter_telegram_links(links, symbol, name):
    """Filter Telegram links that contain the coin symbol or name as a substring or are similar."""
    filtered_links = []
    seen_links = set()
    for link in links:
        link_name = link.split('t.me/')[1].lower()
        if (symbol in link_name or name in link_name or is_similar(link_name, symbol) or is_similar(link_name, name)) and link not in seen_links:
            filtered_links.append(link)
            seen_links.add(link)
    return filtered_links

async def check_dex_paid(address):
    """Check if the DEX is paid for the given address using the new API."""
    url = f"https://www.checkdex.xyz/api/checkToken?tokenAddress={address}"
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.6',
        'priority': 'u=1, i',
        'referer': 'https://www.checkdex.xyz/',
        'sec-ch-ua': '"Not)A;Brand";v="99", "Brave";v="127", "Chromium";v="127"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'sec-gpc': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('paid', False)
                else:
                    logging.warning(f"Error fetching DEX paid status: {response.status} {await response.text()}")
    except aiohttp.ClientError as e:
        logging.error(f"Request exception occurred: {e}")
    return False

async def fetch_wallet_counts(address):
    """Fetch wallet counts for the specified address."""
    url = f"{WALLET_COUNT_API_BASE_URL}{address}"
    data = await fetch_data(url)
    if data and data['code'] == 0:
        return data['data']
    else:
        logging.error(f"No valid data returned for wallet counts of address {address}")
    return None

async def fetch_top_buyers(address):
    """Fetch top buyers data for the specified address."""
    url = f"{TOP_BUYERS_API_BASE_URL}{address}"
    data = await fetch_data(url)
    logging.info(f"Fetching top buyers data for address: {address}")
    if data and data['code'] == 0:
        return data['data']
    else:
        logging.error(f"No valid data returned for top buyers of address {address}")
    return None

async def fetch_bubblemap_data(address):
    """Fetch bubblemap data for the specified address."""
    url = f"https://europe-west1-cryptos-tools.cloudfunctions.net/get-bubble-graph-data?token={address}&chain=sol&pumpfun=true"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 500:
                    logging.error(f"Server error occurred while fetching bubblemap data for address {address}")
                else:
                    logging.error(f"Unexpected response status {response.status} while fetching bubblemap data for address {address}")
    except aiohttp.ClientError as e:
        logging.error(f"Request exception occurred: {e}")
    return "N/A"

def count_connected_wallets(bubblemap_data):
    """Count the number of connected wallets from the bubblemap data."""
    if not bubblemap_data:
        return 0
    links = bubblemap_data.get('links', [])
    return len(links)

def format_large_number(value):
    """Format large numbers into shorthand notation."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)

def format_percentage(value):
    """Format a value as a percentage."""
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"

async def format_embed(item, updated=False, trend="", percentage_change="", trend_indicator="", ca_data=None):
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
    
    if ca_data:
        # Add fields specific to /ca command
        coin_info = ca_data.get('coin_info', '')
        field_value = ca_data.get('field_value', '')
        called_value = ca_data.get('called_value', '')
        other_info = ca_data.get('other_info', '')
        quick_buy = ca_data.get('quicksnipe', '')
        telegram_field_value = ca_data.get('telegram_field_value', '')

        embed.add_field(name="Coin Data", value=coin_info + field_value, inline=False)
        embed.add_field(name="Called Info", value=called_value, inline=False)
        embed.add_field(name="Rug Check", value=other_info, inline=False)
        embed.add_field(name="Quick Buy", value=quick_buy, inline=False)
        embed.add_field(name="CTO TG", value=telegram_field_value, inline=False)
    else:
        # Add fields specific to send_coins
        social_links = get_social_links(item)
        top_buyers = await fetch_top_buyers(item['address'])
        bubblemap_data = await fetch_bubblemap_data(item['address'])
        connected_wallets = count_connected_wallets(bubblemap_data)
        
        if top_buyers is None:
            logging.info(f"Token {item['address']} has dev_team wallets or too many snipers. Skipping.")
            return None
        
        embed_fields = await generate_embed_fields(item, social_links, top_buyers, connected_wallets)
        for field_name, field_value in embed_fields.items():
            embed.add_field(name=field_name, value=field_value, inline=False)
            
    embed.set_footer (text="❕For business inquiry DM/Add 👑@chakazzz")
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

def check_dev_sniper_tags(holders):
    """Check if there are wallets with both dev_team and sniper tags."""
    for holder in holders.get('holderInfo', []):
        if 'dev_team' in holder['maker_token_tags'] and 'sniper' in holder['maker_token_tags']:
            return True
    return False

def check_sniper_count(holders):
    """Check if there are more than 5 sniper wallets."""
    if 'holderInfo' not in holders:
        return False
    sniper_count = sum('sniper' in holder['maker_token_tags'] for holder in holders['holderInfo'])
    return sniper_count > 4

async def generate_embed_fields(item, social_links, top_buyers, connected_wallets):
    """Generate the fields for the embed."""
    coin_info = f"```{item['address']}```\n{social_links}\n💊 **[Pump](https://pump.fun/{item['address']})**\n\n"
    market_cap = format_large_number(int(float(item['usd_market_cap'])) if item.get('usd_market_cap') else 'N/A')
    created_time_since = get_time_since_creation(item['created_timestamp']) if item.get('created_timestamp') else 'N/A'
    top_10_holder_rate = float(item.get('top_10_holder_rate')) * 100 if item.get('top_10_holder_rate') is not None else 0.0
    holder_count = item.get('holder_count', 'N/A')
    volume_1m = format_large_number(int(float(item.get('volume_1m', 0.0) or 0.0)))
    dex_paid = item.get('dexscr_update_link', 0) == 1 or item.get('dexscr_ad', 0) == 1
    dev_sold = "✅" if item.get('creator_close', False) else "❌"

    creator_balance = int(float(item.get('creator_balance', 0.00)))
    creator_balance_rate = float(item.get('creator_balance_rate', 0.0)) * 100 if item.get('creator_balance_rate') is not None else None
    dev_status = "Dev Sold: ✅" if item.get('creator_close', False) else f"Dev Holds: `{creator_balance_rate:.2f}%`" if creator_balance_rate is not None else "Dev Sold: ❌"

    holders = top_buyers.get('holders', {})
    fresh_wallet_count = sum('fresh_wallet' in holder['tags'] for holder in holders.get('holderInfo', []))
    sniper_count = sum('sniper' in holder['maker_token_tags'] for holder in holders.get('holderInfo', []))
    rat_trader_count = sum('rat_trader' in holder['maker_token_tags'] for holder in holders.get('holderInfo', []))
    smart_trader_count = sum('pump_smart' in holder['tags'] for holder in holders.get('holderInfo', []))

    telegram_links = []
    telegram_field_value = "No TG Found"
    if dev_sold == "✅":
        telegram_links = await fetch_telegram_links(item['address'], item['symbol'], item['name'])
        telegram_field_value = " | ".join(telegram_links) if telegram_links else "No TG Found"
        logging.info(f"Telegram links for {item['name']} ({item['symbol']}): {telegram_field_value}")

    ctoflag = "✅" if telegram_links else "❌"
    
    dex_status_check = f"[Check Status](https://www.checkdex.xyz/{item['address']})"
    bubblemap_check = f"[Bubblemap](https://app.bubblemaps.io/sol/token/{item['address']}?pumpfun=true)"
    
    field_value = (
        f"💎 **MCAP:** `${market_cap}` 🕰️ **Age:** `{created_time_since}`\n"
        f"📊 **1m-Vol:** `${volume_1m}`\n"
        f"👁️ **Called At:** `${format_large_number(seen_coins[(item['name'], item['symbol'])]['called_mcap'])}`\n"
        f"🏆 **Top10**: `{top_10_holder_rate:.2f}%` 👥 **Holders:** `{holder_count}`\n"
        f"🫅 **Dev SolBal:** `{creator_balance}`\n"
        f"\n\n\n"
    )

    status_now = top_buyers['holders']['statusNow'] if top_buyers else {}
    buyers_info = (
        f"🕴️ Holders Count: `{holders.get('holder_count', 'N/A')}`\n"
        f"🌑 Hold: `{status_now.get('hold', 'N/A')}`\n"
        f"🌚 Bought More: `{status_now.get('bought_more', 'N/A')}`\n"
        f"🌓 Sold Part: `{status_now.get('sold_part', 'N/A')}`\n"
        f"🌕 Sold All: `{status_now.get('sold', 'N/A')}`\n"
        f"💵 Total Holdings: `{format_percentage(status_now.get('holding_rate'))}`\n"
    ) if status_now else "Top buyers data not available."

    other_info = (
        f"🍼 Fresh Wallets: `{fresh_wallet_count}`\n"
        f"🎯 Snipers: `{sniper_count}`\n"
        f"🐀 Rats: `{rat_trader_count}`\n"
        f"🧠 Smart Traders: `{smart_trader_count}`\n"
        f"🔗 Connected Wallets: `{connected_wallets}` | {bubblemap_check}\n"
        f"⚡ Dex paid?: {'✅' if dex_paid else '❌'} | {dex_status_check} \n"
        f"🧑‍💻 {dev_status}\n"
        f"🫂 CTO?: {ctoflag}\n"
    )

    quick_buy = (
        f"**[GmGn](https://gmgn.ai/sol/token/Sef3AuWIF_{item['address']})** ∙ "
        f"**[Photon](https://photon-sol.tinyastro.io/en/r/@rodent0x/{item['address']})** ∙ "
        f"**[Bull](https://bullx.io/terminal?chainId=1399811149&address={item['address']})** ∙ "
        f"**[PepeB](https://t.me/pepeboost_sol04_bot?start=ref_01obi0_ca_{item['address']})** ∙ "
        f"**[Troj](https://t.me/hector_trojanbot?start=r-j3rrycr3dits-{item['address']})**"
    )

    return {
        "Coin Data": coin_info + field_value,
        "**First 70 Buyer Data**": buyers_info,
        "**Rug Check**": other_info,
        "**Quick Buy**": quick_buy,
        "**CTO TG**": telegram_field_value,
    }

async def send_or_update_embed(channel, item, task_type):
    """Send or update the embed message for the coin."""
    guildname = channel.guild.name
    coins_collection = db[f'coins_{guildname}']

    channel_id = channel.id
    if channel_id not in sent_messages:
        sent_messages[channel_id] = {"soaring": {}, "new": {}, "completing": {}}
        volume_check[channel_id] = {"soaring": {}, "new": {}, "completing": {}}
    
    sent_messages_task = sent_messages[channel_id][task_type]
    updated = item['address'] in sent_messages_task
    trend, percentage_change, trend_indicator = "", "", ""
    
    if updated:
        previous_mcap = seen_coins[(item['name'], item['symbol'])]['called_mcap']
        current_mcap = int(float(item['usd_market_cap']))
        percentage_change, trend_indicator = calculate_percentage_change(previous_mcap, current_mcap)
        trend = "Blasting! 🚀" if current_mcap > previous_mcap else "Dipping! 💥" if current_mcap < previous_mcap else ""
        seen_coins[(item['name'], item['symbol'])]['market_cap'] = current_mcap
    embed = await format_embed(item, updated, trend, percentage_change, trend_indicator)
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
        volume_check[channel_id][task_type][item['address']] = {
            "last_volume": int(float(item['volume_1m'])),
            "timestamp": datetime.now(tz=timezone.utc)
        }

    except Exception as e:
        logging.error(f"Error in send_or_update_embed: {e}")

async def delete_old_messages(channel, valid_addresses, task_type):
    """Delete old messages that are no longer valid."""
    channel_id = channel.id
    if channel_id in sent_messages:
        sent_messages_task = sent_messages[channel_id][task_type]
        for address, message_id in list(sent_messages_task.items()):
            if address not in valid_addresses:
                try:
                    message = await channel.fetch_message(message_id)
                    if message:
                        await message.delete()
                    del sent_messages_task[address]
                except interactions.errors.NotFound:
                    del sent_messages_task[address]

async def send_coins(channel, task_type, ctx):
    global last_data
    guildname = channel.guild.name
    coins_collection = db[f'coins_{guildname}']

    channel_id = channel.id
    if channel_id not in last_data:
        last_data[channel_id] = {"soaring": None, "new": None, "completing": None}
    
    params = {
        "soaring": {
            'limit': '100',
            'orderby': 'usd_market_cap',
            'direction': 'asc',
            'soaring': 'true',
            'min_volume': '3000',
            'min_marketcap': '9000',
            'max_marketcap': '50000',
            'min_holder_count': '40',
            'max_created': '2h',
        },
        "new": {
            'limit': '50',
            'orderby': 'created_timestamp',
            'direction': 'desc',
            'soaring': 'true',
            'min_volume': '500',
            'max_marketcap': '9000',
            'min_progress': '0.05',
            'max_created': '10m',
        },
        "completing": {
            'limit': '100',
            'orderby': 'usd_market_cap',
            'direction': 'desc',
            'pump': 'true',
            'min_progress': '0.8',
            'max_created': '2h',
        }
    }
    try:
        url = build_query_url(BASE_URL, params[task_type])
        data = await fetch_data(url)
        if data and data['data']['rank'] != last_data[channel_id][task_type]:
            last_data[channel_id][task_type] = data['data']['rank']
            valid_addresses = {item['address'] for item in data['data']['rank']}
            for item in data['data']['rank']:
                coin_key = (item['name'], item['symbol'])
                
                # Check for duplicate tickers
                if item['symbol'] in seen_tickers and seen_tickers[item['symbol']] != item['address']:
                    continue
                
                # Check for 1-minute volume below 1000
                volume_1m = int(float(item.get('volume_1m', 0.0) or 0.0))
                if volume_1m < 1800:
                    # logging.info(f"Token {item['address']} has low volume. Skipping.")
                    continue

                # Fetch top buyers data
                top_buyers = await fetch_top_buyers(item['address'])
                if top_buyers is None:
                    logging.info(f"Token {item['address']} has dev_team wallets or too many snipers. Skipping.")
                    continue
                
                holders = top_buyers.get('holders', {})
                if check_dev_sniper_tags(holders) or check_sniper_count(holders):
                    logging.info(f"Token {item['address']} has dev_team and sniper tags in a single wallet or too many snipers. Skipping.")
                    continue

                # Check if the coin was already called by the bot
                called_by = ctx.bot.user.username
                if coin_key not in seen_coins:
                    seen_coins[coin_key] = {
                        'address': item['address'],
                        'called_mcap': int(float(item['usd_market_cap'])),
                        'market_cap': int(float(item['usd_market_cap'])),
                        'called_at': datetime.now(tz=timezone.utc),
                        'called_by': called_by
                    }
                    seen_tickers[item['symbol']] = item['address']
                    update_seen_coin(
                        item['name'], item['symbol'], item['address'],
                        int(float(item['usd_market_cap'])),
                        int(float(item['usd_market_cap'])),
                        datetime.now(tz=timezone.utc),
                        called_by,
                        guildname
                    )
                else:
                    seen_coins[coin_key]['market_cap'] = int(float(item['usd_market_cap']))
                    update_seen_coin(
                        item['name'], item['symbol'], item['address'],
                        seen_coins[coin_key]['called_mcap'],
                        seen_coins[coin_key]['market_cap'],
                        seen_coins[coin_key]['called_at'],
                        seen_coins[coin_key]['called_by'],
                        guildname
                    )
                
                await send_or_update_embed(channel, item, task_type)
            await delete_old_messages(channel, valid_addresses, task_type)
    except Exception as e:
        logging.error(f"Error in send_coins: {e}")

def build_query_url(base_url, params):
    """Build query URL from the base URL and parameters."""
    query_url = f"{base_url}?"
    for key, value in params.items():
        query_url += f"{key}={value}&"
    return query_url.strip('&')

async def fetch_current_market_cap(address):
    """Fetch the current market cap for the given address."""
    url = f"{FETCH_COIN_DATA}{address}"
    data = await fetch_data(url)
    if data and 'data' in data and len(data['data']) > 0:
        return int(float(data['data'][0]['market_cap']))
    else:
        logging.error(f"No valid data returned for address {address}")
    return None

async def check_volume_movement():
    """Check if the volume is moving for each coin."""
    while True:
        for channel_id, channel_data in volume_check.items():
            for task_type, addresses in channel_data.items():
                for address, data in list(addresses.items()):
                    if datetime.now(tz=timezone.utc) - data['timestamp'] >= timedelta(minutes=2):
                        current_volume = fetch_current_volume(address)
                        if int(float(current_volume)) == data['last_volume']:
                            logging.info(f"Removing {address} from {task_type} in channel {channel_id} due to no volume movement.")
                            channel = await bot.fetch_channel(channel_id)
                            await delete_message(channel, address, task_type)
                        else:
                            volume_check[channel_id][task_type][address]['last_volume'] = int(float(current_volume))
                            volume_check[channel_id][task_type][address]['timestamp'] = datetime.now(tz=timezone.utc)
        await asyncio.sleep(120)

async def fetch_current_volume(address):
    """Fetch the current volume for the given address."""
    url = f"{SEARCH_API_BASE_URL}{address}"
    data = await fetch_data(url)
    if data and 'data' in data and len(data['data']) > 0:
        return int(float(data['data'][0]['volume_1m']))
    else:
        logging.error(f"No valid data returned for address {address}")
    return None

async def delete_message(channel, address, task_type):
    """Delete a specific message from the channel."""
    channel_id = channel.id
    if channel_id in sent_messages and address in sent_messages[channel_id][task_type]:
        try:
            message_id = sent_messages[channel_id][task_type][address]
            message = await channel.fetch_message(message_id)
            if message:
                await message.delete()
            del sent_messages[channel_id][task_type][address]
            del volume_check[channel_id][task_type][address]
        except interactions.errors.NotFound:
            del sent_messages[channel_id][task_type][address]
            del volume_check[channel_id][task_type][address]

@bot.event
async def on_ready():
    """Event handler for when the bot is ready."""
    logging.info(f'Bot logged in as {bot.me.name}')

    # Load seen_coins from the database on startup
    for guild in await bot.fetch_guilds().flatten():
        seen_coins.update(get_seen_coins(guild.name))

    asyncio.create_task(monitor_tasks())
    asyncio.create_task(check_volume_movement())

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
    if ctx.channel.id in running_tasks:
        if task_type in running_tasks[ctx.channel.id]:
            await ctx.send(f'Task {task_type.capitalize()} is already running in this channel.', ephemeral=True)
            return
    await ctx.send(f'Grabbing {task_type.capitalize()} Coins for the BAGSS! 👜', ephemeral=True)
    scheduler = await aiojobs.create_scheduler()
    task = await scheduler.spawn(loop_send_coins(ctx.channel, task_type, ctx))
    if ctx.channel.id not in running_tasks:
        running_tasks[ctx.channel.id] = {}
    running_tasks[ctx.channel.id][task_type] = task
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
        if ctx.channel.id in running_tasks:
            for task_type in ["soaring", "new", "completing"]:
                if task_type in running_tasks[ctx.channel.id]:
                    await running_tasks[ctx.channel.id][task_type].close()
                    del running_tasks[ctx.channel.id][task_type]
                    stopped_any = True

            # Delete all messages in the channel
            await ctx.channel.purge()

        if stopped_any:
            await ctx.send(f'Stopped sending token information and deleted all messages in this channel. ❌', ephemeral=True)
        else:
            await ctx.send('No active tasks to stop in this channel. ❌', ephemeral=True)
    except Exception as e:
        logging.error(f"Error in stop command: {e}")

@interactions.slash_command(
    name="clear",
    description="Clear all messages from this channel.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD | interactions.Permissions.MANAGE_CHANNELS,
    dm_permission=False
)
async def clear(ctx):
    try:
        if not await admin_command(ctx):
            await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)
            return

        await ctx.channel.purge()
        await ctx.send('Cleared all messages from this channel. 🗑️', ephemeral=True)
    except interactions.errors.NotFound:
        pass
    except Exception as e:
        logging.error(f"Error in clear command: {e}")
        raise e

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
        if ctx.channel.id in running_tasks:
            for task_type in ["soaring", "new", "completing"]:
                if task_type in running_tasks[ctx.channel.id]:
                    await running_tasks[ctx.channel.id][task_type].close()
                    del running_tasks[ctx.channel.id][task_type]
                    scheduler = await aiojobs.create_scheduler()
                    task = await scheduler.spawn(loop_send_coins(ctx.channel, task_type))
                    if ctx.channel.id not in running_tasks:
                        running_tasks[ctx.channel.id] = {}
                    running_tasks[ctx.channel.id][task_type] = task
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
        guildname = ctx.guild.name
        coins_collection = db[f'coins_{guildname}']

        coins = coins_collection.find({'called_mcap': {'$gte': 55000}})
        
        leaderboard_data = []
        for coin in coins:
            current_mcap = await fetch_current_market_cap(coin['address'])
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
                value=f"Current MCAP: ${format_large_number(data[2])}\nCalled at ${format_large_number(data[3])} on {data[4]}",
                inline=False
            )
        await ctx.send(embeds=[embed])
    except Exception as e:
        logging.error(f"Error in leaderboard command: {e}")

async def loop_send_coins(channel, task_type, ctx):
    """Loop to continuously send coin information."""
    while True:
        try:
            await send_coins(channel, task_type, ctx)
        except Exception as e:
            logging.error(f"Error in loop_send_coins for {task_type}: {e}")
        await asyncio.sleep(3)

async def monitor_tasks():
    """Monitor tasks to ensure they are running."""
    while True:
        for channel_id, task_data in list(running_tasks.items()):
            for task_type, task in task_data.items():
                if task.done():
                    logging.warning(f"Task for channel {channel_id} has stopped. Restarting {task_type} task...")
                    channel = await bot.fetch_channel(channel_id)
                    new_task = await aiojobs.create_scheduler().spawn(loop_send_coins(channel, task_type))
                    running_tasks[channel_id][task_type] = new_task
        await asyncio.sleep(60)

def get_socials(social_links):
    """Generate social media links for the embed."""
    links = []
    
    if social_links.get('twitter_username'):
        links.append(f"**[X](https://twitter.com/{social_links['twitter_username']})**")
    if social_links.get('website'):
        website = social_links['website']
        links.append(f"**[Web]({website if website.startswith('http') else 'https://' + website})**")
    if social_links.get('telegram'):
        telegram = social_links['telegram']
        links.append(f"**[TG]({telegram if telegram.startswith('http') else 'https://' + telegram})**")
    
    return " **∙** ".join(links)


async def generate_embed_ca(item, topbuyers, socials, connected_wallets, called_by):
    try:
        # Prepare the data for the embed
        coin_info = f"```{item['address']}```\n"
        if socials:
            coin_info += f"{socials}\n"
        coin_info += f"💊 **[Pump](https://pump.fun/{item['address']})**\n\n"
        
        market_cap = format_large_number(int(float(item.get('market_cap'))) if item.get('market_cap') else 'N/A')
        created_time_since = get_time_since_creation(item['creation_timestamp']) if item.get('creation_timestamp') else 'N/A'
        holder_count = item.get('holder_count', 'N/A')
        volume_1m = format_large_number(int(float(item.get('volume_1m', 0.0) or 0.0)))
        top_10_holder_rate = float(item.get('top_10_holder_rate')) * 100 if item.get('top_10_holder_rate') is not None else 0.0
        creator_balance = int(float(item.get('creator_balance', 0.00)))
        creator_balance_rate = float(item.get('creator_percentage', 0.0)) * 100 if item.get('creator_percentage') is not None else 0.0
        if item.get('creator_token_status') == "creator_close" or item.get('creator_close') == True:
            dev_status = "Dev sold all: ✅"
        elif item.get('creator_token_status') == "creator_hold":
            dev_status = f"Dev Holds: `{creator_balance_rate:.2f}%`"
        elif item.get('creator_token_status') == "creator_buy":
            dev_status = f"Dev Bought More:  `{creator_balance_rate:.2f}%`"
        else:
            dev_status = "Dev sold: ❌"
            
        holder_rugged_num = item.get('holder_rugged_num', 0.0)
        holder_token_num = item.get('holder_token_num', 0.0)

        holders = topbuyers.get('holders', {})
        fresh_wallet_count = sum('fresh_wallet' in holder['tags'] for holder in holders.get('holderInfo', []))
        sniper_count = sum('sniper' in holder['maker_token_tags'] for holder in holders.get('holderInfo', []))
        rat_trader_count = sum('rat_trader' in holder['maker_token_tags'] for holder in holders.get('holderInfo', []))
        smart_trader_count = sum('pump_smart' in holder['tags'] for holder in holders.get('holderInfo', []))
        
        telegram_links = await fetch_telegram_links(item['address'], item['symbol'], item['name'])
        telegram_field_value = " | ".join(telegram_links) if telegram_links else "No TG Found"
        logging.info(f"Telegram links for {item['name']} ({item['symbol']}): {telegram_field_value}")
        cto_flag = "✅" if telegram_links else "❌"
        
        # Use the new check_dex_paid function
        dex_paid = await check_dex_paid(item['address'])
        if dex_paid == 500:
            logging.warning(f"Dex paid check failed for {item['address']}. Setting default value.")
            dex_paid = False
        
        dex_status_check = f"[Check Status](https://www.checkdex.xyz/{item['address']})"
        bubblemap_check = f"[Bubblemap](https://app.bubblemaps.io/sol/token/{item['address']}?pumpfun=true)"
        
        called_mcap = format_large_number(seen_coins[(item['name'], item['symbol'], item['address'])]['called_mcap'])
        called_at = seen_coins[(item['name'], item['symbol'], item['address'])]['called_at']
        
        if isinstance(called_at, str):
            called_at = datetime.strptime(called_at, "%I:%M %p %b %d")
        called_at_formatted = called_at.strftime("%I:%M %p %b %d")
        profit_percentage = calculate_profit_percentage(seen_coins[(item['name'], item['symbol'], item['address'])]['called_mcap'], int(float(item['market_cap'])))

        field_value = (
            f"💎 **MCAP:** `${market_cap}` 🕰️ **Age:** `{created_time_since}`\n"
            f"📊 **1m-Vol:** `${volume_1m}`\n"
            f"🏆 **Top10**: `{top_10_holder_rate:.2f}%` 👥 **Holders:** `{holder_count}`\n"
            f"🫅 **Dev SolBal:** `{creator_balance}`\n"
        )
        
        called_value = (
            f"👁️ **Called At:** `${called_mcap}` on `{called_at_formatted}`\n"
            f"👤 **Called By:** `@{called_by}` \n"
            f"💰 **Profit/Loss:** `{profit_percentage}`\n"
        )

        other_info = (
            f"🍼 Fresh Wallets: `{fresh_wallet_count}` \n"
            f"🎯 Snipers: `{sniper_count}`\n"
            f"🐀 Rats: `{rat_trader_count}`\n"
            f"🧠 Smart Traders: `{smart_trader_count}`\n"
            f"🔗 Connected Wallets: `{connected_wallets}` | {bubblemap_check}\n"
            f"⚡ Dex paid?: {'✅' if dex_paid else '❌'} | {dex_status_check} \n"
            f"🧑‍💻 {dev_status}\n"
            f"⚠️ Deployed: `{holder_token_num}` | Rugged: `{holder_rugged_num}`\n"
            f"🫂 CTO?: {cto_flag}\n"
        )
        
        quick_buy = (
            f"**[GmGn](https://gmgn.ai/sol/token/Sef3AuWIF_{item['address']})** ∙ "
            f"**[Photon](https://photon-sol.tinyastro.io/en/r/@rodent0x/{item['address']})** ∙ "
            f"**[Bull](https://bullx.io/terminal?chainId=1399811149&address={item['address']})** ∙ "
            f"**[PepeB](https://t.me/pepeboost_sol04_bot?start=ref_01obi0_ca_{item['address']})** ∙ "
            f"**[Troj](https://t.me/hector_trojanbot?start=r-j3rrycr3dits-{item['address']})**"
        )
            
        ca_data = {
            'coin_info': coin_info,
            'field_value': field_value,
            'called_value': called_value,
            'other_info': other_info,
            'quicksnipe': quick_buy,
            'telegram_field_value': telegram_field_value
        }
        embed = await format_embed(item, ca_data=ca_data)
        return embed
    except Exception as e:
        logging.error(f"Error in generate_embed_ca: {e}")
        return None

    
@interactions.slash_command(
    name="ca",
    description="Check the current market cap of a coin.",
    dm_permission=False,
    options=[
        {
            "name": "address",
            "description": "The address of the coin.",
            "type": 3,
            "required": True
        }
    ]
)
async def ca(ctx, address: str):
    try:
        logging.info(f"Starting /ca command for address: {address}")
        await ctx.defer()
        url = f"{FETCH_COIN_DATA}{address}"
        data = await fetch_data(url)

        if data and 'data' in data and 'token' in data['data']:
            item = data['data']['token']
            coin_key = (item['name'], item['symbol'], item['address'])
            name_dc = ctx.author.global_name

            connected_wallets = count_connected_wallets(await fetch_bubblemap_data(item['address']))
            topbuyers = await fetch_top_buyers(item['address'])
            socials = get_socials(item.get('social_links', {}))

            guildname = ctx.guild.name
            coins_collection = db[f'coins_{guildname}']  # Define coins_collection based on the guild name

            # Check if the coin is already in seen_coins and in the database
            existing_coin = coins_collection.find_one({'address': item['address']})

            if coin_key not in seen_coins and not existing_coin:
                seen_coins[coin_key] = {
                    'address': item['address'],
                    'called_mcap': int(float(item['market_cap'])),
                    'market_cap': int(float(item['market_cap'])),
                    'called_at': datetime.now(tz=timezone.utc),
                    'called_by': name_dc
                }
                seen_tickers[item['symbol']] = item['address']
                update_seen_coin(
                    item['name'], item['symbol'], item['address'],
                    int(float(item['market_cap'])),
                    int(float(item['market_cap'])),
                    datetime.now(tz=timezone.utc),
                    name_dc,
                    guildname
                )
                called_by = name_dc
            else:
                if existing_coin:
                    seen_coins[coin_key] = {
                        'address': item['address'],
                        'called_mcap': existing_coin['called_mcap'],
                        'market_cap': int(float(item['market_cap'])),
                        'called_at': existing_coin['called_at'],
                        'called_by': existing_coin['called_by']
                    }
                called_by = seen_coins[coin_key]['called_by']

            logging.info(f"Called by: {called_by}")
            embed = await generate_embed_ca(item, topbuyers, socials, connected_wallets, called_by)
            if embed:
                await ctx.send(embeds=[embed])
            else:
                logging.error(f"No valid embed created for address {address}.")
                await ctx.send(f"No valid data found for address {address}.")
        else:
            logging.error(f"Failed to fetch data for address {address}.")
            await ctx.send(f"No valid data found for address {address}.")
    except Exception as e:
        logging.error(f"Error in ca command: {e}")
        await ctx.send(f"An error occurred while processing the request.")


def get_seen_coins(guildname):
    """Fetch seen_coins from the database."""
    coins_collection = db[f'coins_{guildname}']
    seen_coins = {}
    for coin in coins_collection.find({}):
        key = (coin['name'], coin['symbol'], coin['address'])
        seen_coins[key] = {
            'address': coin['address'],
            'called_mcap': coin['called_mcap'],
            'market_cap': coin['market_cap'],
            'called_at': coin.get('called_at'),
            'called_by': coin.get('called_by')
        }
    return seen_coins

def update_seen_coin(name, symbol, address, called_mcap, market_cap, called_at, called_by, guildname):
    """Update seen_coins in the database."""
    coins_collection = db[f'coins_{guildname}']

    try:
        # Ensure called_at is a datetime object
        if isinstance(called_at, str):
            called_at = datetime.strptime(called_at, "%I:%M %p %b %d")

        # Format the called_at datetime to 12-hour format with AM/PM
        called_at_formatted = called_at.strftime("%I:%M %p %b %d")

        # Prepare the update data
        update_data = {
            'name': name,
            'symbol': symbol,
            'called_mcap': called_mcap,
            'market_cap': market_cap,
            'called_at': called_at_formatted,
            'called_by': called_by
        }

        coins_collection.update_one(
            {'address': address},
            {'$set': update_data},
            upsert=True
        )
    except ValueError as e:
        logging.error(f"Error formatting called_at for address {address}: {e}")
        coins_collection.update_one(
            {'address': address},
            {'$set': {
                'name': name,
                'symbol': symbol,
                'called_mcap': called_mcap,
                'market_cap': market_cap,
                'called_at': called_at,
                'called_by': called_by
            }},
            upsert=True
        )




# Start the bot
bot.start()

