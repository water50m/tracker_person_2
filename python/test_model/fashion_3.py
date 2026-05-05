from transformers import pipeline

pipe = pipeline("object-detection", model="valentinafevu/yolos-fashionpedia")

# ใส่ URL รูปภาพ หรือ Path ในเครื่องลงไป
result = pipe(r"C:\Users\pmach\Downloads\a-business-man-stands-against-white-background-with-his-arms-crossed-ai-generative-photo.jpg")

print(result)