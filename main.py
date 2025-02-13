from telethon import TelegramClient, events
from config import API_ID, API_HASH, BOT_TOKEN
from database import init_db, add_user, add_pokemon, get_collection
from game_logic import get_random_pokemon, should_spawn_pokemon, get_pokemon_stats

bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
current_pokemon = None

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.reply("Welcome to the Pokémon Catcher Game! Keep chatting to spawn Pokémon!")

@bot.on(events.NewMessage(pattern="/mycollection"))
async def my_collection(event):
    user_id = event.sender_id
    collection = get_collection(user_id)

    if not collection:
        await event.reply("❌ You haven't caught any Pokémon yet!")
        return

    # Count duplicate Pokémon
    poke_count = {}
    for poke in collection:
        poke_count[poke] = poke_count.get(poke, 0) + 1

    # Build formatted message
    message = "**📜 Your Pokémon Collection:**\n\n"
    rows = []
    row = []

    for name, count in poke_count.items():
        entry = f"**{name}** x{count}" if count > 1 else f"**{name}**"
        row.append(entry)

        # Format 3 Pokémon per row
        if len(row) == 3:
            rows.append(" | ".join(row))
            row = []

    if row:
        rows.append(" | ".join(row))

    message += "\n".join(rows)
    await event.reply(message)

@bot.on(events.NewMessage(pattern="/stats (.+)"))
async def pokemon_stats(event):
    pokemon_name = event.pattern_match.group(1)
    stats = get_pokemon_stats(pokemon_name)
    
    if stats:
        message = (
            f"📊 **{stats['name']} Stats:**\n"
            f"❤️ HP: {stats['hp']}\n"
            f"⚔️ Attack: {stats['attack']}\n"
            f"🛡️ Defense: {stats['defense']}\n"
            f"🔴 Sp. Attack: {stats['special_attack']}\n"
            f"🔵 Sp. Defense: {stats['special_defense']}\n"
            f"⚡ Speed: {stats['speed']}"
        )
        await bot.send_file(event.chat_id, stats["image"], caption=message)
    else:
        await event.reply("❌ Pokémon not found! Make sure you entered the correct name.")



@bot.on(events.NewMessage)
async def message_handler(event):
    global current_pokemon
    user_id = event.sender_id
    username = event.sender.username
    text = event.raw_text.lower()

    add_user(user_id, username)

    if current_pokemon and text == current_pokemon["name"]:
        add_pokemon(user_id, current_pokemon["name"])
        await event.reply(f"🎉 {username} caught {current_pokemon['name']}! 🎉")
        current_pokemon = None
    elif should_spawn_pokemon():
        current_pokemon = get_random_pokemon()
        await bot.send_file(event.chat_id, current_pokemon["image"], caption="A wild Pokémon appeared! Reply with its name to catch it!")



import random
from telethon import events, Button

battle_data = {}  # Dictionary to store ongoing battles

from telethon import Button
import random

battle_data = {}

import random
from telethon import events, Button

# Dictionary to track active battles
battle_data = {}

@bot.on(events.NewMessage(pattern="/battle"))
async def battle(event):
    if not event.message.is_reply:
        await event.reply("⚠️ Please reply to a user to challenge them to a battle!")
        return

    opponent = await event.get_reply_message()
    challenger_id = event.sender_id
    opponent_id = opponent.sender_id

    if challenger_id == opponent_id:
        await event.reply("⚠️ You can't battle yourself!")
        return

    challenger_pokemon = get_collection(challenger_id)
    opponent_pokemon = get_collection(opponent_id)

    if not challenger_pokemon or not opponent_pokemon:
        await event.reply("⚠️ Both players need at least **1 Pokémon** to battle!")
        return

    # Send challenge request to opponent
    buttons = [
        [Button.inline("✅ Accept", f"accept_{challenger_id}_{opponent_id}"),
         Button.inline("❌ Decline", f"decline_{challenger_id}_{opponent_id}")]
    ]
    await bot.send_message(opponent_id, f"🎮 **You have been challenged to a Pokémon Battle!**\n\n"
                                        f"**Challenger:** {event.sender.first_name}\n"
                                        "Do you accept?", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"accept_(\d+)_(\d+)"))
async def accept_battle(event):
    challenger_id, opponent_id = map(int, event.data.decode().split("_")[1:])

    challenger_pokemon = get_collection(challenger_id)
    opponent_pokemon = get_collection(opponent_id)

    if not challenger_pokemon or not opponent_pokemon:
        await bot.send_message(challenger_id, "⚠️ Battle canceled! One or both players have no Pokémon.")
        await bot.send_message(opponent_id, "⚠️ Battle canceled! One or both players have no Pokémon.")
        return

    # Pick 2 random Pokémon for each player
    challenger_pokemon = random.sample(challenger_pokemon, min(5, len(challenger_pokemon)))
    opponent_pokemon = random.sample(opponent_pokemon, min(5, len(opponent_pokemon)))

    turn = random.choice([challenger_id, opponent_id])

    battle_data[challenger_id] = {"opponent": opponent_id, "pokemon": challenger_pokemon, "score": 0}
    battle_data[opponent_id] = {"opponent": challenger_id, "pokemon": opponent_pokemon, "score": 0}

    challenger_entity = await bot.get_entity(challenger_id)
    opponent_entity = await bot.get_entity(opponent_id)

    await bot.send_message(challenger_id, f"✅ Battle Accepted! You will face {opponent_entity.first_name}")
    await bot.send_message(opponent_id, f"✅ Battle Accepted! You will face {challenger_entity.first_name}")

    await start_round(turn)

