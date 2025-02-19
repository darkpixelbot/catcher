import sqlite3
import random
import requests

# Database path
DB_PATH = "pokemon_game.db"

# Reward constants
REWARD_FOR_WIN = 50  # Points for a clean win (e.g., 5-0)
REWARD_FOR_CLOSE_WIN = 30  # Points for a close win (e.g., 3-2)
REWARD_FOR_CLOSE_LOSS = 20  # Points for a close loss (e.g., 2-3)

def get_db_connection():
    """Returns a database connection and cursor."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    return conn, cursor

def init_db():
    """Initialize the database tables if they don't exist."""
    conn, cursor = get_db_connection()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT,
            doj TEXT DEFAULT (DATE('now')),
            battle_wins INTEGER DEFAULT 0,
            pokecoins INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS catches (
            user_id INTEGER, 
            pokemon TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
    """)
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    """Retrieve user stats: username, DOJ, battle wins, and Pokémon count."""
    conn, cursor = get_db_connection()
    cursor.execute("SELECT username, doj, battle_wins FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) FROM catches WHERE user_id = ?", (user_id,))
    pokemon_count = cursor.fetchone()[0]

    conn.close()
    
    if user_data:
        username, doj, battle_wins = user_data
        return username, doj, battle_wins, pokemon_count
    return None

def add_user(user_id, username):
    """Adds a user if they don't already exist."""
    conn, cursor = get_db_connection()
    try:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, pokecoins) VALUES (?, ?, 0)", (user_id, username))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
    finally:
        conn.close()

def add_pokemon(user_id, pokemon):
    """Adds a caught Pokémon to the user's collection."""
    conn, cursor = get_db_connection()
    try:
        cursor.execute("INSERT INTO catches (user_id, pokemon) VALUES (?, ?)", (user_id, pokemon))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
    finally:
        conn.close()

def get_collection(user_id):
    """Retrieves the list of Pokémon a user has caught."""
    conn, cursor = get_db_connection()
    cursor.execute("SELECT pokemon FROM catches WHERE user_id = ?", (user_id,))
    pokes = [poke[0] for poke in cursor.fetchall()]
    conn.close()
    return pokes

