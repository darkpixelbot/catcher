from telethon import TelegramClient, events,Button 
from config import API_ID, API_HASH, BOT_TOKEN, BOT_OWNER_ID
from database import init_db, add_user, add_pokemon, get_collection,distribute_rewards,get_pokecoins,set_drop_time
from database import setup_shop,add_resource,add_pokemon_to_user,evolve_pokemon,get_db_connection,refresh_shop,buy_pokemon
from game_logic import get_random_pokemon, should_spawn_pokemon, get_pokemon_stats,get_next_evolution,thresholds
import random
import asyncio
import os
from flask import Flask
import threading
from telethon.tl.functions.users import GetFullUserRequest

bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

current_pokemon = None

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    user_id = event.sender_id
    username = event.sender.username

    # Try to add the user (INSERT OR IGNORE prevents duplicates)
    add_user(user_id, username)

    # Check if the user was added (if they already existed, fetch their data)
    collection = get_collection(user_id)  # Checking if user has Pokémon

    if collection:  
        await event.reply("✅ You have already started the Pokémon Catcher Game!")
    else:
        await event.reply("🎉 Welcome to the Pokémon Catcher Game! Keep chatting to spawn Pokémon!")

# Dictionary to track user pages and message IDs
user_pages = {}
user_messages = {}

@bot.on(events.NewMessage(pattern="/mycollection"))
async def my_collection(event):
    user_id = event.sender_id
    collection = get_collection(user_id)

    if not collection:
        await event.reply("❌ You haven't caught any Pokémon yet!")
        return

    # Count duplicate Pokémon and store them in a list
    poke_count = {}
    for poke in collection:
        poke_count[poke] = poke_count.get(poke, 0) + 1

    # Prepare the Pokémon list with counts and sort alphabetically
    pokemon_list = sorted([f"**{name}** x{count}" if count > 1 else f"**{name}**" for name, count in poke_count.items()])

    # Initialize page and message
    user_pages[user_id] = 0  # Start from page 0
    
    # Send the collection page with the formatted Pokémon list
    message = await send_collection_page(event, user_id, pokemon_list)
    user_messages[user_id] = message.id  # Store the bot's message ID

