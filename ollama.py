import os
import time
import hashlib
import base64
import sqlite3
import json
import requests
import bcrypt
from cryptography.fernet import Fernet
from datetime import datetime, timezone

# ============ CONFIGURATION ============
SECRET_KEY = 'votre-clee'          
DB_PATH = 'instance/socialplace.db'
SPACEAI_USERNAME = 'Pseudo'

OLLAMA_URL = 'localhost:11434'   # ou votre api ollama
OLLAMA_MODEL = 'dolphin3:8b'
POLL_INTERVAL = 5

# -------- SYSTEM PROMPT --------
SYSTEM_PROMPT = (
    "Tu es SpaceAI, un assistant intelligent et amical sur un réseau social appelé socialplace. "
    "Tu réponds aux messages privés des utilisateurs en français. "
    "Sois poli, utile, engage la conversation, et donne des réponses claires. "
    "Si tu ne connais pas la réponse, dis-le honnêtement. "
    "Tu peux poser des questions pour mieux comprendre ce que l'utilisateur attend."
)
# ========================================

def get_fernet():
    key = hashlib.sha256(SECRET_KEY.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)

def encrypt_content(plain_text):
    return get_fernet().encrypt(plain_text.encode()).decode()

def decrypt_content(encrypted_text):
    return get_fernet().decrypt(encrypted_text.encode()).decode()

def get_or_create_spaceai(conn):
    c = conn.cursor()
    c.execute("SELECT id FROM user WHERE username = ?", (SPACEAI_USERNAME,))
    row = c.fetchone()
    if row:
        return row[0]

    dummy_password = 'password'
    password_hash = bcrypt.hashpw(dummy_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    dummy_email = 'spaceai@example.com'
    normalized = dummy_email.lower().strip()
    email_hash = hashlib.sha256(normalized.encode()).hexdigest()
    encrypted_email = encrypt_content(normalized)

    c.execute("""
        INSERT INTO user (username, email, email_hash, password_hash,
                          is_admin, is_verified, profile_pic, bio, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (SPACEAI_USERNAME, encrypted_email, email_hash, password_hash,
          0, 0, 'default.png', 'Bot IA', datetime.now(timezone.utc).isoformat()))
    conn.commit()
    return c.lastrowid

def test_ollama_connection():
    """Vérifie que l'API Ollama est accessible."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": "Hello", "system": SYSTEM_PROMPT, "stream": False},
            timeout=5
        )
        if response.status_code == 200:
            print("✅ Connexion à Ollama établie.")
            return True
        else:
            print(f"⚠️ Ollama a répondu avec le statut {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Impossible de joindre Ollama : {e}")
        print(f"   Vérifiez que l'URL '{OLLAMA_URL}' est correcte et que le service tourne.")
        return False

def send_ollama_prompt(user_message):
    """Envoie le message de l'utilisateur avec le system prompt à Ollama."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": user_message,
        "system": SYSTEM_PROMPT,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get('response', '').strip()
    except Exception as e:
        print(f"⚠️ Erreur Ollama : {e}")
        return "Désolé, je n'arrive pas à réfléchir pour le moment."

def main():
    conn = sqlite3.connect(DB_PATH)
    spaceai_id = get_or_create_spaceai(conn)
    conn.close()
    print(f"✅ SpaceAI ID : {spaceai_id}")

    if not test_ollama_connection():
        print("⚠️ Le bot continuera mais les réponses seront des messages d'erreur.")

    processed_file = 'processed_messages.json'
    if os.path.exists(processed_file):
        with open(processed_file, 'r') as f:
            processed_ids = set(json.load(f))
    else:
        processed_ids = set()

    print("🤖 Bot SpaceAI démarré, en attente de messages...")
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                SELECT id, content, sender_id, encrypted
                FROM message
                WHERE receiver_id = ? AND sender_id != ? AND read = 0
                ORDER BY created_at ASC
            """, (spaceai_id, spaceai_id))
            rows = c.fetchall()

            for msg_id, content_data, sender_id, is_encrypted in rows:
                if msg_id in processed_ids:
                    continue

                if is_encrypted:
                    try:
                        decrypted = decrypt_content(content_data)
                    except Exception as e:
                        print(f"❌ Échec déchiffrement du message {msg_id} : {e}")
                        processed_ids.add(msg_id)
                        c.execute("UPDATE message SET read = 1 WHERE id = ?", (msg_id,))
                        conn.commit()
                        with open(processed_file, 'w') as f:
                            json.dump(list(processed_ids), f)
                        continue
                else:
                    decrypted = content_data

                print(f"📩 Nouveau message de l'utilisateur {sender_id} : {decrypted[:100]}...")
                response = send_ollama_prompt(decrypted)
                print(f"🤖 Réponse générée : {response[:100]}...")

                encrypted_response = encrypt_content(response)
                c.execute("""
                    INSERT INTO message (content, sender_id, receiver_id, created_at, read, encrypted)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (encrypted_response, spaceai_id, sender_id,
                      datetime.now(timezone.utc).isoformat(), 0, 1))
                conn.commit()

                c.execute("UPDATE message SET read = 1 WHERE id = ?", (msg_id,))
                conn.commit()
                processed_ids.add(msg_id)
                with open(processed_file, 'w') as f:
                    json.dump(list(processed_ids), f)

                print(f"✅ Réponse envoyée pour le message {msg_id}")

            conn.close()
        except Exception as e:
            print(f"⚠️ Erreur dans la boucle principale : {e}")
            time.sleep(5)

        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
