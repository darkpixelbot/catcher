import sqlite3

def init_db():
    conn = sqlite3.connect("pokemon_game.db")
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS catches (
            user_id INTEGER, pokemon TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )"""
    )
    conn.commit()
    conn.close()

def add_user(user_id, username):
    conn = sqlite3.connect("pokemon_game.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def add_pokemon(user_id, pokemon):
    conn = sqlite3.connect("pokemon_game.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO catches VALUES (?, ?)", (user_id, pokemon))
    conn.commit()
    conn.close()

def get_collection(user_id):
    conn = sqlite3.connect("pokemon_game.db")
    cursor = conn.cursor()
    cursor.execute("SELECT pokemon FROM catches WHERE user_id = ?", (user_id,))
    pokes = cursor.fetchall()
    conn.close()
    return [poke[0] for poke in pokes]