async def send_collection_page(event, user_id, pokemon_list):
    page = user_pages.get(user_id, 0)
    per_page = 10  # Consistent value for pagination
    total_pages = (len(pokemon_list) // per_page) + (1 if len(pokemon_list) % per_page > 0 else 0)  # Corrected the formula for total pages
    
    start = page * per_page
    end = start + per_page
    text = "**📜 Your Pokémon Collection:**\n\n" + "\n".join(pokemon_list[start:end])
    
    buttons = []
    if page > 0:
        buttons.append(Button.inline("⬅ Previous", data=f"prev_{user_id}"))
    if end < len(pokemon_list):
        buttons.append(Button.inline("Next ➡", data=f"next_{user_id}"))
    
    # Ensure that the buttons list is not empty before sending
    if buttons:
        return await event.respond(text, buttons=buttons)
    else:
        return await event.respond(text)

@bot.on(events.CallbackQuery)
async def handle_pagination(event):
    user_id = event.sender_id

    if not event.data:
        await event.answer()
        return

    data = event.data.decode("utf-8")

    if user_id not in user_messages:
        await event.answer()
        return

    # Update page based on button clicked
    if data.startswith("prev_"):
        user_pages[user_id] = max(0, user_pages[user_id] - 1)
    elif data.startswith("next_"):
        user_pages[user_id] += 1
    
    # Fetch and update the collection
    collection = get_collection(user_id)
    poke_count = {poke: collection.count(poke) for poke in set(collection)}
    pokemon_list = sorted([f"**{name}** x{count}" if count > 1 else f"**{name}**" for name, count in poke_count.items()])
    
    page = user_pages[user_id]
    per_page = 10  # Consistent value for pagination
    start = page * per_page
    end = start + per_page
    text = "**📜 Your Pokémon Collection:**\n\n" + "\n".join(pokemon_list[start:end])
    
    buttons = []
    if page > 0:
        buttons.append(Button.inline("⬅ Previous", data=f"prev_{user_id}"))
    if end < len(pokemon_list):
        buttons.append(Button.inline("Next ➡", data=f"next_{user_id}"))
    
    # Update the message and store the new message ID
    await bot.edit_message(event.chat_id, user_messages[user_id], text, buttons=buttons)
    await event.answer()

@bot.on(events.NewMessage)
async def message_handler(event):
    global current_pokemon
    chat_id = event.chat_id

    # Ignore PMs (Only track messages in groups)
    if event.is_private:
        return

    user_id = event.sender_id
    username = event.sender.username
    text = event.raw_text.lower()

    add_user(user_id, username)

    # Ensure `current_pokemon` is a dictionary
    if current_pokemon is None:
        current_pokemon = {}

    # Ensure `chat_id` exists in `current_pokemon` before accessing
    if chat_id in current_pokemon and current_pokemon[chat_id] is not None:
        if text == current_pokemon[chat_id]["name"]:
            add_pokemon(user_id, current_pokemon[chat_id]["name"])
            await event.reply(f"🎉 {username} caught {current_pokemon[chat_id]['name']}! 🎉")
            current_pokemon[chat_id] = None  # Remove Pokémon from this chat
            return  # Exit after catching

    # Check if a new Pokémon should spawn in this specific chat
    if should_spawn_pokemon(chat_id):
        current_pokemon[chat_id] = get_random_pokemon()
        await bot.send_file(
            chat_id, 
            current_pokemon[chat_id]["image"], 
            caption="🐾 A wild Pokémon appeared! Reply with its name to catch it!"
        )



# Global battle data storage
battle_data = {}
battle_timeouts = {}  # To handle battle timeouts

@bot.on(events.NewMessage(pattern="/battle"))
async def battle(event):
    """Handle the /battle command to initiate a battle."""
    if not event.message.is_reply:
        await event.reply("⚠️ Please reply to a user to challenge them to a battle!")
        return

    opponent = await event.get_reply_message()
    challenger_id = event.sender_id
    opponent_id = opponent.sender_id

    if challenger_id == opponent_id:
        await event.reply("⚠️ You can't battle yourself!")
        return

    # Check if either player is already in a battle
    if challenger_id in battle_data or opponent_id in battle_data:
        await event.reply("⚠️ One or both players are already in a battle!")
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

    # Set a timeout for the battle request (e.g., 60 seconds)
    battle_timeouts[(challenger_id, opponent_id)] = asyncio.create_task(
        battle_timeout(challenger_id, opponent_id)
    )

async def battle_timeout(challenger_id, opponent_id):
    """Handle battle request timeouts."""
    await asyncio.sleep(60)  # 60 seconds timeout
    if (challenger_id, opponent_id) in battle_timeouts:
        await bot.send_message(challenger_id, "⚠️ Battle request timed out!")
        await bot.send_message(opponent_id, "⚠️ Battle request timed out!")
        del battle_timeouts[(challenger_id, opponent_id)]

@bot.on(events.CallbackQuery(pattern=r"accept_(\d+)_(\d+)"))
async def accept_battle(event):
    """Handle battle acceptance."""
    challenger_id, opponent_id = map(int, event.data.decode().split("_")[1:])

    # Cancel the timeout task
    if (challenger_id, opponent_id) in battle_timeouts:
        battle_timeouts[(challenger_id, opponent_id)].cancel()
        del battle_timeouts[(challenger_id, opponent_id)]

    challenger_pokemon = get_collection(challenger_id)
    opponent_pokemon = get_collection(opponent_id)

    if not challenger_pokemon or not opponent_pokemon:
        await bot.send_message(challenger_id, "⚠️ Battle canceled! One or both players have no Pokémon.")
        await bot.send_message(opponent_id, "⚠️ Battle canceled! One or both players have no Pokémon.")
        return

    # Pick random Pokémon for each player (max 5)
    challenger_pokemon = random.sample(challenger_pokemon, min(5, len(challenger_pokemon)))
    opponent_pokemon = random.sample(opponent_pokemon, min(5, len(opponent_pokemon)))

    turn = random.choice([challenger_id, opponent_id])

    # Initialize battle data
    battle_data[challenger_id] = {"opponent": opponent_id, "pokemon": challenger_pokemon, "score": 0}
    battle_data[opponent_id] = {"opponent": challenger_id, "pokemon": opponent_pokemon, "score": 0}

    challenger_entity = await bot.get_entity(challenger_id)
    opponent_entity = await bot.get_entity(opponent_id)

    await bot.send_message(challenger_id, f"✅ Battle Accepted! You will face {opponent_entity.first_name}")
    await bot.send_message(opponent_id, f"✅ Battle Accepted! You will face {challenger_entity.first_name}")

    await start_round(turn)

@bot.on(events.CallbackQuery(pattern=r"decline_(\d+)_(\d+)"))
async def decline_battle(event):
    """Handle battle decline."""
    challenger_id, _ = map(int, event.data.decode().split("_")[1:])
    await event.answer("❌ Battle Declined", alert=True)
    await bot.send_message(challenger_id, "⚠️ Your opponent declined the battle!")

async def start_round(player_id):
    """Start a new round of the battle."""
    buttons = get_stat_buttons()
    await bot.send_message(player_id, "🎮 **Choose a stat for this round!**", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"pick_(.+)"))
