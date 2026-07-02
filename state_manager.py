import json
import os
import datetime
from pathlib import Path
from config import STATE_FILE, BASE_DIR

def load_states():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Fehler beim Laden der State-Datei: {e}")
    return {}

def save_states(states):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(states, f, indent=4)
    except Exception as e:
        print(f"Fehler beim Speichern der State-Datei: {e}")

def get_user_state(chat_id):
    states = load_states()
    return states.get(str(chat_id), {})

def update_user_state(chat_id, key, value):
    states = load_states()
    chat_id_str = str(chat_id)
    if chat_id_str not in states:
        states[chat_id_str] = {}
    states[chat_id_str][key] = value
    save_states(states)

def clear_user_state(chat_id):
    states = load_states()
    chat_id_str = str(chat_id)
    if chat_id_str in states:
        user_name = states[chat_id_str].get("user_name")
        states[chat_id_str] = {}
        if user_name:
            states[chat_id_str]["user_name"] = user_name
        save_states(states)

# Compatibility wrappers for old template handling
def get_active_template(chat_id):
    return get_user_state(chat_id).get("active_template")

def set_active_template(chat_id, template_key):
    update_user_state(chat_id, "active_template", template_key)

def clear_active_template(chat_id):
    update_user_state(chat_id, "active_template", None)

# Message management for the secret website tab
def get_messages_file_path():
    env_path = os.getenv("WEBSITE_MESSAGES_JSON")
    if env_path:
        return Path(env_path)
    
    # BASE_DIR is dev/TelegramBots/memegen
    # BASE_DIR.parent.parent is dev/
    mil4nde_path = BASE_DIR.parent.parent / "mil4nde" / "messages.json"
    if mil4nde_path.parent.exists():
        return mil4nde_path
        
    return BASE_DIR / "messages.json"

def load_messages_from_file():
    path = get_messages_file_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Fehler beim Laden der Nachrichten: {e}")
    return []

def save_message_to_file(name, text, chat_id=None):
    now = datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
    path = get_messages_file_path()
    messages = load_messages_from_file()
    messages.append({
        "timestamp": now,
        "name": name,
        "text": text,
        "chat_id": chat_id
    })
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Fehler beim Speichern der Nachricht: {e}")
        return False

def delete_last_message_from_file(chat_id):
    path = get_messages_file_path()
    messages = load_messages_from_file()
    
    target_index = -1
    for i in range(len(messages) - 1, -1, -1):
        if str(messages[i].get("chat_id")) == str(chat_id):
            target_index = i
            break
            
    if target_index != -1:
        removed = messages.pop(target_index)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=4, ensure_ascii=False)
            return True, removed.get("text")
        except Exception as e:
            print(f"Fehler beim Löschen der letzten Nachricht: {e}")
            return False, None
    return False, None

def delete_all_messages_from_file(chat_id):
    path = get_messages_file_path()
    messages = load_messages_from_file()
    
    initial_count = len(messages)
    filtered_messages = [msg for msg in messages if str(msg.get("chat_id")) != str(chat_id)]
    removed_count = initial_count - len(filtered_messages)
    
    if removed_count > 0:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(filtered_messages, f, indent=4, ensure_ascii=False)
            return True, removed_count
        except Exception as e:
            print(f"Fehler beim Löschen aller Nachrichten: {e}")
            return False, 0
    return False, 0

def clear_entire_message_file() -> bool:
    """Empties the messages.json file completely."""
    path = get_messages_file_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Fehler beim Leeren der Nachrichten-Datei: {e}")
        return False

