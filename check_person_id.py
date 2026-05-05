import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASS')
    )
    
    with conn.cursor() as cur:
        # Check if person_id column exists
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'detections' AND column_name = 'person_id'
        """)
        result = cur.fetchone()
        print(f'person_id column: {result}')
        
        # Check sample data
        cur.execute('SELECT COUNT(*) FROM detections')
        total = cur.fetchone()[0]
        print(f'Total detections: {total}')
        
        # Check for any person_id values
        cur.execute('SELECT COUNT(*) FROM detections WHERE person_id IS NOT NULL')
        with_person_id = cur.fetchone()[0]
        print(f'Detections with person_id: {with_person_id}')
        
        # Check for specific UUID
        uuid = 'd964a4c7-e6ad-4530-9ee3-8a4b0fdb2ddd'
        cur.execute('SELECT COUNT(*) FROM detections WHERE person_id = %s', (uuid,))
        found = cur.fetchone()[0]
        print(f'Found UUID {uuid}: {found}')
        
    conn.close()
    
except Exception as e:
    print(f'Error: {e}')