async def handle_pick_stat(event):
    """Handle stat selection for the battle round."""
    user_id = event.sender_id
    stat_choice = event.data.decode().split("_", 1)[1]  # Extract the chosen stat

    if user_id not in battle_data:
        await event.answer("⚠️ You're not in an active battle!", alert=True)
        return

    # Map button callback data to stat keys
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

    # Store the chosen stat
    battle_data[user_id]["chosen_stat"] = chosen_stat
    print(f"Player {user_id} chose stat: {chosen_stat}")

    await event.edit(f"✅ You have chosen **{chosen_stat.upper()}**!,Wait for your turn")

    # Check if opponent has chosen a stat
    if "chosen_stat" in battle_data[opponent_id]:
        await compare_stats(user_id, opponent_id)
    else:
        await bot.send_message(opponent_id, "🔹 Your opponent has chosen a stat! Choose yours now.", buttons=get_stat_buttons())

async def compare_stats(player1, player2):
    """Compare stats and determine the round winner."""
    if not battle_data.get(player1) or not battle_data.get(player2):
        return

    if not battle_data[player1]["pokemon"] or not battle_data[player2]["pokemon"]:
        await declare_winner(player1, player2)
        return

    p1_pokemon = battle_data[player1]["pokemon"].pop(0)
    p2_pokemon = battle_data[player2]["pokemon"].pop(0)

    p1_stats = get_pokemon_stats(p1_pokemon) or {}
    p2_stats = get_pokemon_stats(p2_pokemon) or {}

    # Get each player's chosen stat
    stat1 = battle_data[player1].pop("chosen_stat")
    stat2 = battle_data[player2].pop("chosen_stat")

    print(f"Comparing stats for {p1_pokemon} ({stat1}) vs {p2_pokemon} ({stat2})")

    stat_value_1 = p1_stats.get(stat1, 0)
    stat_value_2 = p2_stats.get(stat2, 0)

    print(f"{p1_pokemon} {stat1}: {stat_value_1}")
    print(f"{p2_pokemon} {stat2}: {stat_value_2}")

    winner = None
    if stat_value_1 > stat_value_2:
        winner = player1
    elif stat_value_1 < stat_value_2:
        winner = player2

    result_message = f"⚔️ **{p1_pokemon}** ({stat1.upper()}: {stat_value_1}) vs **{p2_pokemon}** ({stat2.upper()}: {stat_value_2})\n"

    if winner:
        battle_data[winner]["score"] += 1
        winner_entity = await bot.get_entity(winner)
        result_message += f"🏆 **{winner_entity.first_name} wins this round!**"
    else:
        result_message += "⚖️ **It's a tie!**"

    await bot.send_message(player1, result_message)
    await bot.send_message(player2, result_message)

    # Track round history
    battle_data[player1].setdefault("round_history", []).append(result_message)
    battle_data[player2].setdefault("round_history", []).append(result_message)

    # If both players have Pokémon left, start the next round
    if battle_data[player1]["pokemon"]:
        await start_round(player2 if winner == player1 else player1)
    else:
        await declare_winner(player1, player2)


