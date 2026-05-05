import sqlite3

db_path = "linkedin_engagement.db"
names_to_check = ["Audrew Pelodan", "André Melegari", "Alexandre Miller"]

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Verificando remocao de dados...")
all_removed = True

for name in names_to_check:
    cursor.execute("SELECT COUNT(*) FROM users WHERE nome LIKE ?", (f"%{name}%",))
    count = cursor.fetchone()[0]
    if count == 0:
        print(f"  OK {name}: removido com sucesso")
    else:
        print(f"  ERRO {name}: ainda existem {count} registro(s)")
        all_removed = False

# Get overall database stats
cursor.execute("SELECT COUNT(*) FROM users")
total_users = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM engagement")
total_engagement = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM posts")
total_posts = cursor.fetchone()[0]

print(f"\nEstatisticas do banco de dados:")
print(f"  Total de usuarios: {total_users}")
print(f"  Total de interacoes: {total_engagement}")
print(f"  Total de posts: {total_posts}")

if all_removed:
    print("\nOK - Todos os dados foram removidos com sucesso!")
else:
    print("\nERRO - Alguns dados ainda estao no banco de dados.")

conn.close()
