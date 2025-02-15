from datetime import datetime
import json
from typing import Literal

import discord
from discord.ext import commands, tasks

from bot import Bot


SAVE_FILENAME = "assignments.json"
DATETIME_FORMAT = "%d-%mT%H:%M%z"


class Assignment:
    def __init__(self, _id: str, name: str, groups: str, deadline: datetime, link: str):
        self.id = str(_id)
        self.name = name
        self.groups = groups
        self.deadline = deadline
        self.link = link
    
    def __str__(self):
        return f"Assignment#{self.id} {self.name} Deadline: {self.deadline.strftime("%a, %d %b %y")}"

    def get_relative_date(self):
        # TODO: fix
        return self.deadline.isoformat()
    
    def get_embed(self):
        embed = discord.Embed(title=f"Assignment - {self.name}")
        embed.add_field(name="ID", value=self.id)
        embed.add_field(name="Name", value=self.name)
        embed.add_field(name="Assigned Groups", value=", ".join(self.groups), inline=False)
        embed.add_field(name="Deadline", value=self.deadline.strftime("%a, %d %b %y"), inline=False)
        embed.add_field(name="Link to Resource", value=f"{self.link}", inline=False)
        return embed
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(data['id'], data['name'], data['groups'], datetime.fromisoformat(data['deadline']), data['link'])
    
    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'groups': self.groups, 'deadline': self.deadline.isoformat(), 'link': self.link}


