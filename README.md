# RodentSignalBot

RodentSignalBot is a Discord bot for monitoring Solana memecoin activity and posting automated signal embeds into Discord channels.

It focuses on early discovery and momentum tracking by combining on-chain and market metadata (market cap, holders, wallet behavior, liquidity, social links, and more) into readable alerts.

## Project Purpose

This project was built to:

- Watch newly launched and trending pump.fun/Solana tokens.
- Surface high-signal token metrics in Discord in near real time.
- Track whether a token has been seen before and calculate simple performance progression.
- Provide direct quick-buy links and context checks (top buyers, wallet clustering, DEX paid status, CTO-related indicators).

## Main Capabilities

- Slash-command driven Discord workflow.
- Continuous feed modes for different token profiles:
	- new listings
	- soaring tokens
	- bonding curve completion candidates
	- DEX paid Telegram feed parsing
	- radar signal feed processing
- Per-token embed formatting with:
	- market cap, age, volume, holders
	- top-buyer behavior summaries
	- developer/creator status indicators
	- social links (X, Telegram, Website)
	- Bubblemap and DEX check links
- MongoDB-backed storage for seen calls and highest market cap tracking.

## Tech Stack

- Python
- discord-py-interactions (`interactions`)
- aiohttp + asyncio
- MongoDB (`pymongo`)
- BeautifulSoup (for Telegram preview scraping)

## Data Sources Used by the Bot

The bot queries multiple external endpoints, including:

- gmgn.ai quotation/token APIs
- pump.fun replies API
- checkdex.xyz token check API
- Bubblemaps data endpoint
- CoinGecko (SOL/USD conversion)
- Telegram preview page scraping (`t.me/s/dex_is_paid`)
- Axiom radar recent alerts endpoint

## Repository Structure

- `signalbot.py`: Main Discord bot with slash commands, polling loops, embed generation, and MongoDB tracking.
- `bondedcoinshook.py`: Standalone webhook sender script (non-slash-command flow) for posting filtered pairs to a Discord webhook.
- `test.py`: Simple HTTP test script for one gmgn API request.
- `requirements.txt`: Python dependencies.

## Prerequisites

- Python 3.10+ recommended
- MongoDB instance (local or hosted)
- Discord bot token with the required bot permissions

## Environment Variables

Create a `.env` file in the project root.

Required for `signalbot.py`:

- `DISCORD_TOKEN`: Discord bot token.
- `MONGO_URI`: MongoDB connection URI.

Used by `bondedcoinshook.py`:

- `WEBHOOK_URL`: Discord webhook URL.
- `MONGO_URI`: MongoDB connection URI.

Example:

```env
DISCORD_TOKEN=your_discord_bot_token
MONGO_URI=mongodb://localhost:27017
WEBHOOK_URL=https://discord.com/api/webhooks/...
```

## Installation

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies.

```bash
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Windows (cmd)
.venv\Scripts\activate.bat

pip install -r requirements.txt
```

## Running

Run the main Discord bot:

```bash
python signalbot.py
```

Optional webhook-only script:

```bash
python bondedcoinshook.py
```

## Discord Slash Commands

The main bot exposes these commands:

- `/new [role]`: Start live alerts for very recent token creations.
- `/soaring [role]`: Start live alerts for soaring tokens.
- `/completing [role]`: Start live alerts for tokens close to completion criteria.
- `/dexsignals [role]`: Start monitoring Telegram DEX paid preview signals.
- `/radarsignals [role]`: Start monitoring radar alerts and post/update embeds.
- `/ca <address>`: Fetch and display detailed information for a specific token address.
- `/stop`: Stop running loops in the current channel and purge channel messages.
- `/clear`: Purge channel messages.
- `/reboot`: Restart active token loops in the current channel.

Most administrative commands are restricted to `MANAGE_GUILD` (or admin/owner checks in code).

## Persistence Model

- Database: `crypto_bot`
- Collections are created per guild for seen token tracking:
	- `coins_<guild_name>`

Stored data includes:

- token address, name, symbol
- called market cap
- latest/highest market cap
- called timestamp and caller identity

## Notes and Operational Guidance

- This bot makes frequent external API requests and runs continuous loops; deploy with proper monitoring.
- Some network logic relies on a proxy path in the source code. For production, move proxy credentials to environment variables and never commit secrets.
- The command loops can post often; use dedicated channels for signals.

## Disclaimer

This software is for informational/automation purposes only and is not financial advice. Always do your own research before trading.

## Portfolio Landing Page

This repository includes a simple static landing page for GitHub Pages:

- `index.html`: Portfolio-style project overview with a static Discord alert preview/demo.
- `styles.css`: Responsive dark theme styling for the hero, feature cards, and demo preview.
- `.nojekyll`: Tells GitHub Pages to publish the static files as-is.

To publish it, enable GitHub Pages in the repository settings and select the current branch with the repository root as the Pages source.
