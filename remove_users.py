import sqlite3

db_path = "linkedin_engagement.db"
names_to_remove = ["Audrew Pelodan", "André Melegari", "Alexandre Miller"]

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Find users to remove
print("Procurando usuários para remover...")
user_ids_to_remove = []

for name in names_to_remove:
    cursor.execute("SELECT usuario_id, nome FROM users WHERE nome LIKE ?", (f"%{name}%",))
    results = cursor.fetchall()
    if results:
        for user_id, full_name in results:
            print(f"  Encontrado: {full_name} (ID: {user_id})")
            user_ids_to_remove.append(user_id)
    else:
        print(f"  Nenhum usuário encontrado com nome contendo: {name}")

if user_ids_to_remove:
    print(f"\nRemovendo {len(user_ids_to_remove)} usuário(s)...")

    # Remove from engagement table
    for user_id in user_ids_to_remove:
        cursor.execute("DELETE FROM engagement WHERE usuario_id = ?", (user_id,))
        print(f"  Removidas interações do usuário {user_id}")

    # Remove from users table
    for user_id in user_ids_to_remove:
        cursor.execute("DELETE FROM users WHERE usuario_id = ?", (user_id,))
        print(f"  Removido usuário {user_id}")

    # Commit changes
    conn.commit()
    print("\nDados removidos com sucesso!")
else:
    print("\nNenhum usuário encontrado para remover.")

conn.close()