class ServerAssignmentManager:
    def __init__(self, server_id: str, announcer_channel_id: str, tracked_since: datetime = None):
        self.tracked_since = tracked_since if tracked_since else datetime.now()
        self.server_id = server_id
        self.announcer_channel_id = announcer_channel_id
        self.assignments: dict[str, Assignment] = dict()
        self.past_assignments: dict[str, Assignment] = dict()
        self.groups: set[str] = set()
        self.subscriptions: dict[str, set[str]] = dict() # {user: [groups]}
        self.subscribers: dict[str, set[str]] = dict() # {group: [users]}
        self.group_assignments: dict[str, set[str]] = dict() # {group: [assigments]}
        self.user_checklist: dict[str, set[str]] # {user: [assignments]}
        self.last_assignment_id = 0
    
    @classmethod
    def from_dict(cls, data: dict):
        obj = cls(data['server_id'], data['announcer_channel_id'], datetime.fromisoformat(data['tracked_since']))
        obj.assignments = {_id: Assignment.from_dict(entry) for _id, entry in data['assignments'].items()}
        obj.past_assignments = {_id: Assignment.from_dict(entry) for _id, entry in data['past_assignments'].items()}
        obj.groups = set(data['groups'])
        obj.subscriptions = {user: set(entry) for user, entry in data['subscriptions'].items()}
        obj.subscribers = {group: set(entry) for group, entry in data['subscribers'].items()}
        obj.group_assignments = {group: set(entry) for group, entry in data['group_assignments'].items()}
        obj.user_checklist = {user: set(entry) for user, entry in data['user_checklist'].items()}
        obj.last_assignment_id = data['last_assignment_id']
        return obj
    
    def to_dict(self):
        return {
            'tracked_since': self.tracked_since.isoformat(),
            'server_id': self.server_id,
            'announcer_channel_id': self.announcer_channel_id,
            'assignments': {_id: assignment.to_dict() for _id, assignment in self.assignments.items()},
            'past_assignments': {_id: assignment.to_dict() for _id, assignment in self.past_assignments.items()},
            'groups': list(self.groups),
            'subscriptions': {user: list(groups) for user, groups in self.subscriptions.items()},
            'subscribers': {group: list(users) for group, users in self.subscribers.items()},
            'group_assignments': {group: list(assignment_id) for group, assignment_id in self.group_assignments.items()},
            'user_checklist': {user: list(assignment_id) for user, assignment_id in self.user_checklist.items()},
            'last_assignment_id': self.last_assignment_id
        }
    
    def create_group(self, group_name: str):
        group_name = group_name.upper()
        if group_name in self.groups:
            return False
        self.groups.add(group_name)
        self.subscribers[group_name] = set()
        self.group_assignments[group_name] = set()
        return True
    
    def delete_group(self, group_name: str):
        group_name = group_name.upper()
        if group_name not in self.groups:
            return False
        
        self.groups.remove(group_name)
        self.subscribers.pop(group_name)
        
        for user in self.subscriptions.keys():
            if group_name in self.subscriptions[user]:
                self.subscriptions[user].remove(group_name)
        
        for assignment_id in self.group_assignments[group_name]:
            self.assignments[assignment_id].groups.remove(group_name)
        return True
    
    def subscribe(self, user_id: str, group_name: str):
        group_name = group_name.upper()
        if group_name not in self.groups:
            return False
        if user_id in self.subscribers[group_name]:
            return False
        
        self.subscribers[group_name].add(user_id)
        
        if self.subscriptions.get(user_id) == None:
            self.subscriptions[user_id] = set()
        self.subscriptions[user_id].add(group_name)
        return True
    
    def unsubscribe(self, user_id: str, group_name: str):
        group_name = group_name.upper()
        if group_name not in self.groups:
            return False
        if user_id not in self.subscriptions:
            return False
        self.subscriptions[user_id].remove(group_name)
        self.subscribers[group_name].remove(user_id)
        return True

    def get_all_assignments(self):
        return sorted([assignment for assignment in self.assignments.values()], key=lambda e: e.deadline)
    
    def get_personal_assignments(self, user_id: str, include_completed: bool = True):
        assignment_ids = set()
        for group in self.subscriptions.get(user_id,[]):
            assignment_ids.update(self.group_assignments[group])
        if not include_completed:
            assignment_ids-=self.user_checklist.get(user_id, set())
        return sorted([self.assignments[_id] for _id in assignment_ids], key=lambda e: e.deadline)

    def checklist_assignment(self, user_id: str, assignment_id: str):
        user_id = str(user_id)
        assignment_id = str(assignment_id)
        if assignment_id not in self.assignments:
            return False
        self.user_checklist[user_id] = self.user_checklist.get(user_id, set())
        if assignment_id in self.user_checklist[user_id]:
            return False
        self.user_checklist[user_id].add(assignment_id)
        return True

    def unchecklist_assignment(self, user_id: str, assignment_id: str):
        user_id = str(user_id)
        assignment_id = str(assignment_id)
        self.user_checklist[user_id] = self.user_checklist.get(user_id, set())
        if assignment_id not in self.user_checklist[user_id]:
            return False
        self.user_checklist[user_id].remove(assignment_id)
        return True
    
    def create_assignment(self, name: str, groups: str, deadline: str, link: str):
        groups = groups.upper().split(',')
        self.last_assignment_id+=1
        assignment = Assignment(_id=self.last_assignment_id, name=name, groups=groups, deadline=datetime.strptime(deadline, DATETIME_FORMAT), link=link)
        # assume this assignment's deadline is within this year
        assignment.deadline = assignment.deadline.replace(year=datetime.now().year) 
        if len(assignment.link) and not assignment.startswith('http'):
            assignment = 'https://'+assignment
        for group in groups:
            self.group_assignments[group].add(assignment.id)
        self.assignments[assignment.id] = assignment
        return assignment
        # self.assignments.sort(key=lambda assignment: assignment.deadline) # Sorts by deadline
    
    def edit_assignment(self, assignment_id: str, field_name: Literal['name', 'deadline', 'groups', 'link'], value: str):
        if assignment_id not in self.assignments:
            return False
        assignment = self.assignments[assignment_id]
        if field_name == 'name':
            assignment.name = value
        elif field_name == 'deadline':
            newDeadline = datetime.strptime(value, DATETIME_FORMAT)
            newDeadline = newDeadline.replace(year=datetime.now().year)
            assignment.deadline = newDeadline
        elif field_name == 'groups':
            groups = value.upper().split(',')
            for group in self.assignments[assignment_id].groups:
                self.group_assignments[group].remove(assignment_id)
            for group in groups:
                self.group_assignments[group].add(assignment.id)
        elif field_name == 'link':
            if not value.startswith('http'):
                value = 'https://'+value
            assignment.link = value
        else:
            return False
        return True
    
    def delete_assignment(self, assignment_id: str):
        if assignment_id not in self.assignments:
            return
        for group in self.assignments[assignment_id].groups:
            self.group_assignments[group].remove(assignment_id)
        return self.assignments.pop(assignment_id)

    def archive_assignment(self, assignment_id: str):
        if assignment_id not in self.assignments:
            return False
        assignment = self.assignments[assignment_id]
        self.delete_assignment(assignment_id)
        self.past_assignments[assignment_id]=assignment


