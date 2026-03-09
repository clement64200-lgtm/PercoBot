import sys
import os

# Fix chemin pour Railway
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

import discord
from discord.ext import commands
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
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
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

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
    print(f"✅ Reset hebdomadaire effectué — semaine {semaine_precedente}")


# ─── Événements du bot ─────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} est en ligne !")
    print(f"📁 Répertoire courant : {os.getcwd()}")
    print(f"📁 Contenu : {os.listdir('.')}")
    print(f"📁 Contenu cogs : {os.listdir('cogs') if os.path.exists('cogs') else 'DOSSIER INTROUVABLE'}")

    await bot.load_extension("cogs.perco")
    await bot.load_extension("cogs.config")
    print("✅ Cogs chargés.")

    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"✅ {len(synced)} commandes slash synchronisées.")

    scheduler.add_job(reset_hebdo, "cron", day_of_week="mon", hour=0, minute=0)
    scheduler.start()
    print("✅ Scheduler démarré (reset lundi 00h00).")


# ─── Lancement du bot ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN manquant dans le fichier .env !")
    else:
        bot.run(TOKEN)
