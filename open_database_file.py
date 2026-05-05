import olefile
from PIL import Image
import io

file_path = 'E:/ALL_CODE/my-project/Thumbs.db'

with olefile.OleFileIO(file_path) as ole:
    for entry in ole.listdir():
        # Thumbs.db stores images in 'streams'
        if entry[0].startswith('256'):
            stream = ole.openstream(entry)
            data = stream.read()
            
            # The data inside is usually a raw JPEG or BMP
            try:
                img = Image.open(io.BytesIO(data))
                filename = f"extracted_{entry[0]}.jpg"
                img.save(filename)
                print(f"Saved: {filename}")
            except Exception as e:
                print(f"Could not convert {entry[0]}: {e}")