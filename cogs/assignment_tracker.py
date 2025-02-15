from datetime import datetime
import discord
from discord.ext import commands, tasks

from bot import Bot


SAVE_FILENAME = "assignments.json"


class Assignment:
    def __init__(self, name: str, group: str, deadline: datetime, link: str):
        self.name = name
        self.group = group
        self.deadline = deadline
        self.link = link
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(data['name'], data['group'], datetime.fromisoformat(data['deadline']), data['link'])
    
    def to_dict(self):
        return {'name': self.name, 'group': self.group, 'deadline': self.deadline.isoformat(), 'link': self.link}


class ServerAssignmentManager:
    def __init__(self, server_id: str, announcer_channel_id: str, tracked_since: datetime = None):
        self.tracked_since = tracked_since if tracked_since else datetime.now()
        self.server_id = server_id
        self.announcer_channel_id = announcer_channel_id
        self.assignments = []
        self.past_assignments = []
        self.groups = set()
        self.subscriptions: dict[str, set[str]] = {} # {user: group}
        self.subscribers: dict[str, set[str]] = {} # {group: [users]}
    
    @classmethod
    def from_dict(cls, data: dict):
        pass
    
    def to_dict(self):
        return {
            
        }


class AssignmentTracker(commands.Cog):
    def __init__(self, bot_: Bot):
        self.bot = bot_
        self.assignments_by_server: dict[str, ServerAssignmentManager] = {}
        
        server_data = {
            'announcer_channel': '',
            'active_assignments': [
                {}
            ],
            'past_assignments': [
                {}
            ]
        }
    
    def _init_tasks(self):
        self.autosave_data.start()
    
    @tasks.loop(minutes=1)
    async def autosave_data(self):
        self.save()
    
    def load():
        pass
    
    def save():
        pass
    
    def get_manager(self, guild_id: str):
        return self.assignments_by_server[guild_id]
    
    async def has_been_setup(self, ctx: commands.Context):
        return ctx.guild.id not in self.assignments_by_server
    
    @commands.command(aliases=['trackerchannel', 'setup'])
    async def bind_tracker_announcer_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        if channel==None:
            channel = ctx.channel
        if ctx.guild.id not in self.assignments_by_server:
            self.assignments_by_server[ctx.guild.id] = ServerAssignmentManager(ctx.guild.id, channel.id)
            await ctx.send(f"Successfully setup tracker and set <#{channel.id}> as an announcer channel.")
        else:
            self.assignments_by_server[ctx.guild.id].announcer_channel_id=channel.id
            await ctx.send(f"Successfully set <#{channel.id}> as an announcer channel.")
        self.save()
    
    @commands.command(aliases=['creategroup'])
    @commands.check(has_been_setup)
    async def create_group(self, ctx: commands.Context, group_name: str):
        group_name = group_name.upper() # Case insensitive
        manager = self.get_manager(ctx.guild.id)
        if group_name not in manager.groups:
            manager.groups.add(group_name)
            self.save()
            return await ctx.send(f"Successfully created group<{group_name}>")
        await ctx.send(f"group<{group_name}> already exists.")
    
    @commands.command(aliases=['deletegroup'])
    @commands.check(has_been_setup)
    async def delete_group(self, ctx: commands.Context, group_name: str):
        group_name = group_name.upper() # Case insensitive
        manager = self.get_manager(ctx.guild.id)
        if group_name in manager.groups:
            manager.groups.remove(group_name)
            manager.subscribers.pop(group_name)
            for user in manager.subscriptions.keys():
                if group_name in manager.subscriptions[user]:
                    manager.subscriptions[user].pop(group_name)
            self.save()
            return await ctx.send(f"Successfully removed group<{group_name}>")
        await ctx.send(f"group<{group_name}> does not exist.")
    
    @commands.command(aliases=['listall', 'listallassign'])
    @commands.check(has_been_setup)
    def list_tracked_assignments(self, ctx: commands.Context):
        pass
    
    @commands.command(aliases=['listmine', 'listmyassign'])
    @commands.check(has_been_setup)
    def list_tracked_assignments(self, ctx: commands.Context):
        pass
    
    @commands.command(aliases=['assign', 'add'])
    @commands.check(has_been_setup)
    def add_assignment(self, ctx: commands.Context, name: str, group: str = "", deadline: str = "", *, links: str = ""):
        pass
    
    @commands.command(aliases=['edit'])
    @commands.check(has_been_setup)
    def edit_assignment(self, ctx: commands.Context, assignment_idx: str, group: str = "", deadline: str = "", *, links: str = ""):
        pass


def setup(bot):
    bot.add_cog(AssignmentTracker(bot))
