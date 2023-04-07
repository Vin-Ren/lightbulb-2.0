import os
import asyncio
from dotenv import dotenv_values
import discord
from discord.ext import commands
from discord import Status, Activity, ActivityType

config = dotenv_values()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or("~"), intents=intents)

# @bot.event
# async def on_ready():
#     await asyncio.sleep(1)
#     await bot.change_presence(status=Status.do_not_disturb, activity=Activity(type=ActivityType.watching, name="Under Maintenance."))

def main():
    for _file in os.listdir("cogs"):
        if _file.endswith(".py"):
            bot.load_extension(f"cogs.{_file[:-3]}")
    bot.run(config['TOKEN'])

main()
