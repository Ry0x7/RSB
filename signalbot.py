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
import random
from interactions import listen, Client
from bs4 import BeautifulSoup
import http.client
import json
from urllib.parse import urlparse
import time
import io
import gzip
import base64
import concurrent.futures

dotenv.load_dotenv()

# Initialize the Discord bot
bot = Client(token=os.getenv('DISCORD_TOKEN'))

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
sent_coins = {}

# Configure logging
logging.basicConfig(level=logging.INFO)

# Store running tasks and sent messages
running_tasks = {}
sent_messages = {}

# Store the last volume check for each coin
volume_check = {}
processed_message_ids = set()
last_message_time = None
top_buyers_cache = {}
cache_timeout = 300  # Cache timeout in seconds (e.g., 5 minutes)

# Maximum number of concurrent tasks
MAX_CONCURRENT_TASKS = 2

# List of possible footers
footer_messages = [
    "For business inquiries, DM @chakazzz 👑",
    "Crypto tracking by your favorite bot 🔍",
    "Stay updated with the latest trends 🌐",
    "Want this bot in your server? DM @chakazzz 👑",
    "Monitoring the crypto universe 🌌",
    "Data accuracy is our priority 📈",
    "Powered by your friendly neighborhood bot 🤖",
    "Nothing is more important than data accuracy 📊",
    "For the best bots, DM @chakazzz 👑"
]

status_messages = [
    "Watching the market 🚀",
    "Tracking crypto trends 📊",
    "Monitoring wallets 👀",
    "Fetching the latest data 🧠",
    "Analyzing market caps 💹",
    "Checking for new coins 🪙",
    "Want this bot in your server? DM @chakazzz 👑"
]

useragents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.104 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:84.0) Gecko/20100101 Firefox/84.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:83.0) Gecko/20100101 Firefox/83.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:82.0) Gecko/20100101 Firefox/82.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15A5341f Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 9; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 8.0.0; SM-G950F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.101 Mobile Safari/537.36"
]


main_proxy = "https://spczig9st1:9~QJmaHbtsnv73xbS8@gate.smartproxy.com:7000"

# def fetch_ip(proxy_parsed, proxy_auth_encoded):
#     """Fetch the current IP address using the proxy."""
#     conn = http.client.HTTPSConnection(proxy_parsed.hostname, proxy_parsed.port)
#     conn.set_tunnel("api.ipify.org", headers={"Proxy-Authorization": f"Basic {proxy_auth_encoded}"})
#     conn.request("GET", "/")
#     response = conn.getresponse()
#     if response.status == 200:
#         ip = response.read().decode('utf-8')
#         logging.info(f"Current IP address: {ip}")
#         return ip
#     else:
#         logging.error(f"Failed to fetch IP address: {response.status} {response.reason}")
#     conn.close()
#     return None

def fetch_data_sync(url, retries=3, delay=3):
    """Synchronous fetch data function with retries and delay."""
    logging.info(f"Fetching data from URL: {url}")
    parsed_url = urlparse(url)
    
    # Parse the main proxy URL
    proxy_parsed = urlparse(main_proxy)
    
    # Encode proxy credentials
    proxy_auth = f"{proxy_parsed.username}:{proxy_parsed.password}"
    proxy_auth_encoded = base64.b64encode(proxy_auth.encode()).decode()

    # Check IP address before fetching data
    # logging.info("Checking IP address before fetching data...")
    # fetch_ip(proxy_parsed, proxy_auth_encoded)

    for attempt in range(retries):
        try:
            if parsed_url.netloc == "gmgn.ai":
                logging.info("Connecting to proxy for gmgn.ai...")
                conn = http.client.HTTPSConnection(proxy_parsed.hostname, proxy_parsed.port)
                conn.set_tunnel("gmgn.ai", headers={"Proxy-Authorization": f"Basic {proxy_auth_encoded}"})
                headers = {
                    'User-Agent': random.choice(useragents),
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br, zstd',
                    'Referer': 'https://gmgn.ai/meme?chain=sol',
                    'Alt-Used': 'gmgn.ai',
                    'Connection': 'keep-alive',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-origin',
                    'If-None-Match': 'W/a414-l8/w3z1JNxalxPb2NpnpiXw5qjM',
                    'TE': 'trailers'
                }
                conn.request("GET", f"{parsed_url.path}?{parsed_url.query}", '', headers)
                logging.info("Request sent to gmgn.ai through proxy.")
                response = conn.getresponse()
                logging.info(f"Received response with status code: {response.status}")
                if response.status == 200:
                    data = response.read()
                    if response.getheader('Content-Encoding') == 'gzip':
                        decompressed_data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                        decoded_data = decompressed_data.decode('utf-8')
                    else:
                        decoded_data = data.decode('utf-8')
                    return json.loads(decoded_data)
                elif response.status == 403:
                    logging.warning(f"Received 403 Forbidden. Retrying after delay... ({attempt + 1}/{retries})")
                    time.sleep(delay)  # Add delay before retrying
                else:
                    logging.error(f"Error fetching data from {url}: {response.status} {response.reason}")
            else:
                logging.info(f"Connecting to proxy for {parsed_url.netloc}...")
                conn = http.client.HTTPSConnection(proxy_parsed.hostname, proxy_parsed.port)
                conn.set_tunnel(parsed_url.netloc, headers={"Proxy-Authorization": f"Basic {proxy_auth_encoded}"})
                conn.request("GET", parsed_url.path + "?" + parsed_url.query)
                logging.info(f"Request sent to {parsed_url.netloc} through proxy.")
                response = conn.getresponse()
                logging.info(f"Received response with status code: {response.status}")
                if response.status == 200:
                    data = response.read()
                    return json.loads(data.decode('utf-8'))
                elif response.status == 403:
                    logging.warning(f"Received 403 Forbidden. Retrying after delay... ({attempt + 1}/{retries})")
                    time.sleep(delay)  # Add delay before retrying
                else:
                    logging.error(f"Error fetching data from {url}: {response.status} {response.reason}")
        except http.client.RemoteDisconnected as e:
            logging.error(f"RemoteDisconnected occurred: {e}. Retrying after delay... ({attempt + 1}/{retries})")
            time.sleep(delay)  # Add delay before retrying
        except Exception as e:
            logging.error(f"Exception occurred while connecting to {parsed_url.netloc}: {e}", exc_info=True)
            time.sleep(delay)  # Add delay before retrying
        finally:
            conn.close()
    
    logging.error(f"Failed to fetch data from {url} after {retries} attempts.")
    return None

