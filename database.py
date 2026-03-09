import sqlite3
import os

DB_PATH = "percobot.db"

def get_connection():
    """Retourne une connexion à la base de données."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialise toutes les tables de la base de données."""
    conn = get_connection()
    cursor = conn.cursor()

    # Table des combats reportés
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id TEXT NOT NULL,
            type TEXT NOT NULL,           -- 'perco' ou 'prisme'
            role TEXT NOT NULL,           -- 'attaque' ou 'defense'
            alliance_focus INTEGER NOT NULL, -- 0 ou 1
            allies TEXT NOT NULL,         -- IDs séparés par des virgules
            nb_allies INTEGER NOT NULL,
            nb_enemies INTEGER NOT NULL,
            resultat TEXT NOT NULL,       -- 'victoire' ou 'defaite'
            screenshot_url TEXT,          -- URL du screenshot (optionnel)
            statut TEXT DEFAULT 'en_attente', -- 'en_attente', 'valide', 'refuse'
            points INTEGER DEFAULT 0,
            message_id TEXT,              -- ID du message de validation
            officier_id TEXT,             -- ID de l'officier qui a validé/refusé
            motif_refus TEXT,
            semaine TEXT NOT NULL,        -- Format: YYYY-WW
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table des points par joueur
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ladder (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            joueur_id TEXT NOT NULL,
            semaine TEXT NOT NULL,
            points INTEGER DEFAULT 0,
            nb_combats INTEGER DEFAULT 0,
            nb_victoires INTEGER DEFAULT 0,
            nb_defaites INTEGER DEFAULT 0,
            UNIQUE(joueur_id, semaine)
        )
    """)

    # Table de configuration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            cle TEXT PRIMARY KEY,
            valeur TEXT NOT NULL
        )
    """)

    # Valeurs par défaut de la configuration
    defaults = {
        "points_victoire": "10",
        "points_defaite": "3",
        "bonus_defense": "1.5",
        "bonus_alliance_focus": "2.0",
        "multi_egal": "1.0",
        "multi_minus1": "1.5",
        "multi_minus2": "2.0",
        "multi_minus3": "3.0",
        "multi_seul": "5.0",
        "screenshot_obligatoire": "0",
        "reset_jour": "lundi",
    }

    for cle, valeur in defaults.items():
        cursor.execute("""
            INSERT OR IGNORE INTO config (cle, valeur) VALUES (?, ?)
        """, (cle, valeur))

    conn.commit()
    conn.close()
    print("✅ Base de données initialisée.")

def get_config(cle: str):
    """Récupère une valeur de configuration."""
    conn = get_connection()
    row = conn.execute("SELECT valeur FROM config WHERE cle = ?", (cle,)).fetchone()
    conn.close()
    return row["valeur"] if row else None

def set_config(cle: str, valeur: str):
    """Modifie une valeur de configuration."""
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO config (cle, valeur) VALUES (?, ?)", (cle, valeur))
    conn.commit()
    conn.close()

def calculer_points(role: str, nb_allies: int, nb_enemies: int, resultat: str, alliance_focus: bool) -> int:
    """Calcule les points d'un combat selon la configuration."""
    # Points de base
    base = float(get_config("points_victoire") if resultat == "victoire" else get_config("points_defaite"))

    # Multiplicateur infériorité numérique
    diff = nb_enemies - nb_allies
    if diff <= 0:
        multi_inf = float(get_config("multi_egal"))
    elif diff == 1:
        multi_inf = float(get_config("multi_minus1"))
    elif diff == 2:
        multi_inf = float(get_config("multi_minus2"))
    elif diff == 3:
        multi_inf = float(get_config("multi_minus3"))
    else:
        multi_inf = float(get_config("multi_seul"))

    # Bonus défense
    bonus_def = float(get_config("bonus_defense")) if role == "defense" else 1.0

    # Bonus alliance focus
    bonus_focus = float(get_config("bonus_alliance_focus")) if alliance_focus else 1.0

    total = base * multi_inf * bonus_def * bonus_focus
    return int(round(total))

def ajouter_points(joueur_id: str, semaine: str, points: int, victoire: bool):
    """Ajoute des points à un joueur pour une semaine donnée."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO ladder (joueur_id, semaine, points, nb_combats, nb_victoires, nb_defaites)
        VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(joueur_id, semaine) DO UPDATE SET
            points = points + excluded.points,
            nb_combats = nb_combats + 1,
            nb_victoires = nb_victoires + excluded.nb_victoires,
            nb_defaites = nb_defaites + excluded.nb_defaites
    """, (joueur_id, semaine, points, 1 if victoire else 0, 0 if victoire else 1))
    conn.commit()
    conn.close()

def get_ladder(semaine: str, limit: int = 10):
    """Récupère le classement d'une semaine."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT joueur_id, points, nb_combats, nb_victoires, nb_defaites
        FROM ladder
        WHERE semaine = ?
        ORDER BY points DESC
        LIMIT ?
    """, (semaine, limit)).fetchall()
    conn.close()
    return rows

def get_stats_joueur(joueur_id: str, semaine: str):
    """Récupère les stats d'un joueur pour une semaine."""
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM ladder WHERE joueur_id = ? AND semaine = ?
    """, (joueur_id, semaine)).fetchone()
    conn.close()
    return row

def get_all_config():
    """Récupère toute la configuration."""
    conn = get_connection()
    rows = conn.execute("SELECT cle, valeur FROM config ORDER BY cle").fetchall()
    conn.close()
    return rows