async def declare_winner(player1, player2):
    if player1 not in battle_data or player2 not in battle_data:
        return

    score1 = battle_data[player1].get("score", 0)
    score2 = battle_data[player2].get("score", 0)

    player1_entity = await bot.get_entity(player1)
    player2_entity = await bot.get_entity(player2)

    # Build the final battle summary
    summary = "\U0001F3C6 **Battle Over! Final Scores:**\n"
    summary += f"\U0001F539 {player1_entity.first_name}: {score1} Wins\n"
    summary += f"\U0001F539 {player2_entity.first_name}: {score2} Wins\n\n"
    summary += "**Round History:**\n"

    for i, result in enumerate(battle_data[player1].get("round_history", []), start=1):
        summary += f"**Round {i}**\n{result}\n"

    # Determine the winner and loser
    winner_id = player1 if score1 > score2 else player2
    loser_id = player2 if winner_id == player1 else player1

    if score1 > score2:
        summary += f"\n\U0001F3C5 **{player1_entity.first_name} is the champion!**"
    elif score2 > score1:
        summary += f"\n\U0001F3C5 **{player2_entity.first_name} is the champion!**"
    else:
        summary += "\n⚖️ **It's a tie!**"

    # Distribute rewards
    winner_reward, loser_reward = distribute_rewards(winner_id, loser_id, score1, score2)

    # Notify players of their rewards
    await bot.send_message(winner_id, f"\U0001F3C6 You won the battle and earned {winner_reward} PokéCoins!")
    await bot.send_message(loser_id, f"\U0001F494 You lost the battle but earned {loser_reward} PokéCoins!")

    # Send the summary to both players
    await bot.send_message(player1, summary)
    await bot.send_message(player2, summary)

    # Clean up battle data
    del battle_data[player1]
    del battle_data[player2]

def get_stat_buttons():
    return [
        [Button.inline("❤️ HP", "pick_hp"), Button.inline("⚔️ ATK", "pick_attack")],
        [Button.inline("🛡 DEF", "pick_defense"), Button.inline("🔥 SP. ATK", "pick_sp_attack")],
        [Button.inline("🌀 SP. DEF", "pick_sp_defense"), Button.inline("⚡ SPD", "pick_speed")]
    ]



@bot.on(events.NewMessage(pattern="/myinventory"))
async def my_inventory(event):
    user_id = event.sender_id
    pokecoins = get_pokecoins(user_id)

    await event.reply(f"💰 **Your PokéCoins:** {pokecoins}")