async def fetch_data(url, retries=3, delay=3):
    """Asynchronously fetch data by running the sync fetch in a separate thread."""
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, fetch_data_sync, url, retries, delay)
    return result

async def fetch_data_waf_bypass2(url, retries=3, timeout=10):
    """Fetch data from the specified URL with WAF bypass, retry logic, and timeout."""
    logging.info(f"Fetching data from URL with WAF bypass: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=timeout) as response:
                    logging.info(f"Received response with status code: {response.status}")
                    if response.status == 200:
                        return await response.json()
                    else:
                        logging.error(f"Error fetching data from {url}: {response.status} {await response.text()}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logging.error(f"Request exception occurred: {e}")
            if attempt < retries - 1:
                logging.info(f"Retrying... ({attempt + 1}/{retries})")
                await asyncio.sleep(2)  # Optional: wait a bit before retrying
            else:
                logging.error(f"Failed to fetch data after {retries} attempts.")
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
        return "N/A", False
    change = ((current_mcap - called_mcap) / called_mcap) * 100
    if change == -100:
        return "Loss trade🔴", False
    elif change > 100:
        multiplier = change / 100
        return f"{multiplier:.2f}x🟢", True
    elif change > 0:
        return f"{change:.2f}%🟢", False
    else:
        return f"{change:.2f}%🔴", False


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
    data = await fetch_data_waf_bypass2(url)
    logging.info(f"Fetching Telegram links for address: {address}")
    if data:
        valid_links = set()
        for reply in data:
            links = extract_telegram_links(reply['text'])
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
        # Modification: Ensure a list is always returned
        return filter_telegram_links(list(valid_links), symbol.lower(), name.lower()) or []
    elif data and data['code'] == 403:
        logging.error("Access to replies API is forbidden.")
        return []
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

async def fetch_top_buyers(address, use_cache=True):
    """Fetch top buyers data for the specified address, with optional caching."""
    if use_cache and address in top_buyers_cache:
        logging.info(f"Using cached top buyers data for address: {address}")
        return top_buyers_cache[address]

    url = f"{TOP_BUYERS_API_BASE_URL}{address}"
    logging.info(f"Fetching top buyers data for address: {address}")
    
    data = await fetch_data(url)

    if data and 'code' in data and data['code'] == 0:
        if use_cache:
            top_buyers_cache[address] = data['data']  # Cache the data
        return data['data']
    else:
        logging.error(f"No valid data returned for top buyers of address {address}")
        return None


async def fetch_bubblemap_data(address, retries=3, timeout=10):
    """Fetch bubblemap data for the specified address with retry logic."""
    url = f"https://europe-west1-cryptos-tools.cloudfunctions.net/get-bubble-graph-data?token={address}&chain=sol&pumpfun=true"
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, dict) and 'links' in data:
                            return data
                        else:
                            logging.error(f"Unexpected data format returned for address {address}: {data}")
                            return None
                    elif response.status == 500:
                        logging.error(f"Server error occurred while fetching bubblemap data for address {address}")
                    else:
                        logging.error(f"Unexpected response status {response.status} while fetching bubblemap data for address {address}: {await response.text()}")
        except aiohttp.ClientError as e:
            logging.error(f"Request exception occurred: {e}")
        except asyncio.TimeoutError:
            logging.error(f"Timeout occurred while fetching bubblemap data for address {address}. Retrying... ({attempt + 1}/{retries})")
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    return None  # Return None if all retries fail


def count_connected_wallets(bubblemap_data):
    """Count the number of connected wallets from the bubblemap data."""
    if not isinstance(bubblemap_data, dict):
        logging.error("Bubblemap data is not in the expected format.")
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

async def purge_if_exceeds_limit(channel, limit=10):
    """Purge the channel if the number of messages exceeds the specified limit."""
    try:
        messages = await channel.fetch_messages(limit=limit + 1)
        if len(messages) > limit:
            await channel.purge()  # Remove the limit argument
            logging.info(f"Purged messages in {channel.name} as it exceeded the limit of {limit} messages.")
    except interactions.errors.NotFound:
        logging.error(f"Channel {channel.name} not found during purging.")
    except interactions.errors.Forbidden:
        logging.error(f"Permission denied when attempting to purge channel {channel.name}.")
    except Exception as e:
        logging.error(f"Error purging channel {channel.name}: {e}")

async def monitor_and_purge(channel, limit=10):
    """Continuously monitor the channel and purge messages if they exceed the specified limit."""
    while True:
        await purge_if_exceeds_limit(channel, limit=limit)
        await asyncio.sleep(5)  # Check every 5 seconds




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

async def format_embed(item,):
    """Format the embed message for the coin."""
    embed_title = f"🪙 {item['name']} (${item['symbol']})"
    embed = interactions.Embed(title="", color=0x00ff00)
    embed.set_author(name=embed_title)
    logo_url = item['logo']
    if 'ipfs/' in item['logo']:
        ipfs_hash = item['logo'].split('ipfs/')[-1]
        logo_url = f"https://pump.mypinata.cloud/ipfs/{ipfs_hash}"
    embed.set_thumbnail(url=logo_url)
    
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
        
    random_footer = random.choice(footer_messages)
    embed.set_footer(text=random_footer)
    return embed

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
        f"**[Troj](https://t.me/hector_trojanbot?start=r-j3rrycr3dits-{item['address']})** ∙ "
        f"**[Fasol](https://t.me/fasol_robot?start=ref_rodent0x_ca_{item['address']})**"
    )

    return {
        "Coin Data": coin_info + field_value,
        "**First 70 Buyer Data**": buyers_info,
        "**Rug Check**": other_info,
        "**Quick Buy**": quick_buy,
        "**CTO TG**": telegram_field_value,
    }

