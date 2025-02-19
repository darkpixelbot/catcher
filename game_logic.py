import requests
import random
from config import DEFAULT_THRESHOLD
from database import get_drop_time 
import time 

message_counts = {}  # Track message counts per chat
thresholds = {}  # Store drop time per group (defaults to DEFAULT_THRESHOLD)

current_pokemon = {}  # Track spawned Pokémon per chat

def get_random_pokemon():
    poke_id = random.randint(1, 151)  # Limit to Gen 1
    url = f"https://pokeapi.co/api/v2/pokemon/{poke_id}"

    for attempt in range(3):  # Retry up to 3 times
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()  # Raise error for bad responses (e.g., 404, 500)

            data = response.json()
            return {
                "name": data["name"],
                "image": data["sprites"]["other"]["official-artwork"]["front_default"]
            }

        except requests.exceptions.RequestException as e:
            print(f"⚠️ Attempt {attempt + 1}: API Request Failed - {e}")
            time.sleep(2)  # Wait before retrying

    print("❌ API request failed after 3 attempts.")
    return None  # Return None if all retries fail


def get_pokemon_stats(pokemon_name):
    response = requests.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon_name.lower()}")
    if response.status_code != 200:
        return None  # Pokémon not found

    data = response.json()
    stats = {stat["stat"]["name"]: stat["base_stat"] for stat in data["stats"]}

    return {
        "name": data["name"].capitalize(),
        "image": data["sprites"]["other"]["official-artwork"]["front_default"],
        "hp": stats["hp"],
        "attack": stats["attack"],
        "defense": stats["defense"],
        "special_attack": stats["special-attack"],
        "special_defense": stats["special-defense"],
        "speed": stats["speed"]
    }

def should_spawn_pokemon(chat_id):
    """Check if a Pokémon should spawn in this specific chat."""
    if chat_id not in message_counts:
        message_counts[chat_id] = 0  # Initialize count for new chat

    if chat_id not in thresholds:
        thresholds[chat_id] = DEFAULT_THRESHOLD  # Use default threshold

    message_counts[chat_id] += 1

    if message_counts[chat_id] >= thresholds[chat_id]:  # Use group-specific threshold
        message_counts[chat_id] = 0  # Reset counter
        return True
    
    return False

def get_next_evolution(pokemon_name):
    """Fetches the correct next evolution for a Pokémon from PokeAPI.
    
    - If multiple evolutions exist (branch evolution like Eevee), pick randomly.
    - If a linear evolution (like Pichu → Pikachu → Raichu), return the correct next form.
    """
    try:
        # Fetch species data
        species_url = f"https://pokeapi.co/api/v2/pokemon-species/{pokemon_name.lower()}/"
        species_response = requests.get(species_url)

        if species_response.status_code != 200:
            return None  # Species not found

        species_data = species_response.json()
        evolution_chain_url = species_data["evolution_chain"]["url"]

        # Fetch evolution chain
        chain_response = requests.get(evolution_chain_url)
        if chain_response.status_code != 200:
            return None  # Evolution chain not found

        evolution_data = chain_response.json()
        chain = evolution_data["chain"]

        # Traverse the evolution chain
        while chain:
            if chain["species"]["name"] == pokemon_name.lower():
                evolutions = chain["evolves_to"]

                if not evolutions:
                    return None  # Already at final evolution

                if len(evolutions) == 1:
                    return evolutions[0]["species"]["name"]  # Normal evolution

                # Branch Evolution: Pick a random evolution
                return random.choice([evo["species"]["name"] for evo in evolutions])

            if not chain["evolves_to"]:
                return None  # No evolution found
            chain = chain["evolves_to"][0]

        return None  # No evolution found

    except Exception as e:
        print(f"Error fetching evolution data: {e}")
        return None
    


def should_spawn_pokemon(chat_id):
    """Check if a Pokémon should spawn in this specific chat."""
    if chat_id not in message_counts:
        message_counts[chat_id] = 0  # Initialize count for new chat

    drop_time = get_drop_time(chat_id)  # Get threshold from database
    message_counts[chat_id] += 1

    if message_counts[chat_id] >= drop_time:  # Use stored threshold
        message_counts[chat_id] = 0  # Reset counter
        return True
    
    return False