def get_pokecoins(user_id):
    """Retrieves the amount of PokéCoins a user has."""
    conn, cursor = get_db_connection()
    cursor.execute("SELECT pokecoins FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def update_pokecoins(user_id, amount):
    """Updates the user's PokéCoins balance by adding or subtracting the given amount."""
    conn, cursor = get_db_connection()
    try:
        cursor.execute("UPDATE users SET pokecoins = pokecoins + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
    finally:
        conn.close()

def calculate_rewards(winner_score, loser_score):
    """
    Calculates the rewards for the winner and loser based on the battle score.
    Returns a tuple of (winner_reward, loser_reward).
    """
    if winner_score == 5 and loser_score == 0:
        # Clean win (5-0)
        return REWARD_FOR_WIN, 0
    else:
        # Close battle (e.g., 3-2)
        return REWARD_FOR_CLOSE_WIN, REWARD_FOR_CLOSE_LOSS

def distribute_rewards(winner_id, loser_id, winner_score, loser_score):
    """Distributes rewards and updates battle wins for the winner."""
    
    winner_reward, loser_reward = calculate_rewards(winner_score, loser_score)

    # Update battle wins for the winner
    update_battle_wins(winner_id)

    # Update PokéCoins
    update_pokecoins(winner_id, winner_reward)
    update_pokecoins(loser_id, loser_reward)

    return winner_reward, loser_reward


def update_battle_wins(user_id):
    """Increments the battle wins count for a user."""
    conn, cursor = get_db_connection()
    cursor.execute("UPDATE users SET battle_wins = battle_wins + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()



def evolve_pokemon(user_id, current_pokemon, evolved_pokemon):
    """Replaces a Pokémon in the user's collection with its evolved form."""
    conn, cursor = get_db_connection()

    try:
        cursor.execute("SELECT rowid FROM catches WHERE user_id = ? AND pokemon = ? LIMIT 1", (user_id, current_pokemon))
        row = cursor.fetchone()

        if row:
            cursor.execute("DELETE FROM catches WHERE rowid = ?", (row[0],))
            cursor.execute("INSERT INTO catches (user_id, pokemon) VALUES (?, ?)", (user_id, evolved_pokemon))
            conn.commit()
            print(f"🟢 {current_pokemon} evolved into {evolved_pokemon} for user {user_id}")  # Debug message
    except Exception as e:
        print(f"🔴 Database Error: {e}")  # Debug error
    finally:
        conn.close()
        print("🟢 Database connection closed.")  # Debug: Ensure DB closes


def setup_shop():
    """Creates the shop and purchases tables if they don't exist."""
    conn, cursor = get_db_connection()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS shop (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pokemon TEXT,
            price INTEGER,
            date TEXT DEFAULT (DATE('now'))
        );

        CREATE TABLE IF NOT EXISTS purchases (
            user_id INTEGER,
            pokemon TEXT,
            date TEXT DEFAULT (DATE('now')),
            PRIMARY KEY (user_id, pokemon, date)
        );
    """)
    conn.commit()
    conn.close()





def refresh_shop():
    """Generates a new set of Pokémon for the daily shop."""
    conn, cursor = get_db_connection()

    # Check if the shop already has Pokémon for today
    cursor.execute("SELECT 1 FROM shop WHERE date = DATE('now')")
    if cursor.fetchone():
        conn.close()
        return  # Shop is already set for today

    # Clear old shop entries
    cursor.execute("DELETE FROM shop WHERE date != DATE('now')")

    # Get 5 random Pokémon (limit to 151 for now)
    random_pokemon = random.sample(range(1, 151), 5)

    # Insert new Pokémon with random prices (50-200 PokéCoins)
    for poke_id in random_pokemon:
        response = requests.get(f"https://pokeapi.co/api/v2/pokemon/{poke_id}")
        if response.status_code == 200:
            pokemon_name = response.json()["name"]
            price = random.randint(50, 200)
            cursor.execute("INSERT INTO shop (pokemon, price) VALUES (?, ?)", (pokemon_name, price))

    conn.commit()
    conn.close()


def buy_pokemon(user_id, pokemon_name):
    """Handles purchasing Pokémon if the user has enough coins and hasn't bought it today."""
    conn, cursor = get_db_connection()

    # Check if Pokémon is in the shop today
    cursor.execute("SELECT price FROM shop WHERE pokemon = ? AND date = DATE('now')", (pokemon_name,))
    shop_entry = cursor.fetchone()

    if not shop_entry:
        conn.close()
        return "❌ This Pokémon is not available in today's shop!"

    price = shop_entry[0]

    # Check user's PokéCoins balance
    cursor.execute("SELECT pokecoins FROM users WHERE user_id = ?", (user_id,))
    user_coins = cursor.fetchone()[0]

    if user_coins < price:
        conn.close()
        return "❌ You don't have enough PokéCoins to buy this Pokémon!"

    # Check if user already purchased this Pokémon today
    cursor.execute("SELECT 1 FROM purchases WHERE user_id = ? AND pokemon = ? AND date = DATE('now')", (user_id, pokemon_name))
    if cursor.fetchone():
        conn.close()
        return "❌ You have already purchased this Pokémon today!"

    # Deduct PokéCoins and add Pokémon to user's collection
    cursor.execute("UPDATE users SET pokecoins = pokecoins - ? WHERE user_id = ?", (price, user_id))
    cursor.execute("INSERT INTO purchases (user_id, pokemon) VALUES (?, ?)", (user_id, pokemon_name))
    cursor.execute("INSERT INTO catches (user_id, pokemon) VALUES (?, ?)", (user_id, pokemon_name))

    conn.commit()
    conn.close()
    return f"✅ You successfully bought {pokemon_name.capitalize()} for {price} PokéCoins!"

def add_resource(user_id, resource, amount):
    """Adds PokéCoins to a specific user."""
    conn, cursor = get_db_connection()

    if resource == "pokecoins":
        cursor.execute("UPDATE users SET pokecoins = pokecoins + ? WHERE user_id = ?", (amount, user_id))
    else:
        conn.close()
        return f"❌ Invalid resource: {resource}"

    conn.commit()
    conn.close()
    return f"✅ Successfully added {amount} {resource.capitalize()} to user {user_id}!"


def add_pokemon_to_user(user_id, pokemon_name):
    """Adds a Pokémon to the user's collection and ensures the database is updated properly."""
    conn, cursor = get_db_connection()
    try:
        print(f"🟢 Attempting to add {pokemon_name.capitalize()} to User {user_id}")  # Debug log
        cursor.execute("INSERT INTO catches (user_id, pokemon) VALUES (?, ?)", (user_id, pokemon_name))
        conn.commit()
        print(f"✅ {pokemon_name.capitalize()} successfully added to User {user_id}")  # Debug log
        return f"✅ Successfully added {pokemon_name.capitalize()} to user {user_id}!"
    except sqlite3.Error as e:
        print(f"🔴 Database Error: {e}")  # Debug log
        return f"❌ Database Error: {e}"
    finally:
        conn.close()

