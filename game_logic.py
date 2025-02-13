import requests
import random
from config import MESSAGE_THRESHOLD

message_count = 0
current_pokemon = None

def get_random_pokemon():
    poke_id = random.randint(1, 151)  # Limit to Gen 1
    response = requests.get(f"https://pokeapi.co/api/v2/pokemon/{poke_id}")
    data = response.json()
    return {
        "name": data["name"],
        "image": data["sprites"]["other"]["official-artwork"]["front_default"]
    }

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

def should_spawn_pokemon():
    global message_count
    message_count += 1
    if message_count >= MESSAGE_THRESHOLD:
        message_count = 0
        return True
    return False
