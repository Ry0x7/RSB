import requests
import json
import os
import pymongo
from datetime import datetime
import dotenv

# Load environment variables
dotenv.load_dotenv()

# MongoDB setup
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
MONGO_URI = os.getenv('MONGO_URI')
mongo_client = pymongo.MongoClient(MONGO_URI)
db = mongo_client['crypto_bot']
coins_collection = db['coins']

# API parameters
api_base_url = "https://gmgn.ai/defi/quotation/v1/pairs/sol/new_pairs"
params = {
    "limit": 100,
    "orderby": "price_change_percent1m",
    "direction": "asc",
    "launchpad": "pump",
    "filters[]": ["not_honeypot", "pump", "renounced", "frozen"],
    "min_marketcap": 50000,
    "min_volume": 50000
}

# Fetch data from the API
response = requests.get(api_base_url, params=params)
if response.status_code == 200:
    data = response.json()
else:
    print(f"Failed to fetch data: {response.status_code} - {response.text}")
    exit()

# To store processed addresses to avoid duplicates
processed_addresses = set()

# Iterate over all pairs
for pair in data['data']['pairs']:
    token_info = pair['base_token_info']

    # Skip if top holder rate is >= 30%
    top_holder_rate = token_info.get('top_10_holder_rate', 0)
    if top_holder_rate >= 0.30:
        print(f"Skipping {token_info['symbol']} due to high top holder rate.")
        continue

    # Fetch the last market cap from MongoDB
    last_entry = coins_collection.find_one({"address": token_info['address']})

    # Calculate percentage change
    significant_change = False
    if last_entry:
        last_mcap = last_entry['called_mcap']
        current_mcap = token_info['market_cap']
        percentage_change = ((current_mcap - last_mcap) / last_mcap) * 100
        trend_indicator = "🟢" if percentage_change > 0 else "🔴" if percentage_change < 0 else ""
        percentage_change_str = f"{percentage_change:.2f}% {trend_indicator}"

        # Check for significant change
        significant_change = abs(percentage_change) >= 100
    else:
        percentage_change_str = "N/A"
        # Insert the new coin if not found in the database
        coins_collection.insert_one({
            "address": token_info['address'],
            "called_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            "called_mcap": token_info['market_cap'],
            "name": token_info['name'],
            "symbol": token_info['symbol']
        })

    # Skip if the address has already been processed and there's no significant change
    if token_info['address'] in processed_addresses and not significant_change:
        continue

    # Calculate age of the coin
    creation_timestamp = pair['creation_timestamp']
    current_timestamp = int(datetime.utcnow().timestamp())
    age_seconds = current_timestamp - creation_timestamp
    age_days = age_seconds // (24 * 3600)
    age_str = f"{age_days} days"

    # Quick buy links using token_info base_address
    quick_buy = (
        f"**[Photon](https://photon-sol.tinyastro.io/en/r/@rodent0x/{token_info['address']})** ∙ "
        f"**[Bull](https://bullx.io/terminal?chainId=1399811149&address={token_info['address']})** ∙ "
        f"**[PepeB](https://t.me/pepeboost_sol04_bot?start={token_info['address']})** ∙ "
        f"**[Troj](https://t.me/hector_trojanbot?start=r-j3rrycr3dits-{token_info['address']})** "
    )

    # Determine dex_paid and dev_sold statuses
    dex_paid = token_info.get('dexscr_update_link', 0) == 1 or token_info.get('dexscr_ad', 0) == 1
    dev_sold = "✅" if token_info.get('creator_close', False) else "❌"

    # Format message
    description = (
        f"```{token_info['address']}```\n"
        f"**📈 Market Cap:** `${token_info['market_cap']:,.2f}`  Seen at: `{percentage_change_str}`\n"
        f"**⏳ Age:** `{age_str}`\n"
        f"**💧 Liquidity:** `${pair['liquidity']}` \n"
        f"**🔄 Volume (24h):** `${token_info['volume_24h']:,.2f}`\n"
        f"**👥 Holders:** `{token_info['holder_count']}`\n"
        f"**🔥 Burn Status:** {token_info['burn_status']} \n"
        f"**🧑‍💻 Dev Balance Rate:** {token_info['creator_balance_rate']:.2%} \n"
        f"**🐀 Rat Trader Rate:** {token_info['rat_trader_amount_rate']:.2%} \n"
        f"**🫂 CTO Check:** {'Yes' if token_info['cto_flag'] == 1 else 'No'} \n"
        f"**🐦 Twitter Change:** {'Yes' if token_info['twitter_change_flag'] == 1 else 'No'} \n"
        f"**Dex Paid?:** {'✅' if dex_paid else '❌'} ∙ **Dev Sold?:** {dev_sold}\n"
        f"**Top Holder Rate:** {top_holder_rate:.2%}\n"
        f"{quick_buy}\n"
    )

    fields = []
    twitter_username = token_info['social_links'].get('twitter_username')
    telegram = token_info['social_links'].get('telegram')
    website = token_info['social_links'].get('website')

    if twitter_username:
        fields.append({
            "name": "Twitter",
            "value": f"[{twitter_username}](https://twitter.com/{twitter_username})",
            "inline": True
        })

    if telegram:
        fields.append({
            "name": "Telegram",
            "value": f"[Join](https://t.me/{telegram})",
            "inline": True
        })

    if website:
        fields.append({
            "name": "Website",
            "value": f"[Link]({website})",
            "inline": True
        })

    webhook_message = {
        "embeds": [
            {
                "title": f"{token_info['name']} ({token_info['symbol']})",
                "description": description,
                "color": 5814783,
                "thumbnail": {
                    "url": token_info["logo"]
                },
                "fields": fields
            }
        ]
    }

    # Sending the POST request to the Discord webhook
    response = requests.post(WEBHOOK_URL, json=webhook_message)

    # Checking the response
    if response.status_code == 204:
        print(f"Message for {token_info['name']} successfully sent to Discord webhook")
        processed_addresses.add(token_info['address'])
    else:
        print(f"Failed to send message for {token_info['name']}: {response.status_code} - {response.text}")
