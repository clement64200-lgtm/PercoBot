import discord
from discord.ext import commands
from discord import app_commands
import os
import database as db

CLES_VALIDES = {
    "points_victoire": "Points pour une victoire",
    "points_defaite": "Points pour une défaite",
    "bonus_defense": "Multiplicateur bonus défense",
    "bonus_alliance_focus": "Multiplicateur bonus alliance focus",
    "multi_egal": "Multiplicateur combat à égalité",
    "multi_minus1": "Multiplicateur -1 allié vs ennemis",
    "multi_minus2": "Multiplicateur -2 alliés vs ennemis",
    "multi_minus3": "Multiplicateur -3 alliés vs ennemis",
    "multi_seul": "Multiplicateur seul contre tous",
    "screenshot_obligatoire": "Screenshot obligatoire (0=non, 1=oui)",
}

class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def is_officier(self, interaction: discord.Interaction) -> bool:
        role_id = int(os.getenv("ROLE_OFFICIER", 0))
        role = interaction.guild.get_role(role_id)
        return role and role in interaction.user.roles

    config_group = app_commands.Group(name="config", description="Configuration du bot (Officiers uniquement)")

    @config_group.command(name="voir", description="Affiche toute la configuration actuelle")
    async def voir(self, interaction: discord.Interaction):
        if not self.is_officier(interaction):
            await interaction.response.send_message("❌ Réservé aux officiers.", ephemeral=True)
            return

        rows = db.get_all_config()
        embed = discord.Embed(
            title="⚙️ Configuration PercoBot",
            color=discord.Color.blurple()
        )

        for row in rows:
            cle = row["cle"]
            valeur = row["valeur"]
            label = CLES_VALIDES.get(cle, cle)
            embed.add_field(name=f"`{cle}`", value=f"{label}\n→ **{valeur}**", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="modifier", description="Modifie une valeur de configuration")
    @app_commands.describe(
        cle="La clé à modifier",
        valeur="La nouvelle valeur"
    )
    @app_commands.choices(cle=[
        app_commands.Choice(name="Points victoire", value="points_victoire"),
        app_commands.Choice(name="Points défaite", value="points_defaite"),
        app_commands.Choice(name="Bonus défense (multiplicateur)", value="bonus_defense"),
        app_commands.Choice(name="Bonus alliance focus (multiplicateur)", value="bonus_alliance_focus"),
        app_commands.Choice(name="Multi combat égal", value="multi_egal"),
        app_commands.Choice(name="Multi -1 allié", value="multi_minus1"),
        app_commands.Choice(name="Multi -2 alliés", value="multi_minus2"),
        app_commands.Choice(name="Multi -3 alliés", value="multi_minus3"),
        app_commands.Choice(name="Multi seul contre tous", value="multi_seul"),
        app_commands.Choice(name="Screenshot obligatoire (0/1)", value="screenshot_obligatoire"),
    ])
    async def modifier(self, interaction: discord.Interaction, cle: str, valeur: str):
        if not self.is_officier(interaction):
            await interaction.response.send_message("❌ Réservé aux officiers.", ephemeral=True)
            return

        try:
            float(valeur)
        except ValueError:
            await interaction.response.send_message("❌ La valeur doit être un nombre !", ephemeral=True)
            return

        ancienne = db.get_config(cle)
        db.set_config(cle, valeur)

        label = CLES_VALIDES.get(cle, cle)
        embed = discord.Embed(
            title="✅ Configuration mise à jour",
            color=discord.Color.green()
        )
        embed.add_field(name="Paramètre", value=label, inline=False)
        embed.add_field(name="Ancienne valeur", value=str(ancienne), inline=True)
        embed.add_field(name="Nouvelle valeur", value=f"**{valeur}**", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="bareme", description="Affiche un exemple de calcul de points")
    async def bareme(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Barème de points actuel",
            color=discord.Color.blurple()
        )

        # Exemples de calcul
        exemples = [
            ("Victoire 5v5", "defense", 5, 5, True),
            ("Victoire 3v5 (focus)", "defense", 3, 5, True),
            ("Victoire 1v5", "defense", 1, 5, False),
            ("Défaite 5v5", "attaque", 5, 5, False),
            ("Victoire attaque 5v5", "attaque", 5, 5, False),
        ]

        details = ""
        for label, role, nb_allies, nb_enemies, focus in exemples:
            pts_v = db.calculer_points(role, nb_allies, nb_enemies, "victoire", focus)
            pts_d = db.calculer_points(role, nb_allies, nb_enemies, "defaite", focus)
            details += f"**{label}** → 🏆 {pts_v} pts / 💀 {pts_d} pts\n"

        embed.description = details
        embed.set_footer(text="Modifiable avec /config modifier")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
