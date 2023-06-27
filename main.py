import dotenv
import os
from argparse import ArgumentParser
from bot import setup


def main(development):
    bot = setup(os.environ) #type:ignore
    token = os.getenv("TOKEN")
    if development:
        bot.cogs['Core'].set_presence = bot.cogs['Core'].maintenance_presence
        token = os.getenv("DEV_TOKEN")
    bot.run(token)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('-c', '--config', dest="config_name", default='.env', help="Sets config file")
    parser.add_argument('-d', '--dev', action="store_true", dest="is_development", help="Sets development to true")
    args = parser.parse_args()
    dotenv.load_dotenv(args.config_name)
    main(args.is_development)