async def generate_embed_ca(item, socials, connected_wallets, called_by):
    try:
        # Prepare the data for the embed
        coin_info = f"```{item.get('address', 'N/A')}```\n"
        if socials:
            coin_info += f"{socials}\n"
        coin_info += f"💊 **[Pump](https://pump.fun/{item.get('address', 'N/A')})**\n\n"
        
        # Safely convert and format the data
        market_cap = format_large_number(int(float(item.get('market_cap', 0.0))))
        created_time_since = get_time_since_creation(item.get('creation_timestamp', 0)) if item.get('creation_timestamp') else 'N/A'
        holder_count = item.get('holder_count', 'N/A')
        volume_1m = format_large_number(int(float(item.get('volume_1m', 0.0))))
        top_10_holder_rate = float(item.get('top_10_holder_rate', 0.0)) * 100
        creator_balance = int(float(item.get('creator_balance', 0.0)))
        creator_balance_rate = float(item.get('creator_percentage', 0.0)) * 100
        
        # Handle dev status conditions safely
        dev_status = "Dev sold: ❌"
        if item.get('creator_token_status') == "creator_close" or item.get('creator_close') is True:
            dev_status = "Dev sold all: ✅"
        elif item.get('creator_token_status') == "creator_hold":
            dev_status = f"Dev Holds: `{creator_balance_rate:.2f}%`"
        elif item.get('creator_token_status') == "creator_buy":
            dev_status = f"Dev Bought More:  `{creator_balance_rate:.2f}%`"
            
        holder_rugged_num = item.get('holder_rugged_num', 0.0)
        holder_token_num = item.get('holder_token_num', 0.0)
        
        # Fetch and safely handle telegram links
        telegram_links = await fetch_telegram_links(item.get('address', 'N/A'), item.get('symbol', 'N/A'), item.get('name', 'N/A'))
        telegram_field_value = " | ".join(telegram_links) if telegram_links else "No TG Found"
        cto_flag = "✅" if telegram_links else "❌"
        
        # Check DEX paid status and handle failures
        dex_paid = await check_dex_paid(item.get('address', 'N/A'))
        if dex_paid == 500:
            logging.warning(f"Dex paid check failed for {item.get('address', 'N/A')}. Setting default value.")
            dex_paid = False
        
        dex_status_check = f"[Check Status](https://www.checkdex.xyz/{item.get('address', 'N/A')})"
        bubblemap_check = f"[Bubblemap](https://app.bubblemaps.io/sol/token/{item.get('address', 'N/A')}?pumpfun=true)"
        
        # Safely handle the called market cap and date formatting
        seen_coin = seen_coins.get((item.get('name', 'N/A'), item.get('symbol', 'N/A'), item.get('address', 'N/A')), {})
        called_mcap = format_large_number(seen_coin.get('called_mcap', 0))
        highest_mcap = seen_coin.get('highest_mcap', seen_coin.get('market_cap', int(float(item.get('market_cap', 0.0)))))
        current_market_cap = int(float(item.get('market_cap', 0.0)))
        logging.info(f"Called MCAP: {called_mcap}, Highest MCAP: {highest_mcap}")
        called_at = seen_coin.get('called_at', 'N/A')
        
        if isinstance(called_at, str):
            called_at = datetime.strptime(called_at, "%I:%M %p %b %d")
        called_at_formatted = called_at.strftime("%I:%M %p %b %d") if called_at != 'N/A' else 'N/A'
        
        # Calculate profit percentage using highest_mcap
        profit_percentage, is_above_100 = calculate_profit_percentage(seen_coin.get('called_mcap', 0), highest_mcap)

        # Use the current market cap if highest_mcap profit is not above 100%
        if not is_above_100:
            profit_percentage, _ = calculate_profit_percentage(seen_coin.get('called_mcap', 0), current_market_cap)
        
        # Construct the embed fields
        field_value = (
            f"💎 **MCAP:** `${market_cap}` 🕰️ **Age:** `{created_time_since}`\n"
            f"📊 **1m-Vol:** `${volume_1m}`\n"
            f"🏆 **Top10**: `{top_10_holder_rate:.2f}%` 👥 **Holders:** `{holder_count}`\n"
            f"🫅 **Dev SolBal:** `{creator_balance}`\n\n"
        )
        
        called_value = (
            f"👁️ **Called At:** `${called_mcap}` on `{called_at_formatted}`\n"
            f"👤 **Called By:** `@{called_by}` \n"
            f"💰 **Profit/Loss:** `{profit_percentage}`\n\n"
        )
        other_info = (
            f"🔗 Connected Wallets: `{connected_wallets}` | {bubblemap_check}\n"
            f"⚡ Dex paid?: {'✅' if dex_paid else '❌'} | {dex_status_check} \n"
            f"🧑‍💻 {dev_status}\n"
            f"⚠️ Deployed: `{holder_token_num}` | Rugged: `{holder_rugged_num}`\n"
            f"🫂 CTO?: {cto_flag}\n\n"
        )
        
        quick_buy = (
            f"**[GmGn](https://gmgn.ai/sol/token/Sef3AuWIF_{item.get('address', 'N/A')})** ∙ "
            f"**[Photon](https://photon-sol.tinyastro.io/en/r/@rodent0x/{item.get('address', 'N/A')})** ∙ "
            f"**[Bull](https://bullx.io/terminal?chainId=1399811149&address={item.get('address', 'N/A')})** ∙ "
            f"**[PepeB](https://t.me/pepeboost_sol04_bot?start=ref_01obi0_ca_{item.get('address', 'N/A')})** ∙ "
            f"**[Troj](https://t.me/hector_trojanbot?start=r-j3rrycr3dits-{item.get('address', 'N/A')})** ∙ "
            f"**[Fasol](https://t.me/fasol_robot?start=ref_rodent0x_ca_{item.get('address', 'N/A')})**"
        )
        ctotg = (
            f"\n\n**CTO TG:** {telegram_field_value}"
        )
        # Create the embed
        embed = interactions.Embed(
            title=f"{item.get('name', 'N/A')} ({item.get('symbol', 'N/A')})",
            description=coin_info + field_value + called_value + other_info + quick_buy + ctotg,
            color=0x00ff00
        )
        
        # Set thumbnail with a check for 'ipfs/' in the logo URL
        logo_url = item.get('logo', '')
        if 'ipfs/' in logo_url:
            ipfs_hash = logo_url.split('ipfs/')[-1]
            logo_url = f"https://pump.mypinata.cloud/ipfs/{ipfs_hash}"
        embed.set_thumbnail(url=logo_url)
        
        embed.set_footer(text=random.choice(footer_messages))
        return embed
    except Exception as e:
        logging.error(f"Error in generate_embed_ca: {e}")
        return None


