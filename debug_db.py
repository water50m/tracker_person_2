from src.services.database import DatabaseService

def check_detection(det_id):
    db = DatabaseService()
    with db.conn.cursor() as cur:
        # Check by ID
        cur.execute("SELECT id, image_path FROM detections WHERE id::text = %s", (det_id,))
        row = cur.fetchone()
        if row:
            print(f"Found detection: {row[0]}")
            print(f"Image Path: '{row[1]}'")
            if not row[1]:
                print("WARNING: image_path is NULL or Empty!")
        else:
            print("Detection not found!")

if __name__ == "__main__":
    check_detection("be603bb1-82c9-4030-ba1d-913bf1f5200b")
