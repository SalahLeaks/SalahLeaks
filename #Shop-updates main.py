import discord
import os
import requests
import json
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

API_URL = "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/mp-item-shop"
SECTIONS_FILE = "shop_sections.json"

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# Ensure the shop sections file exists
def ensure_file():
    if not os.path.exists(SECTIONS_FILE):
        with open(SECTIONS_FILE, "w") as f:
            json.dump([], f)

# Fetch the shop sections from the API
def fetch_shop_sections():
    try:
        response = requests.get(API_URL)
        if response.status_code == 200:
            data = response.json()

            # Extract the sections from the response
            sections = []
            if "shopData" in data and "sections" in data["shopData"]:
                for section in data["shopData"]["sections"]:
                    display_name = section.get("displayName", None)
                    section_id = section.get("sectionID", None)
                    category = section.get("category", None)  # May not be present in every section
                    background_url = section.get("metadata", {}).get("background", {}).get("customTexture", None)

                    # Only include valid sections with displayName and sectionID
                    if display_name and section_id:
                        sections.append({
                            "displayName": display_name,
                            "sectionID": section_id,
                            "category": category,  # category might be None
                            "background_url": background_url  # Add background URL
                        })

            return sections
        else:
            print(f"Failed to fetch shop data. Status Code: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching shop sections: {e}")
        return []

# Load previous shop sections from file (if exists)
def load_previous_sections():
    ensure_file()
    try:
        with open(SECTIONS_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

# Save new shop sections to file
def save_sections(sections):
    with open(SECTIONS_FILE, "w") as f:
        json.dump(sections, f, indent=4)

# Function to detect changes between the new and old sections
def detect_changes(new_sections, old_sections):
    changes = []
    old_dict = {s["sectionID"]: s for s in old_sections}

    for section in new_sections:
        section_id = section["sectionID"]
        if section_id not in old_dict or old_dict[section_id] != section:
            changes.append(section)

    return changes

# Task to check shop updates every 45 seconds
async def check_shop_updates():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    while not client.is_closed():
        print("Checking for shop updates...")

        new_sections = fetch_shop_sections()
        old_sections = load_previous_sections()
        changes = detect_changes(new_sections, old_sections)

        if changes:
            print("New or updated sections found!")
            save_sections(new_sections)  # Update file

            for section in changes:
                embed = discord.Embed()  # No color
                embed.add_field(name="Display Name:", value=section['displayName'], inline=True)
                embed.add_field(name="Section ID:", value=section['sectionID'], inline=True)

                if section.get("category"):
                    embed.add_field(name="Category:", value=section['category'], inline=False)
                if section.get("background_url"):
                    embed.add_field(name="Background:", value=f"[Background]({section['background_url']})", inline=False)

                # Send the embedded message to the Discord channel
                await channel.send(embed=embed)

        else:
            print("No new shop sections detected.")

        await asyncio.sleep(45)  # Wait before checking again

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    client.loop.create_task(check_shop_updates())

# Run the bot
client.run(TOKEN)
