import os
import discord
import aiohttp
import asyncio
import json
import logging
from discord.ext import tasks
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO

# Setup logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

# Fortnite API endpoints
ENDPOINTS = [
    "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/mp-item-shop",
    "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/shopoffervisuals"
]

# Allowed image formats
IMAGE_FORMATS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tga", ".bmp")

# Load previous assets
def load_previous_assets():
    try:
        with open("previous_assets.json", "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("No previous assets found or invalid JSON. Starting fresh.")
        return {}

previous_assets = load_previous_assets()

# Save updated assets
def save_previous_assets():
    with open("previous_assets.json", "w") as file:
        json.dump(previous_assets, file, indent=4)

# Discord bot setup
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
client = discord.Client(intents=intents)

# Helper function to extract codename from URL
def extract_codename_from_url(url):
    parts = url.split('/')
    for part in parts:
        if 'billboard' in part:
            return part.split('-')[1]  # Extracts the codename after 'billboard-'
    return None

# Helper function to check if URL is related to billboard assets
def is_billboard_asset(url):
    return '/billboard-' in url

# Extract image URLs from API response
def extract_image_urls(data):
    image_urls = {}

    def recursive_search(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and value.lower().endswith(IMAGE_FORMATS):
                    image_urls[value] = obj.get("lastModified", "unknown")
                else:
                    recursive_search(value)
        elif isinstance(obj, list):
            for item in obj:
                recursive_search(item)

    recursive_search(data)
    logger.debug(f"Extracted image URLs: {image_urls}")
    return image_urls

# Handle the merging of related billboard assets
async def handle_billboard_assets(new_assets, channel):
    merged_assets = {}
    # Organize assets by codename
    for asset in new_assets:
        if "/billboard-" in asset:
            codename = extract_codename_from_url(asset)
            if codename not in merged_assets:
                merged_assets[codename] = {'background': None, 'character': None, 'itemstack': None, 'logo': None, 'figure': None}
            # Assign assets to their respective categories
            if 'bg' in asset:
                merged_assets[codename]['background'] = asset
            elif 'character' in asset:
                if 'jn' in asset:  # Lego character
                    merged_assets[codename]['figure'] = asset
                else:
                    merged_assets[codename]['character'] = asset
            elif 'itemstack' in asset:
                merged_assets[codename]['itemstack'] = asset
            elif 'logo' in asset:
                merged_assets[codename]['logo'] = asset
            elif 'figure' in asset:
                merged_assets[codename]['figure'] = asset

    # Send individual assets before merging them
    for codename, assets in merged_assets.items():
        for key, asset in assets.items():
            if asset:
                embed = discord.Embed(title=f"New {key.capitalize()} Asset Detected", description=asset)
                embed.set_image(url=asset)
                await channel.send(embed=embed)

    # Merge assets if all required components are present
    for codename, assets in merged_assets.items():
        if all(assets[key] for key in ['background', 'character', 'itemstack']):  # Ensure these are present
            if assets['figure']:  # If figure (Lego) asset exists
                # Send merged character and figure billboard
                embed = discord.Embed(title=f"Merged Asset for {codename} (Character)", description=assets['character'])
                embed.set_image(url=assets['character'])
                await channel.send(embed=embed)

                embed = discord.Embed(title=f"Merged Asset for {codename} (Figure)", description=assets['figure'])
                embed.set_image(url=assets['figure'])
                await channel.send(embed=embed)
            else:
                # Regular merged asset
                merged_url = f"https://merged-assets/{codename}"  # Placeholder for merging process
                embed = discord.Embed(title=f"Merged Asset for {codename}", description=merged_url)
                embed.set_image(url=merged_url)
                await channel.send(embed=embed)

# Fetch Fortnite assets
async def fetch_fortnite_assets():
    global previous_assets
    detected_changes = []
    logger.debug("Fetching Fortnite assets...")

    async with aiohttp.ClientSession() as session:
        for endpoint in ENDPOINTS:
            try:
                async with session.get(endpoint, timeout=10) as response:
                    data = await response.json()
                    logger.debug(f"Data fetched from {endpoint}: {data}")
                    new_assets = extract_image_urls(data)

                    # Compare with previous assets
                    if endpoint in previous_assets:
                        old_assets = previous_assets[endpoint]
                        for asset, last_modified in new_assets.items():
                            if asset not in old_assets or old_assets[asset] != last_modified:
                                detected_changes.append(asset)  # Add asset to detected changes if updated or added
                    else:
                        detected_changes.extend(new_assets.keys())  # If it's the first time detecting this endpoint

                    previous_assets[endpoint] = new_assets
            except aiohttp.ClientError as e:
                logger.error(f"Error fetching assets from {endpoint}: {e}")

    save_previous_assets()  # Save the updated assets
    return detected_changes  # Return the list of updated or new assets

# Check for updates
@tasks.loop(seconds=45)
async def check_for_updates():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    if not channel:
        logger.error("Invalid channel ID. Cannot send updates.")
        return

    logger.debug("Checking for updates...")

    detected_assets = await fetch_fortnite_assets()

    # If no new assets, skip
    if not detected_assets:
        logger.debug("No new assets detected.")
        return

    logger.debug(f"Detected assets: {detected_assets}")

    for asset_url in detected_assets:
        if "/billboard-" in asset_url:  # Only process billboard assets for merging
            await handle_billboard_assets([asset_url], channel)
        else:
            await send_asset(asset_url, channel)

# Send individual assets
async def send_asset(url, channel):
    try:
        embed = discord.Embed(title="New Asset Detected", description=url)
        embed.set_image(url=url)
        await channel.send(embed=embed)
    except discord.HTTPException as e:
        logger.error(f"Error sending asset {url}: {e}")

@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user}")
    check_for_updates.start()

client.run(TOKEN)
