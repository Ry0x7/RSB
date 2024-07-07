import requests
import logging
import interactions
import aiojobs
from datetime import datetime, timedelta
import asyncio
import random
import dotenv
import os

dotenv.load_dotenv()

# Correct token and default_scope initialization
bot = interactions.Client(token=os.getenv('DISCORD_TOKEN'))

BASE_URL = 'https://gmgn.ai/defi/quotation/v1/rank/sol/pump'
PHOTON_API_URL = 'https://photon-sol.tinyastro.io/api/memescope/search'

last_soaring_data = None
last_new_data = None
owner_username = "chakazzz"

logging.basicConfig(level=logging.INFO)

# Dictionary to keep track of running tasks and sent messages
running_tasks = {
    "soaring": {},
    "new": {}
}
sent_soaring_messages = {}
sent_new_messages = {}

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
        return f"{time_diff.days} days ago"
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

    field_value = (
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
    )

    if len(field_value) > 1024:
        logging.warning(f"Field value for {item['address']} exceeded 1024 characters. Truncating.")
        field_value = field_value[:1021] + "..."

    embed.add_field(
        name=f"{item['name']} [{item['symbol']}]",
        value=field_value,
        inline=False
    )
    return embed

async def filter_coins(coins):
    filtered_coins = []
    for coin in coins:
        response = requests.get(f"{PHOTON_API_URL}?address={coin['address']}")
        if response.status_code == 200:
            coin_data = response.json()
            snipers_count = coin_data.get("snipers_count", 0)
            holders_below_35 = coin_data.get("holders_below_35", 100)
            if snipers_count <= 10 and holders_below_35 >= 35:
                filtered_coins.append(coin)
    return filtered_coins

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
                    await edit_message_with_retry(message, embed)
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

async def edit_message_with_retry(message, embed, retries=5):
    for attempt in range(retries):
        try:
            await message.edit(embeds=[embed])
            return
        except RuntimeError as e:
            if 'Attempted to lock a bucket that is already locked' in str(e):
                wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff
                await asyncio.sleep(wait_time)
            else:
                raise e
    logging.error("Failed to edit message after multiple retries")

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
            except interactions.errors.HTTPException as e:
                if e.response.status == 429:
                    retry_after = e.response.headers.get('Retry-After')
                    await asyncio.sleep(float(retry_after))
                    await delete_old_messages(channel, valid_addresses, sent_messages)
            except Exception as e:
                logging.error(f"Error in delete_old_messages: {e}")

async def send_soaring_coins(channel):
    global last_soaring_data
    try:
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
        url = build_query_url(BASE_URL, params)
        data = fetch_data(url)
        if data and data['data']['rank'] != last_soaring_data:
            last_soaring_data = data['data']['rank']
            valid_addresses = {item['address'] for item in data['data']['rank']}
            filtered_coins = await filter_coins(data['data']['rank'])
            for item in filtered_coins:
                await send_or_update_embed(channel, item, "🚀 Soaring Coin", sent_soaring_messages)
            await delete_old_messages(channel, valid_addresses, sent_soaring_messages)
    except Exception as e:
        logging.error(f"Error in send_soaring_coins: {e}")

async def send_new_created_coins(channel):
    global last_new_data
    try:
        params = {
            'limit': '50',
            'orderby': 'created_timestamp',
            'direction': 'desc',
            'new_creation': 'true',
            'max_marketcap': '10000',
            'min_holder_count': '15',
        }
        url = build_query_url(BASE_URL, params)
        data = fetch_data(url)
        if data and data['data']['rank'] != last_new_data:
            last_new_data = data['data']['rank']
            valid_addresses = {item['address'] for item in data['data']['rank']}
            filtered_coins = await filter_coins(data['data']['rank'])
            for item in filtered_coins:
                await send_or_update_embed(channel, item, "🌟 Newly Created Coin", sent_new_messages)
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
        for task_type in ["soaring", "new"]:
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
        for task_type in ["soaring", "new"]:
            if ctx.channel.id in running_tasks[task_type]:
                await running_tasks[task_type][ctx.channel.id].close()
                del running_tasks[task_type][ctx.channel.id]
        scheduler = await aiojobs.create_scheduler()
        task = await scheduler.spawn(loop_send_soaring_coins(ctx.channel))
        running_tasks["soaring"][ctx.channel.id] = task
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

async def loop_send_new_created_coins(channel):
    while True:
        try:
            await send_new_created_coins(channel)
        except Exception as e:
            logging.error(f"Error in loop_send_new_created_coins: {e}")
        await asyncio.sleep(4)  # Wait for 4 seconds before sending the next update

async def monitor_tasks():
    while True:
        for task_type in ["soaring", "new"]:
            for channel_id, task in list(running_tasks[task_type].items()):
                if task.done():
                    logging.warning(f"Task for channel {channel_id} has stopped. Restarting {task_type} task...")
                    channel = await bot.fetch_channel(channel_id)
                    scheduler = await aiojobs.create_scheduler()
                    if task_type == "soaring":
                        new_task = await scheduler.spawn(loop_send_soaring_coins(channel))
                    else:
                        new_task = await scheduler.spawn(loop_send_new_created_coins(channel))
                    running_tasks[task_type][channel_id] = new_task
        await asyncio.sleep(60)  # Check every minute

bot.start()
