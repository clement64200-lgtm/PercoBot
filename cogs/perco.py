import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
import database as db

def get_semaine() -> str:
    now = datetime.now()
    return f"{now.year}-{now.strftime('%W')}"

def get_medaille(position: int) -> str:
    medailles = {1: "🥇", 2: "🥈", 3: "🥉"}
    return medailles.get(position, f"#{position}")

async def refresh_ladder(guild: discord.Guild):
    """Met à jour le message ladder en temps réel."""
    channel_ladder_id = int(os.getenv("CHANNEL_LADDER", 0))
    channel = guild.get_channel(channel_ladder_id)
    if not channel:
        return

    semaine = get_semaine()
    rows = db.get_ladder(semaine, limit=10)
    now = datetime.now().strftime("%d/%m/%Y à %Hh%M")

    embed = discord.Embed(
        title=f"⚔️ LADDER PERCO — Semaine {semaine.split('-')[1]}",
        color=discord.Color.gold()
    )

    if not rows:
        embed.description = "*Aucun combat enregistré cette semaine.*"
    else:
        classement = ""
        for i, row in enumerate(rows, 1):
            medaille = get_medaille(i)
            try:
                member = guild.get_member(int(row['joueur_id']))
                nom = member.display_name if member else f"Joueur {row['joueur_id'][:6]}"
            except:
                nom = "Joueur inconnu"
            winrate = int(row['nb_victoires'] / row['nb_combats'] * 100) if row['nb_combats'] > 0 else 0
            classement += f"{medaille} **{nom}** — {row['points']} pts │ {row['nb_victoires']}V/{row['nb_defaites']}D │ {winrate}%\n"
        embed.description = classement

    embed.set_footer(text=f"🔄 Mis à jour : {now} • Reset chaque lundi minuit")

    ladder_msg_id = db.get_config("ladder_message_id")
    if ladder_msg_id and ladder_msg_id.strip():
        try:
            msg = await channel.fetch_message(int(ladder_msg_id))
            await msg.edit(embed=embed)
            return  # Message trouvé et édité, on s'arrête là
        except discord.NotFound:
            pass  # Message supprimé, on en recrée un
        except Exception:
            return  # Autre erreur, on ne crée pas de doublon

    # Créer un nouveau message uniquement si aucun existant
    msg = await channel.send(embed=embed)
    try:
        await msg.pin()
    except:
        pass
    db.set_config("ladder_message_id", str(msg.id))


# ─── Boutons de validation officier ───────────────────────────────────────────

class BoutonsValidation(discord.ui.View):
    def __init__(self, report_id: int):
        super().__init__(timeout=None)
        self.report_id = report_id

    async def check_officier(self, interaction: discord.Interaction) -> bool:
        role_id = int(os.getenv("ROLE_OFFICIER", 0))
        role = interaction.guild.get_role(role_id)
        if role and role in interaction.user.roles:
            return True
        await interaction.response.send_message(
            "❌ Tu dois être **Lieutenant** pour valider les reports.", ephemeral=True
        )
        return False

    @discord.ui.button(label="✅ Valider", style=discord.ButtonStyle.success, custom_id="valider")
    async def valider(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_officier(interaction):
            return

        conn = db.get_connection()
        report = conn.execute("SELECT * FROM reports WHERE id = ?", (self.report_id,)).fetchone()
        conn.close()

        if not report:
            await interaction.response.send_message("❌ Report introuvable.", ephemeral=True)
            return
        if report["statut"] != "en_attente":
            await interaction.response.send_message("⚠️ Ce report a déjà été traité.", ephemeral=True)
            return

        points = db.calculer_points(
            role=report["role"],
            nb_allies=report["nb_allies"],
            nb_enemies=report["nb_enemies"],
            resultat=report["resultat"],
            alliance_focus=bool(report["alliance_focus"])
        )

        conn = db.get_connection()
        conn.execute("""
            UPDATE reports SET statut = 'valide', points = ?, officier_id = ?
            WHERE id = ?
        """, (points, str(interaction.user.id), self.report_id))
        conn.commit()
        conn.close()

        semaine = report["semaine"]
        victoire = report["resultat"] == "victoire"
        allies_ids = report["allies"].split(",")
        for ally_id in allies_ids:
            ally_id = ally_id.strip()
            if ally_id:
                db.ajouter_points(ally_id, semaine, points, victoire)

        embeds = interaction.message.embeds
        embeds[0].color = discord.Color.green()
        embeds[0].set_footer(text=f"✅ Validé par {interaction.user.display_name} | {points} pts distribués")

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(embeds=embeds, view=self)

        await refresh_ladder(interaction.guild)

        allies_mentions = " ".join([f"<@{a.strip()}>" for a in allies_ids if a.strip()])
        resultat_emoji = "🏆" if victoire else "💀"

        annonce = discord.Embed(
            title=f"{resultat_emoji} Combat validé — {report['type'].capitalize()} {report['role'].capitalize()}",
            color=discord.Color.gold() if victoire else discord.Color.red(),
            timestamp=datetime.now()
        )
        annonce.add_field(name="👥 Participants", value=allies_mentions or "Aucun", inline=False)
        annonce.add_field(name="⚔️ Ratio", value=f"{report['nb_allies']}v{report['nb_enemies']}", inline=True)
        annonce.add_field(name="⚡ Alliance Focus", value="Oui" if report["alliance_focus"] else "Non", inline=True)
        annonce.add_field(name="🎯 Points gagnés", value=f"**{points} pts**", inline=True)

        channel_ladder_id = int(os.getenv("CHANNEL_LADDER", 0))
        channel_ladder = interaction.guild.get_channel(channel_ladder_id)
        if channel_ladder:
            await channel_ladder.send(embed=annonce)

        await interaction.response.send_message(
            f"✅ Report validé ! **{points} pts** distribués à {len([a for a in allies_ids if a.strip()])} joueur(s).",
            ephemeral=True
        )

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger, custom_id="refuser")
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_officier(interaction):
            return

        conn = db.get_connection()
        report = conn.execute("SELECT * FROM reports WHERE id = ?", (self.report_id,)).fetchone()
        conn.close()

        if not report or report["statut"] != "en_attente":
            await interaction.response.send_message("⚠️ Ce report a déjà été traité.", ephemeral=True)
            return

        modal = MotifRefus(report_id=self.report_id, view_parent=self, message=interaction.message)
        await interaction.response.send_modal(modal)


