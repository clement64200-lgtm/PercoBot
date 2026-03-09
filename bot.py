import discord
from discord.ext import commands
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import os
import database as db

# Chargement des variables d'environnement
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))

# Initialisation de la base de données
db.init_db()

# Configuration des intents Discord
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Création du bot
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()


# ─── Reset hebdomadaire ────────────────────────────────────────────────────────

async def reset_hebdo():
    """Effectue le reset hebdomadaire et annonce les résultats."""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    # Récupérer la semaine qui vient de se terminer
    now = datetime.now()
    semaine_precedente = f"{now.year}-{int(now.strftime('%W')) - 1:02d}"
    rows = db.get_ladder(semaine_precedente, limit=3)

    channel_ladder_id = int(os.getenv("CHANNEL_LADDER", 0))
    channel = guild.get_channel(channel_ladder_id)

    if not channel or not rows:
        return

    embed = discord.Embed(
        title="🏆 Résultats de la semaine !",
        description="Voici le podium des défenseurs de l'alliance cette semaine :",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )

    medailles = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(rows):
        embed.add_field(
            name=f"{medailles[i]} {i+1}ère place" if i == 0 else f"{medailles[i]} {i+1}ème place",
            value=f"<@{row['joueur_id']}> — **{row['points']} pts** ({row['nb_victoires']}V/{row['nb_defaites']}D)",
            inline=False
        )

    embed.set_footer(text="Nouveau ladder démarré ! Bonne chance à tous ⚔️")
    await channel.send("@everyone", embed=embed)

    # Attribution du rôle Défenseur de la semaine au 1er
    if rows:
        role_def_id = int(os.getenv("ROLE_DEFENSEUR", 0))
        role_def = guild.get_role(role_def_id)

        if role_def:
            # Retirer le rôle à l'ancien
            for member in guild.members:
                if role_def in member.roles:
                    await member.remove_roles(role_def)

            # Attribuer au nouveau
            winner = guild.get_member(int(rows[0]["joueur_id"]))
            if winner:
                await winner.add_roles(role_def)

    print(f"✅ Reset hebdomadaire effectué — semaine {semaine_precedente}")


# ─── Événements du bot ─────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} est en ligne !")

    # Chargement des cogs
    await bot.load_extension("cogs.perco")
    await bot.load_extension("cogs.config")
    print("✅ Cogs chargés.")

    # Synchronisation des commandes slash
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"✅ {len(synced)} commandes slash synchronisées.")

    # Planification du reset chaque lundi à 00h00
    scheduler.add_job(reset_hebdo, "cron", day_of_week="mon", hour=0, minute=0)
    scheduler.start()
    print("✅ Scheduler démarré (reset lundi 00h00).")


# ─── Lancement du bot ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN manquant dans le fichier .env !")
    else:
        bot.run(TOKEN)