@bot.on(events.NewMessage(pattern="/stats (.+)"))
async def pokemon_stats(event):
    user_id = event.sender_id
    pokemon_name = event.pattern_match.group(1).strip().lower()

    # Check if the Pokémon is in the user's collection
    collection = get_collection(user_id)

    if not collection or pokemon_name not in [poke.lower() for poke in collection]:
        await event.reply(f"❌ You don’t own {pokemon_name.capitalize()}!")
        return

    # Get Pokémon stats
    stats = get_pokemon_stats(pokemon_name)
    
    if not stats:
        await event.reply("❌ Pokémon not found! Make sure you entered the correct name.")
        return

    # Count how many of this Pokémon the user owns
    pokemon_count = sum(1 for poke in collection if poke.lower() == pokemon_name)

    # Get evolution details
    evolved_pokemon = get_next_evolution(pokemon_name)
    evolve_button = None  # Default: No button

    if evolved_pokemon:
        next_evolution = get_next_evolution(evolved_pokemon)  # Check if it's final form
        required_count = 10 if next_evolution else 20  # 1 for second form, 2 for final form

        # Button text logic
        if pokemon_count >= required_count:
            button_text = f"✅ Ready to Evolve! ({pokemon_count}/{required_count})"
        else:
            button_text = f"🔄 Evolve ({pokemon_count}/{required_count})"

        # Create button
        evolve_button = [[Button.inline(button_text, f"evolve_{pokemon_name}")]]
    
    # Build stats message
    message = (
        f"📊 **{stats['name']} Stats:**\n"
        f"❤️ HP: {stats['hp']}\n"
        f"⚔️ Attack: {stats['attack']}\n"
        f"🛡️ Defense: {stats['defense']}\n"
        f"🔴 Sp. Attack: {stats['special_attack']}\n"
        f"🔵 Sp. Defense: {stats['special_defense']}\n"
        f"⚡ Speed: {stats['speed']}"
    )

    await bot.send_file(event.chat_id, stats["image"], caption=message, buttons=evolve_button)


@bot.on(events.CallbackQuery(pattern=r"evolve_(.+)"))
async def evolve_button(event):
    user_id = event.sender_id
    pokemon_name = event.data.decode().split("_", 1)[1]  # Get the Pokémon name

    collection = get_collection(user_id)

    if pokemon_name not in [poke.lower() for poke in collection]:
        await event.answer(f"❌ You no longer have {pokemon_name.capitalize()}!", alert=True)
        return

    evolved_pokemon = get_next_evolution(pokemon_name)

    if not evolved_pokemon:
        await event.answer(f"❌ {pokemon_name.capitalize()} cannot evolve further!", alert=True)
        return

    # Count how many of this Pokémon the user has
    pokemon_count = sum(1 for poke in collection if poke.lower() == pokemon_name)
    next_evolution = get_next_evolution(evolved_pokemon)  # Check if it's the final form
    required_count = 10 if next_evolution else 20  # 1 Pokémon for 2nd form, 2 for final form

    if pokemon_count < required_count:
        await event.answer(f"❌ You need at least {required_count} copies of {pokemon_name.capitalize()} to evolve!", alert=True)
        return

    # Perform Evolution: Remove base form & add evolved form
    evolve_pokemon(user_id, pokemon_name, evolved_pokemon)  # Database update

    # Fetch new stats and image
    evolved_stats = get_pokemon_stats(evolved_pokemon)
    
    if evolved_stats:
        # Build new stats message
        new_message = (
            f"🎉 **{pokemon_name.capitalize()} evolved into {evolved_pokemon.capitalize()}!** ✨\n\n"
            f"📊 **{evolved_stats['name']} Stats:**\n"
            f"❤️ HP: {evolved_stats['hp']}\n"
            f"⚔️ Attack: {evolved_stats['attack']}\n"
            f"🛡️ Defense: {evolved_stats['defense']}\n"
            f"🔴 Sp. Attack: {evolved_stats['special_attack']}\n"
            f"🔵 Sp. Defense: {evolved_stats['special_defense']}\n"
            f"⚡ Speed: {evolved_stats['speed']}"
        )

        # Send updated message with the evolved Pokémon's image
        await event.edit(new_message, file=evolved_stats["image"], buttons=None)
    else:
        await event.edit(f"🎉 **{pokemon_name.capitalize()} evolved into {evolved_pokemon.capitalize()}!** ✨")