class MotifRefus(discord.ui.Modal, title="Motif du refus"):
    motif = discord.ui.TextInput(
        label="Motif",
        placeholder="Ex: Screenshot illisible, mauvais ratio...",
        max_length=200
    )

    def __init__(self, report_id: int, view_parent: BoutonsValidation, message: discord.Message):
        super().__init__()
        self.report_id = report_id
        self.view_parent = view_parent
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        conn = db.get_connection()
        conn.execute("""
            UPDATE reports SET statut = 'refuse', officier_id = ?, motif_refus = ?
            WHERE id = ?
        """, (str(interaction.user.id), self.motif.value, self.report_id))
        conn.commit()
        conn.close()

        embeds = self.message.embeds
        embeds[0].color = discord.Color.red()
        embeds[0].set_footer(text=f"❌ Refusé par {interaction.user.display_name} — {self.motif.value}")

        for child in self.view_parent.children:
            child.disabled = True
        await self.message.edit(embeds=embeds, view=self.view_parent)
        await interaction.response.send_message(f"❌ Report refusé. Motif : *{self.motif.value}*", ephemeral=True)


# ─── Cog principal ─────────────────────────────────────────────────────────────

class PercoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    perco_group = app_commands.Group(name="perco", description="Commandes perco de l'alliance")

    @perco_group.command(name="report", description="Reporter un combat perco ou prisme")
    @app_commands.describe(
        type="Type de combat",
        role="Attaque ou défense",
        resultat="Victoire ou défaite",
        nb_enemies="Nombre d'ennemis",
        allies="Tags Discord de tous les alliés présents (ex: @Joueur1 @Joueur2)",
        alliance_focus="L'ennemi était-il focus alliance ?",
        screenshot="1er screenshot du combat",
        screenshot2="2ème screenshot du combat"
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Perco", value="perco"),
            app_commands.Choice(name="Prisme", value="prisme"),
        ],
        role=[
            app_commands.Choice(name="Défense", value="defense"),
            app_commands.Choice(name="Attaque", value="attaque"),
        ],
        resultat=[
            app_commands.Choice(name="Victoire", value="victoire"),
            app_commands.Choice(name="Défaite", value="defaite"),
        ],
        alliance_focus=[
            app_commands.Choice(name="Oui", value=1),
            app_commands.Choice(name="Non", value=0),
        ]
    )
    async def report(
        self,
        interaction: discord.Interaction,
        type: str,
        role: str,
        resultat: str,
        nb_enemies: int,
        allies: str,
        alliance_focus: int,
        screenshot: discord.Attachment,
        screenshot2: discord.Attachment
    ):
        allies_ids = []
        for word in allies.split():
            word = word.strip("<@!>")
            if word.isdigit():
                allies_ids.append(word)

        nb_allies = len(allies_ids)
        semaine = get_semaine()
        points_preview = db.calculer_points(role, nb_allies, nb_enemies, resultat, bool(alliance_focus))

        conn = db.get_connection()
        cursor = conn.execute("""
            INSERT INTO reports (reporter_id, type, role, alliance_focus, allies, nb_allies, nb_enemies, resultat, screenshot_url, semaine)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            reporter_id, type, role, alliance_focus,
            ",".join(allies_ids), nb_allies, nb_enemies,
            resultat, screenshot.url, semaine
        ))
        report_id = cursor.lastrowid
        conn.commit()
        conn.close()

        type_emoji = "🏛️" if type == "perco" else "💎"
        role_emoji = "🛡️" if role == "defense" else "⚔️"
        resultat_emoji = "🏆" if resultat == "victoire" else "💀"
        allies_mentions = " ".join([f"<@{a}>" for a in allies_ids])

        embed = discord.Embed(
            title=f"📋 Nouveau Report #{report_id} — En attente de validation",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.add_field(name=f"{type_emoji} Type", value=type.capitalize(), inline=True)
        embed.add_field(name=f"{role_emoji} Rôle", value=role.capitalize(), inline=True)
        embed.add_field(name=f"{resultat_emoji} Résultat", value=resultat.capitalize(), inline=True)
        embed.add_field(name="⚡ Alliance Focus", value="Oui" if alliance_focus else "Non", inline=True)
        embed.add_field(name="⚔️ Ratio", value=f"{nb_allies}v{nb_enemies}", inline=True)
        embed.add_field(name="🎯 Points prévus", value=f"**{points_preview} pts**", inline=True)
        embed.add_field(name=f"👥 Alliés ({nb_allies})", value=allies_mentions, inline=False)
        embed.set_footer(text=f"Reporté par {interaction.user.display_name}")

        # Embed screenshot 1
        embed_s1 = discord.Embed(color=discord.Color.orange())
        embed_s1.set_image(url=screenshot.url)

        # Embed screenshot 2
        embed_s2 = discord.Embed(color=discord.Color.orange())
        embed_s2.set_image(url=screenshot2.url)

        channel_val_id = int(os.getenv("CHANNEL_VALIDATION", 0))
        channel_val = interaction.guild.get_channel(channel_val_id)
        view = BoutonsValidation(report_id=report_id)

        if channel_val:
            msg = await channel_val.send(embeds=[embed, embed_s1, embed_s2], view=view)

            conn = db.get_connection()
            conn.execute("UPDATE reports SET message_id = ? WHERE id = ?", (str(msg.id), report_id))
            conn.commit()
            conn.close()

        await interaction.response.send_message(
            f"✅ Report **#{report_id}** soumis ! Un Lieutenant va le valider.", ephemeral=True
        )

    @perco_group.command(name="ladder", description="Affiche le classement de la semaine")
    async def ladder(self, interaction: discord.Interaction):
        await refresh_ladder(interaction.guild)
        await interaction.response.send_message("✅ Ladder mis à jour !", ephemeral=True)

    @perco_group.command(name="stats", description="Affiche les stats d'un joueur")
    @app_commands.describe(joueur="Le joueur dont tu veux voir les stats")
    async def stats(self, interaction: discord.Interaction, joueur: discord.Member = None):
        cible = joueur or interaction.user
        semaine = get_semaine()
        row = db.get_stats_joueur(str(cible.id), semaine)

        embed = discord.Embed(
            title=f"📊 Stats de {cible.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        if not row:
            embed.description = "Aucun combat cette semaine."
        else:
            embed.add_field(name="🎯 Points", value=f"**{row['points']} pts**", inline=True)
            embed.add_field(name="⚔️ Combats", value=str(row["nb_combats"]), inline=True)
            embed.add_field(name="🏆 Victoires", value=str(row["nb_victoires"]), inline=True)
            embed.add_field(name="💀 Défaites", value=str(row["nb_defaites"]), inline=True)
            winrate = int(row["nb_victoires"] / row["nb_combats"] * 100) if row["nb_combats"] > 0 else 0
            embed.add_field(name="📈 Winrate", value=f"{winrate}%", inline=True)

        embed.set_thumbnail(url=cible.display_avatar.url)
        embed.set_footer(text=f"Semaine {semaine}")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PercoCog(bot))
