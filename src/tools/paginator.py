import discord
from discord.ui import View, Button, Modal, TextInput
from typing import List

class SkipToModal(Modal):
    def __init__(self, paginator_view):
        super().__init__(title="Skip to Page")
        self.paginator_view = paginator_view
        
        self.page_input = TextInput(
            label="Page Number",
            placeholder=f"Enter a page number (1-{len(paginator_view.embeds)})",
            required=True,
            max_length=4
        )
        self.add_item(self.page_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            page_num = int(self.page_input.value) - 1
            if 0 <= page_num < len(self.paginator_view.embeds):
                self.paginator_view.current_page = page_num
                await interaction.response.edit_message(
                    embed=self.paginator_view.embeds[page_num],
                    view=self.paginator_view
                )
            else:
                await interaction.response.send_message(
                    f"Invalid page number. Please enter a number between 1 and {len(self.paginator_view.embeds)}",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number.",
                ephemeral=True
            )

class PaginatorView(View):
    def __init__(self, embeds: List[discord.Embed], author_id: int = None, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0
        self.buttons_visible = True
        self.author_id = author_id
        
        # Update all embeds with page numbers
        self._update_page_footers()
        
        # Add buttons with custom emojis
        self.back_button = Button(
            emoji="<:left:1447310768851652608>",
            style=discord.ButtonStyle.secondary
        )
        self.back_button.callback = self.back_callback
        
        self.forward_button = Button(
            emoji="<:right:1447310737104961636>",
            style=discord.ButtonStyle.secondary
        )
        self.forward_button.callback = self.forward_callback
        
        self.skipto_button = Button(
            emoji="<:skipto:1447310792897593395>",
            style=discord.ButtonStyle.secondary
        )
        self.skipto_button.callback = self.skipto_callback
        
        self.close_button = Button(
            emoji="<:close:1447310831342583908>",
            style=discord.ButtonStyle.secondary
        )
        self.close_button.callback = self.close_callback
        
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.skipto_button)
        self.add_item(self.close_button)
    
    def _update_page_footers(self):
        """Update all embed footers with page numbers"""
        total = len(self.embeds)
        for i, embed in enumerate(self.embeds):
            existing_footer = embed.footer.text if embed.footer and embed.footer.text else ""
            # Remove any existing page indicator
            if " • Page " in existing_footer:
                existing_footer = existing_footer.split(" • Page ")[0]
            elif existing_footer.startswith("Page "):
                existing_footer = ""
            
            page_text = f"Page {i + 1}/{total}"
            if existing_footer:
                embed.set_footer(text=f"{existing_footer} • {page_text}")
            else:
                embed.set_footer(text=page_text)
    
    async def back_callback(self, interaction: discord.Interaction):
        if self.author_id and interaction.user.id != self.author_id:
            return await interaction.response.send_message("can't use this fam", ephemeral=True)
        
        if self.current_page == 0:
            self.current_page = len(self.embeds) - 1
        else:
            self.current_page -= 1
        
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page],
            view=self
        )
    
    async def forward_callback(self, interaction: discord.Interaction):
        if self.author_id and interaction.user.id != self.author_id:
            return await interaction.response.send_message("can't use this fam", ephemeral=True)
        
        if self.current_page == len(self.embeds) - 1:
            self.current_page = 0
        else:
            self.current_page += 1
        
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page],
            view=self
        )
    
    async def skipto_callback(self, interaction: discord.Interaction):
        if self.author_id and interaction.user.id != self.author_id:
            return await interaction.response.send_message("can't use this fam", ephemeral=True)
        
        modal = SkipToModal(self)
        await interaction.response.send_modal(modal)
    
    async def close_callback(self, interaction: discord.Interaction):
        if self.author_id and interaction.user.id != self.author_id:
            return await interaction.response.send_message("can't use this fam", ephemeral=True)
        
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page],
            view=None
        )
        self.stop()
