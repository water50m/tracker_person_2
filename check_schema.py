from src.services.database import DatabaseService

db = DatabaseService()
print('Detections table schema:')
db._ensure_connection()
cur = db.conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'detections' ORDER BY ordinal_position")
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]}')

print('\nDetection_colors table schema:')
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'detection_colors' ORDER BY ordinal_position")
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]}')