@bot.on(events.NewMessage(pattern="/shop"))
async def shop(event):
    user_id = event.sender_id

    refresh_shop()  # Ensure shop is set for today

    # Get today's Pokémon shop list
    conn, cursor = get_db_connection()
    cursor.execute("SELECT pokemon, price FROM shop WHERE date = DATE('now')")
    shop_items = cursor.fetchall()
    conn.close()

    if not shop_items:
        await event.reply("❌ No Pokémon available in the shop today. Try again tomorrow!")
        return

    message = "🛒 **Today's Pokémon Shop:**\n\n"
    buttons = []

    for pokemon, price in shop_items:
        message += f"🔹 **{pokemon.capitalize()}** - 💰 {price} PokéCoins\n"
        buttons.append([Button.inline(f"Buy {pokemon.capitalize()} ({price})", f"buy_{pokemon}")])

    await event.reply(message, buttons=buttons)


@bot.on(events.CallbackQuery(pattern=r"buy_(.+)"))
async def buy_button(event):
    user_id = event.sender_id
    pokemon_name = event.data.decode().split("_", 1)[1]  # Extract Pokémon name

    result = buy_pokemon(user_id, pokemon_name)
    await event.answer(result, alert=True)


@bot.on(events.NewMessage(pattern=r"/add (\w+) (\S+) (\d+)"))
async def add_resource_command(event):
    sender_id = event.sender_id
    if sender_id != BOT_OWNER_ID:
        await event.reply("❌ You are not authorized to use this command!")
        return

    resource = event.pattern_match.group(1).lower()  # Resource type (pokecoins/pokemon)
    amount_or_pokemon = event.pattern_match.group(2)  # Amount or Pokémon name
    target_user_id = int(event.pattern_match.group(3))  # Target user ID

    print(f"🟢 /add command received: {resource} {amount_or_pokemon} for User {target_user_id}")  # Debug log

    if resource == "pokecoins":
        amount = int(amount_or_pokemon)
        if amount <= 0:
            await event.reply("❌ Amount must be greater than zero!")
            return
        result = add_resource(target_user_id, "pokecoins", amount)

    elif resource == "pokemon":
        pokemon_name = amount_or_pokemon.lower()
        add_pokemon(target_user_id, pokemon_name)  # Use your existing function
        result = f"✅ Successfully added {pokemon_name.capitalize()} to user {target_user_id}!"

    else:
        result = "❌ Invalid resource! Use `pokecoins` or `pokemon`."

    print(f"🟢 Result: {result}")  # Debug log
    await event.reply(result)





app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

def run_server():
    app.run(host="0.0.0.0", port=8000)

threading.Thread(target=run_server, daemon=True).start()


@bot.on(events.NewMessage(pattern="/backup"))
async def backup(event):
    if event.sender_id != BOT_OWNER_ID:
        await event.reply("You are not authorized to use this command.")
        return

    db_path = "pokemon_game.db"

    if os.path.exists(db_path):
        await bot.send_file(event.chat_id, db_path, caption="Here is the latest database backup.")
    else:
        await event.reply("Database file not found.")

@bot.on(events.NewMessage(pattern=r"/drop_time (\d+)"))
async def change_threshold(event):
    sender_id = event.sender_id
    chat_id = event.chat_id  # Get the group ID

    if sender_id != BOT_OWNER_ID:
        await event.reply("❌ You are not authorized to change the drop time!")
        return

    new_threshold = int(event.pattern_match.group(1))

    if new_threshold < 1:
        await event.reply("❌ Threshold must be at least 1!")
        return

    # Update the threshold for this specific group in the database
    set_drop_time(chat_id, new_threshold)

    await event.reply(f"✅ Pokémon spawn threshold updated to **{new_threshold} messages** for this group!")

setup_shop()
init_db()
print("Bot is running...")
bot.run_until_disconnected()