async def generate_simple_embed(item, socials, connected_wallets, topbuyers, role):
    """Generate a simple embed with the required fields."""
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
        
        if item.get('creator_token_status') == "creator_close" or item.get('creator_close') is True:
            dev_status = "Dev sold all: ✅"
        elif item.get('creator_token_status') == "creator_hold":
            dev_status = f"Dev Holds: `{creator_balance_rate:.2f}%`"
        elif item.get('creator_token_status') == "creator_buy":
            dev_status = f"Dev Bought More:  `{creator_balance_rate:.2f}%`"
        else:
            dev_status = "Dev sold: ❌"
            
        holder_rugged_num = item.get('holder_rugged_num', 0.0)
        holder_token_num = item.get('holder_token_num', 0.0)

        # Ensure topbuyers is a dictionary-like object before accessing its contents
        holders = topbuyers.get('holders', {})
        fresh_wallet_count = sum('fresh_wallet' in holder.get('tags', []) for holder in holders.get('holderInfo', []))
        sniper_count = sum('sniper' in holder.get('maker_token_tags', []) for holder in holders.get('holderInfo', []))
        rat_trader_count = sum('rat_trader' in holder.get('maker_token_tags', []) for holder in holders.get('holderInfo', []))
        smart_trader_count = sum('pump_smart' in holder.get('tags', []) for holder in holders.get('holderInfo', []))

        telegram_links = await fetch_telegram_links(item['address'], item['symbol'], item['name'])
        telegram_field_value = " | ".join(telegram_links) if telegram_links else "No TG Found"
        logging.info(f"Telegram links for {item['name']} ({item['symbol']}): {telegram_field_value}")
        cto_flag = "✅" if telegram_links else "❌"

        bubblemap_check = f"[Bubblemap](https://app.bubblemaps.io/sol/token/{item['address']}?pumpfun=true)"
        cto_flag = "✅" if item.get('cto_flag') else "❌"

        field_value = (
            f"💎 **MCAP:** `${market_cap}` 🕰️ **Age:** `{created_time_since}`\n"
            f"📊 **1m-Vol:** `${volume_1m}`\n"
            f"🏆 **Top10**: `{top_10_holder_rate:.2f}%` 👥 **Holders:** `{holder_count}`\n"
            f"🫅 **Dev SolBal:** `{creator_balance}`"
            f"\n\n\n"
        )

        other_info = (
            f"🍼 Fresh Wallets: `{fresh_wallet_count}` \n"
            f"🎯 Snipers: `{sniper_count}`\n"
            f"🐀 Rats: `{rat_trader_count}`\n"
            f"🧠 Smart Traders: `{smart_trader_count}`\n"
            f"🧑‍💻 {dev_status}\n"
            f"🔗 Connected Wallets: `{connected_wallets}` | {bubblemap_check}\n"
            f"⚠️ Deployed: `{holder_token_num}` | Rugged: `{holder_rugged_num}`\n"
            f"🫂 CTO?: {cto_flag}\n\n\n"
        )
        
        quick_buy = (
            f"**[GmGn](https://gmgn.ai/sol/token/Sef3AuWIF_{item['address']})** ∙ "
            f"**[Photon](https://photon-sol.tinyastro.io/en/r/@rodent0x/{item['address']})** ∙ "
            f"**[Bull](https://bullx.io/terminal?chainId=1399811149&address={item['address']})** ∙ "
            f"**[PepeB](https://t.me/pepeboost_sol04_bot?start=ref_01obi0_ca_{item['address']})** ∙ "
            f"**[Troj](https://t.me/hector_trojanbot?start=r-j3rrycr3dits-{item['address']})** ∙ "
            f"**[Fasol](https://t.me/fasol_robot?start=ref_rodent0x_ca_{item['address']})**\n\n"
        )
        
        ctotg =(
            f"🧑‍💻 CTO TG: {telegram_field_value}\n"
        )
        
        # Fix placement of embed creation
        embed = interactions.Embed(
            title="✅ **DexScreener PAID!** ✅",
            description=coin_info + field_value + other_info + quick_buy + ctotg,
            color=0x013220
        )
        
        logo_url = item['logo']
        if 'ipfs/' in item['logo']:
            ipfs_hash = item['logo'].split('ipfs/')[-1]
            logo_url = f"https://pump.mypinata.cloud/ipfs/{ipfs_hash}"
        embed.set_thumbnail(url=logo_url)
        
        embed.set_author(name=f"{item['name']} ({item['symbol']})")
        
        random_footer = random.choice(footer_messages)
        embed.set_footer(text=random_footer)
        return embed

    except Exception as e:
        logging.error(f"Error in generate_simple_embed: {e}")
        return None  # Handle the error gracefully and return None
        

