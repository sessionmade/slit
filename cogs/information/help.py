import discord
from discord.ext import commands
from src.config import Config
from src.tools.paginator import PaginatorView


class HelpSelect(discord.ui.Select):
    """Dropdown menu for help command"""
    
    def __init__(self, bot, cogs_dict, author_id: int):
        options = [
            discord.SelectOption(
                label="Home",
                description="Go back to the main page",
                value="home"
            )
        ]
        
        # Add cog options
        for cog_name, cog in cogs_dict.items():
            options.append(
                discord.SelectOption(
                    label=cog_name,
                    description=cog.description[:50] if cog.description else "No description",
                    value=f"cog_{cog_name}"
                )
            )
        
        super().__init__(
            placeholder="Select a category...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.bot = bot
        self.cogs_dict = cogs_dict
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("can't use this fam", ephemeral=True)
        """Handle select menu interaction"""
        value = self.values[0]
        
        if value == "home":
            embed = await self.create_home_embed()
        else:
            cog_name = value.replace("cog_", "")
            cog = self.cogs_dict.get(cog_name)
            if cog:
                embed = await self.create_cog_embed(cog, cog_name)
            else:
                return await interaction.response.send_message("Cog not found!", ephemeral=True)
        
        await interaction.response.edit_message(embed=embed, view=self.view)
    
    async def create_home_embed(self):
        """Create the home page embed"""
        embed = discord.Embed(
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=self.bot.user.name)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Commands with an * have subcommands")
        
        # Add support links
        embed.add_field(
            name="",
            value="[**Support Server**](https://discord.gg/uQ6rQYquQG) - [**View on Web**](https://flare.bot)",
            inline=False
        )
        
        return embed
    
    async def create_cog_embed(self, cog, cog_name):
        """Create a cog category embed"""
        embed = discord.Embed(
            description=cog.description or "No description available",
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=self.bot.user.name)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        # Get all commands in this cog
        cog_commands = [cmd for cmd in cog.get_commands() if not cmd.hidden]
        
        if cog_commands:
            command_names = []
            for cmd in cog_commands:
                # Add * if command is a group
                if isinstance(cmd, commands.Group):
                    command_names.append(f"{cmd.name}*")
                else:
                    command_names.append(cmd.name)
            
            commands_str = ", ".join(command_names)
            embed.add_field(
                name="",
                value=f"```yaml\n{commands_str}```",
                inline=False
            )
            
            embed.set_footer(text=f"{len(cog_commands)} Commands")
        else:
            embed.set_footer(text="0 Commands")
        
        return embed


class HelpView(discord.ui.View):
    """View for help command with select menu"""
    
    def __init__(self, bot, cogs_dict, author_id: int, timeout=180):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.add_item(HelpSelect(bot, cogs_dict, author_id))


class HelpCommand(commands.HelpCommand):
    """Custom help command with embed format"""
    
    def __init__(self):
        super().__init__(
            command_attrs={
                'help': 'Shows help about the bot, a command, or a category',
                'aliases': ['h']
            }
        )
    
    async def send_bot_help(self, mapping):
        """Send the default help page showing all cogs"""
        ctx = self.context
        bot = ctx.bot
        
        embed = discord.Embed(
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=bot.user.name)
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.set_footer(text="Commands with an * have subcommands")
        
        # Add support links
        embed.add_field(
            name="",
            value="[**Support Server**](https://discord.gg/uQ6rQYquQG) - [**View on Web**](https://flare.bot)",
            inline=False
        )
        
        # Create cogs dictionary for select menu (filter out unwanted cogs)
        cogs_dict = {}
        for cog_name, cog in bot.cogs.items():
            if cog_name.lower() in ['jishaku', 'help', 'test', 'owner']:
                continue
            
            cog_commands = await self.filter_commands(cog.get_commands(), sort=True)
            if cog_commands:
                cogs_dict[cog_name] = cog
        
        view = HelpView(bot, cogs_dict, ctx.author.id)
        await ctx.send(embed=embed, view=view)
    
    async def send_cog_help(self, cog):
        """Send help for a specific cog/category"""
        ctx = self.context
        bot = ctx.bot
        
        embed = discord.Embed(
            description=cog.description or "No description available",
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=bot.user.name)
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        
        # Get all commands in this cog
        cog_commands = await self.filter_commands(cog.get_commands(), sort=True)
        
        if cog_commands:
            command_names = []
            for cmd in cog_commands:
                # Add * if command is a group
                if isinstance(cmd, commands.Group):
                    command_names.append(f"{cmd.name}*")
                else:
                    command_names.append(cmd.name)
            
            commands_str = ", ".join(command_names)
            embed.add_field(
                name="",
                value=f"```yaml\n{commands_str}```",
                inline=False
            )
            
            embed.set_footer(text=f"{len(cog_commands)} Commands")
        else:
            embed.set_footer(text="0 Commands")
        
        await ctx.send(embed=embed)
    
    async def send_group_help(self, group):
        """Send help for a group command"""
        ctx = self.context
        bot = ctx.bot
        # Use the prefix that was actually used
        prefix = ctx.prefix
        
        # Get all subcommands
        subcommands = await self.filter_commands(group.commands, sort=True)
        
        # Create main group command embed
        main_embed = discord.Embed(
            title=f"Group command: {group.qualified_name}",
            description=group.help or "No description available",
            color=Config.COLORS.DEFAULT
        )
        main_embed.set_author(name=bot.user.name)
        main_embed.set_thumbnail(url=bot.user.display_avatar.url)
        
        # Show syntax
        syntax = f"Syntax: {prefix}{group.qualified_name} {group.signature}"
        
        # Check if group has a custom example in extras
        if hasattr(group, 'extras') and 'example' in group.extras:
            example = f"Example: {prefix}{group.extras['example']}"
        else:
            example = f"Example: {prefix}{group.qualified_name}"
        
        main_embed.add_field(
            name="",
            value=f"```js\n{syntax}\n{example}```",
            inline=False
        )
        
        # Show aliases if any
        if group.aliases:
            aliases_str = ", ".join(group.aliases)
            main_embed.add_field(
                name="",
                value=f"Aliases: {aliases_str}",
                inline=False
            )
        
        # Create embeds for subcommands
        embeds = [main_embed]
        
        for cmd in subcommands:
            # Determine title based on if it's a subcommand or not
            if cmd.parent:
                title = f"Sub command: {cmd.qualified_name}"
            else:
                title = f"Command: {cmd.name}"
            
            sub_embed = discord.Embed(
                title=title,
                description=cmd.help or "No description available",
                color=Config.COLORS.DEFAULT
            )
            sub_embed.set_author(name=bot.user.name)
            sub_embed.set_thumbnail(url=bot.user.display_avatar.url)
            
            # Show syntax
            syntax = f"Syntax: {prefix}{cmd.qualified_name} {cmd.signature}"
            
            # Check if command has a custom example in extras
            if hasattr(cmd, 'extras') and 'example' in cmd.extras:
                example = f"Example: {prefix}{cmd.extras['example']}"
            else:
                example = f"Example: {prefix}{cmd.qualified_name}"
            
            sub_embed.add_field(
                name="",
                value=f"```js\n{syntax}\n{example}```",
                inline=False
            )
            
            # Show aliases if any
            if cmd.aliases:
                aliases_str = ", ".join(cmd.aliases)
                sub_embed.add_field(
                    name="",
                    value=f"Aliases: {aliases_str}",
                    inline=False
                )
            
            embeds.append(sub_embed)
        
        # Use paginator if there are multiple embeds
        if len(embeds) > 1:
            view = PaginatorView(embeds, ctx.author.id)
            await ctx.send(embed=embeds[0], view=view)
        else:
            await ctx.send(embed=main_embed)
    
    async def send_command_help(self, command):
        """Send help for a specific command"""
        ctx = self.context
        bot = ctx.bot
        # Use the prefix that was actually used
        prefix = ctx.prefix
        
        # Determine title based on if it's a subcommand or not
        if command.parent:
            title = f"Sub command: {command.qualified_name}"
        else:
            title = f"Command: {command.name}"
        
        embed = discord.Embed(
            title=title,
            description=command.help or "No description available",
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=bot.user.name)
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        
        # Show syntax
        syntax = f"Syntax: {prefix}{command.qualified_name} {command.signature}"
        
        # Check if command has a custom example in extras
        if hasattr(command, 'extras') and 'example' in command.extras:
            example = f"Example: {prefix}{command.extras['example']}"
        else:
            example = f"Example: {prefix}{command.qualified_name}"
        
        embed.add_field(
            name="",
            value=f"```js\n{syntax}\n{example}```",
            inline=False
        )
        
        # Show aliases if any
        if command.aliases:
            aliases_str = ", ".join(command.aliases)
            embed.add_field(
                name="",
                value=f"Aliases: {aliases_str}",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    async def send_error_message(self, error):
        """Send error message when command/cog not found"""
        ctx = self.context
        embed = discord.Embed(
            description=f"{Config.EMOJIS.ERROR} {error}",
            color=Config.COLORS.ERROR
        )
        await ctx.send(embed=embed)


class Help(commands.Cog):
    """Help command cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        bot.help_command = HelpCommand()
        bot.help_command.cog = self
    
    def cog_unload(self):
        self.bot.help_command = self._original_help_command

async def setup(bot):
    await bot.add_cog(Help(bot))