@bot.on(events.CallbackQuery(pattern=r"decline_(\d+)_(\d+)"))
async def decline_battle(event):
    challenger_id, _ = map(int, event.data.decode().split("_")[1:])
    await event.answer("❌ Battle Declined", alert=True)
    await bot.send_message(challenger_id, "⚠️ Your opponent declined the battle!")

async def start_round(player_id):
    buttons = get_stat_buttons()
    await bot.send_message(player_id, "🎮 **Choose a stat for this round!**", buttons=buttons)
@bot.on(events.CallbackQuery(pattern=r"pick_(.+)"))
async def handle_pick_stat(event):
    user_id = event.sender_id
    stat_choice = event.data.decode().split("_", 1)[1]  

    if user_id not in battle_data:
        await event.answer("⚠️ You're not in an active battle!", alert=True)
        return

    stat_map = {
        "hp": "hp",
        "attack": "attack",
        "defense": "defense",
        "sp_attack": "special_attack",  
        "sp_defense": "special_defense",
        "speed": "speed"
    }

    if stat_choice not in stat_map:
        await event.answer("⚠️ Invalid choice!", alert=True)
        return

    chosen_stat = stat_map[stat_choice]
    battle = battle_data[user_id]
    opponent_id = battle["opponent"]

    # Edit message to remove buttons
    await event.edit("✅ You have chosen a stat!")

    if "chosen_stat" in battle_data[opponent_id]:  
        await compare_stats(user_id, opponent_id, chosen_stat)
    else:
        battle_data[user_id]["chosen_stat"] = chosen_stat
        await bot.send_message(opponent_id, "🔹 Your opponent has chosen a stat! Choose yours now.", buttons=get_stat_buttons())

async def compare_stats(player1, player2, stat_choice):
    if not battle_data[player1]["pokemon"] or not battle_data[player2]["pokemon"]:
        await declare_winner(player1, player2)
        return

    p1_pokemon = battle_data[player1]["pokemon"].pop(0)
    p2_pokemon = battle_data[player2]["pokemon"].pop(0)

    p1_stats = get_pokemon_stats(p1_pokemon)
    p2_stats = get_pokemon_stats(p2_pokemon)

    stat_value_1 = p1_stats.get(stat_choice, 0)
    stat_value_2 = p2_stats.get(stat_choice, 0)

    winner = None
    if stat_value_1 > stat_value_2:
        winner = player1
    elif stat_value_1 < stat_value_2:
        winner = player2

    result_message = f"⚔️ **{p1_pokemon}** ({stat_value_1}) vs **{p2_pokemon}** ({stat_value_2})\n"

    if winner:
        battle_data[winner]["score"] += 1
        winner_entity = await bot.get_entity(winner)
        result_message += f"🏆 **{winner_entity.first_name} wins this round!**"
    else:
        result_message += "⚖️ **It's a tie!**"

    await bot.send_message(player1, result_message)
    await bot.send_message(player2, result_message)

    # **Fix: Reset `chosen_stat` for both players**
    battle_data[player1].pop("chosen_stat", None)
    battle_data[player2].pop("chosen_stat", None)

    # If both players have Pokémon left, start the next round
    if battle_data[player1]["pokemon"]:
        await start_round(player2 if winner == player1 else player1)
    else:
        await declare_winner(player1, player2)


async def declare_winner(player1, player2):
    score1 = battle_data[player1]["score"]
    score2 = battle_data[player2]["score"]

    player1_entity = await bot.get_entity(player1)
    player2_entity = await bot.get_entity(player2)

    message = "🏆 **Battle Over! Final Scores:**\n"
    message += f"🔹 {player1_entity.first_name}: {score1} Wins\n"
    message += f"🔹 {player2_entity.first_name}: {score2} Wins\n"

    if score1 > score2:
        message += f"\n🥇 **{player1_entity.first_name} is the champion!**"
    elif score2 > score1:
        message += f"\n🥇 **{player2_entity.first_name} is the champion!**"
    else:
        message += "\n⚖️ **It's a tie!**"

    await bot.send_message(player1, message)
    await bot.send_message(player2, message)

    del battle_data[player1]
    del battle_data[player2]


def get_stat_buttons():
    return [
        [Button.inline("❤️ HP", "pick_hp"), Button.inline("⚔️ Attack", "pick_attack")],
        [Button.inline("🛡 Defense", "pick_defense"), Button.inline("🔥 Sp. Attack", "pick_sp_attack")],
        [Button.inline("🌀 Sp. Defense", "pick_sp_defense"), Button.inline("⚡ Speed", "pick_speed")]
    ]




init_db()
print("Bot is running...")
bot.run_until_disconnected()