class AssignmentTracker(commands.Cog):
    def __init__(self, bot_: Bot):
        self.bot = bot_
        self.assignments_by_server: dict[str, ServerAssignmentManager] = {}
        self.load()
        # print(self.assignments_by_server)
    
    def _init_tasks(self):
        self.autosave_data.start()
    
    @tasks.loop(minutes=1)
    async def autosave_data(self):
        self.save()
    
    def load(self):
        try: 
            with open(SAVE_FILENAME, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # print(f"{data=}")
                self.assignments_by_server = {server_id: ServerAssignmentManager.from_dict(entry) for server_id, entry in data.items()}
                assert(list(self.assignments_by_server.values())[0].groups.__contains__('ALIN'))
        except:
            pass
    
    def save(self):
        try: 
            with open(SAVE_FILENAME, 'w', encoding='utf-8') as f:
                data = {server_id: manager.to_dict() for server_id, manager in self.assignments_by_server.items()}
                json.dump(data, f, indent=4)
        except:
            pass
    
    def get_manager(self, guild_id: str):
        return self.assignments_by_server[str(guild_id)]
    
    @staticmethod
    def has_been_setup():
        async def predicate(ctx: commands.Context):
            return str(ctx.guild.id) in ctx.cog.assignments_by_server
        return commands.check(predicate)
    
    @commands.command(aliases=['trackerchannel', 'setup'])
    async def bind_tracker_announcer_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        if channel==None:
            channel = ctx.channel
        if ctx.guild.id not in self.assignments_by_server:
            self.assignments_by_server[str(ctx.guild.id)] = ServerAssignmentManager(ctx.guild.id, channel.id)
            await ctx.send(f"Successfully setup tracker and set <#{channel.id}> as an announcer channel.")
        else:
            self.assignments_by_server[str(ctx.guild.id)].announcer_channel_id=channel.id
            await ctx.send(f"Successfully set <#{channel.id}> as an announcer channel.")
    
    @commands.command(aliases=['listgroups'])
    @has_been_setup()
    async def list_groups(self, ctx: commands.Context):
        manager = self.get_manager(ctx.guild.id)
        groups_str = "\n".join([str(idx+1)+". "+str(group) for idx, group in enumerate(manager.groups)])
        await ctx.send(f"Groups:\n{groups_str}")
    
    @commands.command(aliases=['creategroup'])
    @has_been_setup()
    async def create_group(self, ctx: commands.Context, group_name: str):
        if ',' in group_name:
            return await ctx.send("Group names must not contain commas.")
        manager = self.get_manager(ctx.guild.id)
        if manager.create_group(group_name):
            return await ctx.send(f"Successfully created group<{group_name.upper()}>")
        await ctx.send(f"Group<{group_name.upper()}> already exists.")
    
    @commands.command(aliases=['deletegroup'])
    @has_been_setup()
    async def delete_group(self, ctx: commands.Context, group_name: str):
        manager = self.get_manager(ctx.guild.id)
        if manager.delete_group(group_name):
            return await ctx.send(f"Successfully removed group<{group_name.upper()}>")
        await ctx.send(f"Group<{group_name.upper()}> does not exist.")
    
    @commands.command(aliases=['subscribe'])
    @has_been_setup()
    async def subscribe_group(self, ctx: commands.Context, *, group_names: str):
        manager = self.get_manager(ctx.guild.id)
        groups = [e for e in group_names.upper().split(' ') if len(e)>0]
        successful = []
        for group in groups:
            if manager.subscribe(str(ctx.author.id), group):
                successful.append(group.upper())
        await ctx.send(f"Successfully subscribed to groups=[{', '.join(successful)}].")
    
    @commands.command(aliases=['listall', 'listallassign'])
    @has_been_setup()
    async def list_all_assignments(self, ctx: commands.Context):
        manager = self.get_manager(ctx.guild.id)
        assignment_str = "\n".join([str(e) for e in manager.get_all_assignments()])
        await ctx.send(f"All Assignments:\n"+assignment_str)
    
    @commands.command(aliases=['listmine', 'listmyassign'])
    @has_been_setup()
    async def list_personal_assignments(self, ctx: commands.Context, modifier: Literal['all', ''] = ''):
        manager = self.get_manager(ctx.guild.id)
        assignment_str = "\n".join([str(e) for e in manager.get_personal_assignments(str(ctx.author.id), modifier=='all')])
        await ctx.send(f"Your Assignments:\n"+assignment_str)
    
    @commands.command(aliases=['completed', 'done'])
    @has_been_setup()
    async def checklist_assignment(self, ctx: commands.Context, assignment_id: str):
        manager = self.get_manager(ctx.guild.id)
        if manager.checklist_assignment(ctx.author.id, assignment_id):
            return await ctx.send(f"Nicely done <@{ctx.author.id}>! :fire: :fire: :fire:")
        await ctx.send(f"No-uh, Can't do that.")
    
    @commands.command(aliases=['incompleted', 'incomplete', 'undone'])
    @has_been_setup()
    async def unchecklist_assignment(self, ctx: commands.Context, assignment_id: str):
        manager = self.get_manager(ctx.guild.id)
        if manager.unchecklist_assignment(ctx.author.id, assignment_id):
            return await ctx.send(f"Bruh, ok tho. -1 aura")
        await ctx.send(f"What are you trying to do?")
    
    @commands.command(aliases=['getassignment', 'getdetail', 'details'])
    @has_been_setup()
    async def get_assignment(self, ctx: commands.Context, assignment_id: str):
        manager = self.get_manager(ctx.guild.id)
        assignment = manager.assignments.get(assignment_id, None)
        if assignment is None:
            return await ctx.send("That assignment does not exists.")
        await ctx.send(embed=assignment.get_embed())
    
    @commands.command(aliases=['createassignment', 'add', 'create'])
    @has_been_setup()
    async def add_assignment(self, ctx: commands.Context, name: str, groups: str = "", deadline: str = "", link: str = ""):
        manager = self.get_manager(ctx.guild.id)
        assignment = manager.create_assignment(name, groups, deadline, link)
        await ctx.send(f"Successfully created Assignment#{assignment.id}:\n" + str(assignment))
    
    @commands.command(aliases=['edit'])
    @has_been_setup()
    async def edit_assignment(self, ctx: commands.Context, assignment_id: str, field: Literal['name', 'deadline', 'groups', 'link'], value: str):
        manager = self.get_manager(ctx.guild.id)
        if manager.edit_assignment(assignment_id, field, value):
            await ctx.send(f"Successfully edited Assignment#{assignment_id}!\n")
            return await ctx.send(embed=manager.assignments[assignment_id].get_embed())
        await ctx.send(f"Failed to delete assignment")
    
    @commands.command(aliases=['deleteassignment', 'delete'])
    @has_been_setup()
    async def delete_assignment(self, ctx: commands.Context, assignment_id: str):
        manager = self.get_manager(ctx.guild.id)
        deleted_assignment = manager.delete_assignment(assignment_id)
        if deleted_assignment is not None:
            return await ctx.send(f"Successfully deleted Assignment#{assignment_id}!")
        await ctx.send(f"Failed to delete assignment.")
    
    @commands.command(aliases=['archiveassignment', 'archive'])
    @has_been_setup()
    async def archive_assignment(self, ctx: commands.Context, assignment_id: str):
        manager = self.get_manager(ctx.guild.id)
        if manager.archive_assignment(assignment_id):
            return await ctx.send(f"Successfully archived Assignment#{assignment_id}!")
        await ctx.send(f"Failed to archive assignment.")
    
    @bind_tracker_announcer_channel.after_invoke
    @create_group.after_invoke
    @delete_group.after_invoke
    @subscribe_group.after_invoke
    @checklist_assignment.after_invoke
    @unchecklist_assignment.after_invoke
    @add_assignment.after_invoke
    @edit_assignment.after_invoke
    @delete_assignment.after_invoke
    @archive_assignment.after_invoke
    async def save_after_action(self, ctx: commands.Context):
        self.save()
    
    @bind_tracker_announcer_channel.error
    @create_group.error
    @delete_group.error
    @subscribe_group.error
    @checklist_assignment.error
    @unchecklist_assignment.error
    @get_assignment.error
    @add_assignment.error
    @edit_assignment.error
    @delete_assignment.error
    @archive_assignment.error
    async def error_handler(self, ctx: commands.Context, error: discord.DiscordException):
        print(error, type(error))
        if isinstance(error, discord.ext.commands.errors.CheckFailure):
            await ctx.send("You have to setup an assignment tracker before doing that!\nrun `~trackerchannel` on a channel you would like to set as a reminder channel.")
        else:
            raise error


def setup(bot):
    bot.add_cog(AssignmentTracker(bot))