async def send_or_update_embed(channel, item, task_type, role=None):
    """Send the embed message for the coin without updating it if already sent."""
    guildname = channel.guild.name
    coins_collection = db[f'coins_{guildname}']

    channel_id = channel.id
    if channel_id not in sent_messages:
        sent_messages[channel_id] = {"soaring": {}, "new": {}, "completing": {}}
        volume_check[channel_id] = {"soaring": {}, "new": {}, "completing": {}}
    
    sent_messages_task = sent_messages[channel_id][task_type]
    
    # Check if the embed has already been sent
    if item['address'] in sent_messages_task:
        logging.info(f"Skipping {item['name']} ({item['symbol']}) as it has already been sent.")
        return
    
    embed = await format_embed(item)
    if not embed:
        return
    
    try:
        # Send the message only if it hasn't been sent already
        if role:
            message = await channel.send(f"{role.mention} {item['address']}", embeds=[embed])
        else:
            message = await channel.send(f"{item['address']}", embeds=[embed])
        sent_messages_task[item['address']] = message.id
    except Exception as e:
        logging.error(f"Error in send_or_update_embed: {e}")



async def send_coins(channel, task_type, ctx, role=None):
    global last_data
    guildname = channel.guild.name
    coins_collection = db[f'coins_{guildname}']

    channel_id = channel.id
    if channel_id not in last_data:
        last_data[channel_id] = {"soaring": None, "new": None, "completing": None}

    params = {
        "soaring": {
            'limit': '100',
            'orderby': 'created_timestamp',
            'direction': 'desc',
            'soaring': 'true',
            'min_marketcap': '9000',
            'max_marketcap': '50000',
            'min_holder_count': '40',
            'max_created': '2h',
        },
        "new": {
            'limit': '50',
            'orderby': 'created_timestamp',
            'direction': 'desc',
            'new_creation': 'true',
            'max_marketcap': '9000',
            'max_created': '10m',
            'min_holder_count': '3',
            'min_volume': '1000',
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
        logging.info(f"Fetching data for {task_type} task")
        if data and data['data']['rank'] != last_data[channel_id][task_type]:
            last_data[channel_id][task_type] = data['data']['rank']
            for item in data['data']['rank']:
                coin_key = (item['name'], item['symbol'])

                # Check for duplicate tickers
                if item['symbol'] in seen_tickers and seen_tickers[item['symbol']] != item['address']:
                    continue

                # Conditional filtering based on task_type
                volume_1m = item.get('volume_1m')
                if volume_1m is None:
                    continue  # Skip this item if volume_1m is None
                
                volume_1m = int(float(volume_1m))
                
                if task_type == "new" and volume_1m < 3500:
                    continue  # Skip if volume is below 3500 for new coins
                elif task_type == "soaring" and volume_1m < 5000:
                    continue  # Skip if volume is below 5000 for soaring coins
                elif task_type == "completing" and volume_1m < 2000:
                    continue  # Skip if volume is below 2000 for completing coins
                
                # Fetch top buyers data only for the /new task using the cache
                if task_type == "new" or "soaring":
                    if item['address'] in top_buyers_cache:
                        top_buyers = top_buyers_cache[item['address']]
                    else:
                        top_buyers = await fetch_top_buyers(item['address'])
                        top_buyers_cache[item['address']] = top_buyers

                    # Check for dev_team and sniper tags only for the /new task
                    if top_buyers is None:
                        logging.info(f"Token {item['address']} has dev_team wallets or too many snipers. Skipping.")
                        continue

                    holders = top_buyers.get('holders', {})
                    if check_dev_sniper_tags(holders) or check_sniper_count(holders):
                        logging.info(f"Token {item['address']} has dev_team and sniper tags in a single wallet or too many snipers. Skipping.")
                        continue

                # Record the coin as seen and update the seen_coins dictionary
                called_by = ctx.bot.user.username
                usd_market_cap = item.get('usd_market_cap')
                
                if usd_market_cap is None:
                    continue  # Skip this item if usd_market_cap is None
                
                usd_market_cap = int(float(usd_market_cap))
                
                if coin_key not in seen_coins:
                    seen_coins[coin_key] = {
                        'address': item['address'],
                        'called_mcap': usd_market_cap,
                        'market_cap': usd_market_cap,
                        'called_at': datetime.now(tz=timezone.utc),
                        'called_by': called_by
                    }
                    seen_tickers[item['symbol']] = item['address']
                    update_seen_coin(
                        item['name'], item['symbol'], item['address'],
                        usd_market_cap,
                        usd_market_cap,
                        datetime.now(tz=timezone.utc),
                        called_by,
                        guildname
                    )
                else:
                    seen_coins[coin_key]['market_cap'] = usd_market_cap
                    # Only update 'called_by' if it's not already set
                    existing_called_by = seen_coins[coin_key].get('called_by')
                    if not existing_called_by:
                        seen_coins[coin_key]['called_by'] = called_by
                    update_seen_coin(
                        item['name'], item['symbol'], item['address'],
                        seen_coins[coin_key]['called_mcap'],
                        seen_coins[coin_key]['market_cap'],
                        seen_coins[coin_key]['called_at'],
                        seen_coins[coin_key]['called_by'],
                        guildname
                    )

                # Send the embed for the coin
                await send_or_update_embed(channel, item, task_type, role)

    except Exception as e:
        logging.error(f"Error in send_coins: {e}", exc_info=True)

        
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

@listen()
async def on_ready():
    """Event handler for when the bot is ready."""
    # Access the bot's user information
    bot_user = bot.user

    # Log the bot's username
    logging.info(f'Bot logged in as {bot_user.username}')

    # Set a random bot status from the predefined status messages
    random_status = random.choice(status_messages)
    await bot.change_presence(
        activity=interactions.Activity(
            name=random_status,
            type=interactions.ActivityType.WATCHING
        ),
        status=interactions.Status.ONLINE
    )

    # Load seen_coins from the database on startup
    for guild in bot.guilds:
        seen_coins.update(get_seen_coins(guild.name))

    
async def change_status_loop():
    """Loop to change the bot's status every minute."""
    while True:
        logging.info("Changing status...")
        random_status = random.choice(status_messages)
        logging.info(f"Selected status: {random_status}")
        try:
            await bot.change_presence(
                activity=interactions.Activity(
                    name=random_status, 
                    type=interactions.ActivityType.WATCHING
                ),
                status=interactions.StatusType.ONLINE
            )
            logging.info(f"Presence successfully set to: {random_status}")
        except Exception as e:
            logging.error(f"Failed to change presence: {e}")
        
        logging.info("Sleeping for 15 seconds.")
        await asyncio.sleep(15)  # Delay for 1 minute (60 seconds)
        
async def admin_command(ctx):
    """Check if the user has admin permissions."""
    owner_id = "239243874529312768"  # Replace with the actual owner ID
    guild = ctx.guild  # Ensure this command is used in a guild

    if guild is None:
        return False  # Return False if not in a guild (e.g., in a DM)

    member = ctx.author  # Get the member object for the author

    # Allow all commands for the owner
    if ctx.author.id == int(owner_id):
        return True

    # Check if the user has Manage Guild or Administrator permissions
    if member.has_permission(interactions.Permissions.MANAGE_GUILD) or member.has_permission(interactions.Permissions.ADMINISTRATOR):
        return True

    return False

async def start_task(ctx, task_type, role=None):
    if ctx.channel.id in running_tasks:
        if task_type in running_tasks[ctx.channel.id]:
            await ctx.send(f'Task {task_type.capitalize()} is already running in this channel.', ephemeral=True)
            return
    await ctx.send(f'Grabbing {task_type.capitalize()} Coins for the BAGSS! 👜', ephemeral=True)
    scheduler = await aiojobs.create_scheduler()

    if task_type == "dexsignals":
        task = await scheduler.spawn(scrape_telegram_preview(ctx, role))
    else:
        task = await scheduler.spawn(loop_send_coins(ctx.channel, task_type, ctx, role))

    if ctx.channel.id not in running_tasks:
        running_tasks[ctx.channel.id] = {}
    running_tasks[ctx.channel.id][task_type] = task
    await ctx.send(f'Started sending {task_type} coin information. 📈', ephemeral=True)

    # Schedule the purge if messages exceed the limit of 10
    asyncio.create_task(monitor_and_purge(ctx.channel, limit=10))




@interactions.slash_command(
    name="new",
    description="Start sending newly created coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False,
    options=[
        {
            "name": "role",
            "description": "The role to mention in the alerts.",
            "type": interactions.OptionType.ROLE,
            "required": False  # Make this option optional
        }
    ]
)
async def new(ctx, role: interactions.Role = None):
    await start_task(ctx, "new", role)


@interactions.slash_command(
    name="soaring",
    description="Start sending soaring coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False,
    options=[
        {
            "name": "role",
            "description": "The role to mention in the alerts.",
            "type": interactions.OptionType.ROLE,
            "required": False  # Make this option optional
        }
    ]
)
async def soaring(ctx, role: interactions.Role = None):
    await start_task(ctx, "soaring", role)


@interactions.slash_command(
    name="completing",
    description="Start sending completing coin information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False,
    options=[
        {
            "name": "role",
            "description": "The role to mention in the alerts.",
            "type": interactions.OptionType.ROLE,
            "required": False  # Make this option optional
        }
    ]
)
async def completing(ctx, role: interactions.Role = None):
    await start_task(ctx, "completing", role)


@interactions.slash_command(
    name="stop",
    description="Stop sending token information.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False
)
async def stop(ctx):
    if await admin_command(ctx):
        stopped_any = False
        if ctx.channel.id in running_tasks:
            for task_type in ["soaring", "new", "completing", "dexsignals"]:
                if task_type in running_tasks[ctx.channel.id]:
                    await running_tasks[ctx.channel.id][task_type].close()
                    del running_tasks[ctx.channel.id][task_type]
                    stopped_any = True

            await ctx.channel.purge()  # Optionally clear messages

        if stopped_any:
            await ctx.send(f'Stopped sending token information and deleted all messages in this channel. ❌', ephemeral=True)
        else:
            await ctx.send('No active tasks to stop in this channel. ❌', ephemeral=True)
    else:
        await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)


@interactions.slash_command(
    name="clear",
    description="Clear all messages from this channel.",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
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
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
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

async def loop_send_coins(channel, task_type, ctx, role=None):
    """Loop to continuously send coin information."""
    while True:
        try:
            await send_coins(channel, task_type, ctx, role)
        except Exception as e:
            logging.error(f"Error in loop_send_coins for {task_type}: {e}")
        await asyncio.sleep(30)


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
        
        # Fetch data synchronously
        data = await fetch_data(url)

        if data and 'data' in data and 'token' in data['data']:
            item = data['data']['token']
            coin_key = (item['name'], item['symbol'], item['address'])
            name_dc = ctx.author.global_name

            # Fetch data from synchronous functions or properly await asynchronous ones
            connected_wallets = count_connected_wallets(await fetch_bubblemap_data(item['address']))
            socials = get_socials(item.get('social_links', {}))

            guildname = ctx.guild.name
            coins_collection = db[f'coins_{guildname}']

            existing_coin = coins_collection.find_one({'address': item['address']})

            if coin_key not in seen_coins and not existing_coin:
                seen_coins[coin_key] = {
                    'address': item['address'],
                    'called_mcap': int(float(item['market_cap'])),
                    'highest_mcap': int(float(item['market_cap'])),  # Initialize highest_mcap with the first market cap
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
                        'highest_mcap': existing_coin.get('highest_mcap', int(float(item['market_cap']))),
                        'market_cap': int(float(item['market_cap'])),
                        'called_at': existing_coin['called_at'],
                        'called_by': existing_coin['called_by']
                    }
                called_by = seen_coins[coin_key]['called_by']

            logging.info(f"Called by: {called_by}")

            # Calculate the profit percentage using the highest_mcap instead of current market cap
            highest_mcap = seen_coins[coin_key].get('highest_mcap', int(float(item['market_cap'])))

            # Check if the current market cap is the new highest
            current_market_cap = int(float(item['market_cap']))
            if current_market_cap > highest_mcap:
                logging.info(f"New highest market cap detected for {item['symbol']}. Updating highest_mcap.")
                update_highest_mcap(item['address'], current_market_cap, guildname)
                seen_coins[coin_key]['highest_mcap'] = current_market_cap

            embed = await generate_embed_ca(item, socials, connected_wallets, called_by)
            if embed:
                await ctx.send(f'{item["address"]}', embeds=[embed])
            else:
                logging.error(f"No valid embed created for address {address}.")
                await ctx.send(f"No valid data found for address {address}.")
        else:
            logging.error(f"Failed to fetch data for address {address}.")
            await ctx.send(f"No valid data found for address {address}.")
    except Exception as e:
        logging.error(f"Error in ca command: {e}")
        await ctx.send(f"An error occurred while processing the request.")


@interactions.slash_command(
    name="dexsignals",
    description="Start sending signals from the DEX Paid Coins",
    default_member_permissions=interactions.Permissions.MANAGE_GUILD,
    dm_permission=False,
    options=[
        {
            "name": "role",
            "description": "The role to mention in the alerts.",
            "type": interactions.OptionType.ROLE,
            "required": False  # Make this option optional
        }
    ]
)
async def dexsignals(ctx, role: interactions.Role = None):
    if await admin_command(ctx):
        await start_task(ctx, "dexsignals", role)
    else:
        await ctx.send('You do not have the required permissions to use this command.', ephemeral=True)

        
async def scrape_telegram_preview(ctx, role):
    """Scrape the Telegram preview page for the last three messages and send signals."""
    url = 'https://t.me/s/dex_is_paid'
    last_message_time = None
    processed_addresses = set()  # Set to keep track of processed contract addresses

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        page_content = await response.text()
                        soup = BeautifulSoup(page_content, 'html.parser')

                        # Find all message blocks
                        message_blocks = soup.find_all('div', class_='tgme_widget_message_wrap')

                        # Only check the last three messages (from the bottom)
                        message_blocks = message_blocks[-3:]

                        new_addresses = set()

                        for block in reversed(message_blocks):  # Process from bottom to top
                            try:
                                # Extract the message time
                                message_time_element = block.find('time')
                                if message_time_element:
                                    message_time = message_time_element['datetime']

                                    if last_message_time is None or message_time > last_message_time:
                                        # Extract the contract address
                                        code_element = block.find('code')
                                        if code_element:
                                            contract_address = code_element.get_text()

                                            # Check if the address has already been processed
                                            if contract_address not in processed_addresses:
                                                new_addresses.add(contract_address)
                                                processed_addresses.add(contract_address)  # Mark as processed
                                                last_message_time = message_time
                            except Exception as inner_e:
                                logging.error(f"Error processing block: {inner_e}")

                        if new_addresses:
                            valid_addresses = set()

                            for address in new_addresses:
                                api_url = f"{FETCH_COIN_DATA}{address}"
                                data = await fetch_data(api_url)
                                if data and 'data' in data and 'token' in data['data']:
                                    item = data['data']['token']
    
                                    connected_wallets = count_connected_wallets(await fetch_bubblemap_data(item['address']))
                                    socials = get_socials(item.get('social_links', {}))
                                    topbuyers = await fetch_top_buyers(item['address'])

                                    embed = await generate_simple_embed(item, socials, connected_wallets, topbuyers, role)
                                    if embed:
                                        if role:
                                            await ctx.channel.send(content=f"{role.mention}", embeds=[embed])
                                        else:
                                            await ctx.channel.send(f"{item['address']}", embeds=[embed])
                                        valid_addresses.add(address)

                            if not valid_addresses:
                                await ctx.send('No valid data found for the extracted addresses.', ephemeral=True)

                    else:
                        logging.error(f"Failed to fetch the page, status code: {response.status}")

                # Wait for 5 seconds before checking again
                await asyncio.sleep(5)

            except Exception as e:
                logging.error(f"Error in scrape_telegram_preview: {e}", exc_info=True)
                await asyncio.sleep(30)  # Wait before retrying
        
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
            'highest_mcap': market_cap,  # Use highest_mcap here
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
                'highest_mcap': market_cap,  # Use highest_mcap here
                'market_cap': market_cap,
                'called_at': called_at,
                'called_by': called_by
            }},
            upsert=True
        )

def update_highest_mcap(address, current_mcap, guildname):
    """Update the highest market cap in the database."""
    coins_collection = db[f'coins_{guildname}']

    # Update or insert the highest_mcap for the coin
    coins_collection.update_one(
        {'address': address},
        {'$set': {'highest_mcap': current_mcap}},
        upsert=True
    )
    logging.info(f"Updated highest_mcap for address {address} with value: {current_mcap}")


# Start the bot
bot.start()
