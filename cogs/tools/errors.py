import discord
from discord.ext import commands

class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def send_error(self, ctx, message: str):
        """Send an error embed"""
        embed = discord.Embed(
            description=f"❌ {ctx.author.mention}: {message}",
            color=0x2b2d31
        )
        await ctx.deny(f"{message}")
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Global error handler for all commands"""
        
        # Ignore if command has its own error handle
        if hasattr(ctx.command, 'on_error'):
            return
        
        # Get the original error if it's wrapped
        error = getattr(error, 'original', error)
        
        # Missing Permissions
        if isinstance(error, commands.MissingPermissions):
            missing = ', '.join(error.missing_permissions).replace('_', ' ').title()
            await self.send_error(ctx, f"You're missing permissions to **{missing}**")
        
        # Bot Missing Permissions
        elif isinstance(error, commands.BotMissingPermissions):
            missing = ', '.join(error.missing_permissions).replace('_', ' ').title()
            await self.send_error(ctx, f"I'm **missing permissions** to {missing}")
        
        # Member Not Found
        elif isinstance(error, commands.MemberNotFound):
            await self.send_error(ctx, "Member **not found**")
        
        # User Not Found
        elif isinstance(error, commands.UserNotFound):
            await self.send_error(ctx, "User **not found**")
        
        # Missing Required Argument
        elif isinstance(error, commands.MissingRequiredArgument):
            await self.send_error(ctx, f"Missing required argument: **{error.param.name}**")
        
        # Bad Argument
        elif isinstance(error, commands.BadArgument):
            await self.send_error(ctx, f"Invalid argument provided")
        
        # Command Not Found (optional - you might want to ignore this)
        elif isinstance(error, commands.CommandNotFound):
            return  # Silently ignore
        
        # Command on Cooldown
        elif isinstance(error, commands.CommandOnCooldown):
            await self.send_error(ctx, f"This command is on cooldown. Try again in **{error.retry_after:.2f}s**")
        
        # Max Concurrency
        elif isinstance(error, commands.MaxConcurrencyReached):
            await self.send_error(ctx, "This command is already being used. Please wait.")
        
        # Not Owner
        elif isinstance(error, commands.NotOwner):
            await self.send_error(ctx, "This command is **owner only**")
        
        # Disabled Command
        elif isinstance(error, commands.DisabledCommand):
            await self.send_error(ctx, "This command is **disabled**")
        
        # NSFW Channel Required
        elif isinstance(error, commands.NSFWChannelRequired):
            await self.send_error(ctx, "This command can only be used in **NSFW channels**")
        
        # Check Failure (custom checks)
        elif isinstance(error, commands.CheckFailure):
            await self.send_error(ctx, "You don't have permission to use this command")
        
        # Unhandled errors
        else:
            await self.send_error(ctx, "An unexpected error occurred")
            # Log the error for debugging
            print(f'Ignoring exception in command {ctx.command}:', error)
            import traceback
            traceback.print_exception(type(error), error, error.__traceback__)

async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
