#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sqlite3
import bcrypt
import getpass
import sys

# Chemin vers la base de données (à adapter si nécessaire)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'socialplace.db')

def main():
    print("=== Changement de mot de passe utilisateur ===\n")

    # Vérifier que la base existe
    if not os.path.exists(DB_PATH):
        print(f"❌ Base de données introuvable : {DB_PATH}")
        sys.exit(1)

    # Demander le nom d'utilisateur
    username = input("Nom d'utilisateur : ").strip()
    if not username:
        print("❌ Le nom d'utilisateur ne peut pas être vide.")
        sys.exit(1)

    # Vérifier que l'utilisateur existe
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM user WHERE username = ?", (username,))
    user = cursor.fetchone()
    if not user:
        print(f"❌ L'utilisateur '{username}' n'existe pas.")
        conn.close()
        sys.exit(1)

    # Saisie du nouveau mot de passe (caché)
    try:
        password = getpass.getpass("Nouveau mot de passe : ")
        confirm = getpass.getpass("Confirmer le mot de passe : ")
    except KeyboardInterrupt:
        print("\n\n❌ Opération annulée.")
        conn.close()
        sys.exit(1)

    if password != confirm:
        print("❌ Les mots de passe ne correspondent pas.")
        conn.close()
        sys.exit(1)

    if len(password) < 6:
        print("❌ Le mot de passe doit contenir au moins 6 caractères.")
        conn.close()
        sys.exit(1)

    # Hacher le mot de passe avec bcrypt
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Mise à jour dans la base
    cursor.execute("UPDATE user SET password_hash = ? WHERE username = ?", (hashed, username))
    conn.commit()
    conn.close()

    print(f"\n✅ Mot de passe de '{username}' modifié avec succès !")

if __name__ == "__main__":
    main()
