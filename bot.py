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


def setup(config: dict, development_mode=False):
    config.setdefault("LOG_FILE", 'logs.log')
    config.setdefault("COGS_DIR", 'cogs')
    try:
        open(config["LOG_FILE"])
    except FileNotFoundError:
        with open(config["LOG_FILE"], 'w') as f:
            pass
    
    target_pipe=MultiWritePipe(open(config["LOG_FILE"], 'w', encoding='utf-8'), sys.stdout)
    printer = PrettyPrinter(debug=development_mode, target_pipe=target_pipe)
    
    printer.print_debug("Printer Init", {
        'pipes': target_pipe,
        "debug": printer.debug
    })
    
    intents = discord.Intents.default()
    intents.message_content = True
    bot = Bot(command_prefix=commands.when_mentioned_or("~"), intents=intents, printer=printer, test_guilds=[] if development_mode else None)
    for _file in os.listdir(config["COGS_DIR"]):
        if _file.endswith(".py"):
            bot.load_extension(f"{config['COGS_DIR']}.{_file[:-3]}")
    return bot
