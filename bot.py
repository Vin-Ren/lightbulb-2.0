import os
import sys
import dotenv

import discord
from discord.ext import commands

from utils.printer import PrettyPrinter, MultiWritePipe


class Bot(commands.Bot):
    def __init__(self, *args, printer=PrettyPrinter(), **options):
        super().__init__(*args, **options)
        self.PRINTER = printer


def setup(config: dict):
    config.setdefault("LOG_FILE", 'logs.log')
    config.setdefault("COGS_DIR", 'cogs')
    try:
        open(config["LOG_FILE"])
    except FileNotFoundError:
        with open(config["LOG_FILE"], 'w') as f:
            pass
    
    printer = PrettyPrinter()
    printer.target_pipe=MultiWritePipe(open(config["LOG_FILE"]), sys.stdout)
    
    intents = discord.Intents.default()
    intents.message_content = True
    bot = Bot(command_prefix=commands.when_mentioned_or("~"), intents=intents, printer=printer)
    for _file in os.listdir(config["COGS_DIR"]):
        if _file.endswith(".py"):
            bot.load_extension(f"{config['COGS_DIR']}.{_file[:-3]}")
    return bot
