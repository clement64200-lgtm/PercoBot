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


    @config_group.command(name="reset_ladder", description="Reset manuel du ladder (Admin uniquement)")
    @app_commands.describe(semaine="Semaine à reset (format YYYY-WW) ou vide pour la semaine courante")
    async def reset_ladder(self, interaction: discord.Interaction, semaine: str = None):
        if str(interaction.user.id) != "402234653404168193":
            await interaction.response.send_message("❌ Réservé à l'administrateur du bot.", ephemeral=True)
            return

        from datetime import datetime
        if not semaine:
            now = datetime.now()
            semaine = f"{now.year}-{now.strftime('%W')}"

        # Confirmation avant reset
        view = ConfirmReset(semaine=semaine, officier=interaction.user)
        embed = discord.Embed(
            title="⚠️ Confirmation de reset",
            description=f"Tu es sur le point de **supprimer tous les points** de la semaine .",
            color=discord.Color.yellow()
        )
        embed.set_footer(text="Cette action est irréversible !")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ConfirmReset(discord.ui.View):
    def __init__(self, semaine: str, officier: discord.Member):
        super().__init__(timeout=30)
        self.semaine = semaine
        self.officier = officier

    @discord.ui.button(label="✅ Confirmer le reset", style=discord.ButtonStyle.danger)
    async def confirmer(self, interaction: discord.Interaction, button: discord.ui.Button):
        import os
        from datetime import datetime

        conn = db.get_connection()
        conn.execute("DELETE FROM ladder WHERE semaine = ?", (self.semaine,))
        conn.commit()
        conn.close()

        # Mettre à jour le message ladder pour afficher vide
        ladder_msg_id = db.get_config("ladder_message_id")
        if ladder_msg_id and ladder_msg_id.strip():
            try:
                channel_ladder_id = int(os.getenv("CHANNEL_LADDER", 0))
                channel = interaction.guild.get_channel(channel_ladder_id)
                if channel:
                    old_msg = await channel.fetch_message(int(ladder_msg_id))
                    now = datetime.now().strftime("%d/%m/%Y à %Hh%M")
                    embed = discord.Embed(
                        title=f"⚔️ LADDER PERCO — Semaine {self.semaine.split("-")[1]}",
                        description="*Aucun combat enregistré cette semaine.*",
                        color=discord.Color.gold()
                    )
                    embed.set_footer(text=f"🔄 Mis à jour : {now} • Reset chaque lundi minuit")
                    await old_msg.edit(embed=embed)
            except:
                db.set_config("ladder_message_id", "")

        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title="✅ Ladder resetté !",
            description=f"Tous les points de la semaine  ont été supprimés.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def annuler(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Reset annulé.", embed=None, view=self)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
