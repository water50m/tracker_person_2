import os
import cv2
import torch
import numpy as np
from ultralytics import YOLO

# 1. โหลดโมเดลเสื้อผ้า (Classification Model)
model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "models/clothing_classifier.pt"))
print(f"Loading Model: {model_path}")
model = YOLO(model_path)

# 2. สร้างรูปจำลองแบบคน (สุ่มสี)
dummy_img = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)

print("\n--- ทดสอบการ X-Ray หา Vector จาก Model ---")
try:
    # ทดสอบใช้ .embed() (มีใน Ultralytics รุ่นใหม่)
    results = model.embed(source=dummy_img, verbose=False)
    
    if results and len(results) > 0:
        embeddings = results[0]
        print(f"✅ สำเร็จ! ใช้ .embed() ได้")
        print(f"📊 ขนาดของ Vector (จำนวนตัวเลขที่ใช้อธิบายเสื้อผ้า): {embeddings.shape}")
        if hasattr(embeddings, 'cpu'):
            print(f"ตัวอย่างค่า 5 ตัวแรก: {embeddings.cpu().numpy().flatten()[:5]}")
        else:
             print(f"ตัวอย่างค่า 5 ตัวแรก: {np.array(embeddings).flatten()[:5]}")
    else:
        print("❌ ไม่คืนค่าจาก .embed()")
except Exception as e:
    print(f"❌ .embed() ไม่ระบุว่าพังเพราะ: {e}")
    
    print("\n--- ลองวิธีที่ 2: ใช้ Forward Hook ก่อน Layer สุดท้าย ---")
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        # ดึงโมเดล PyTorch แท้ๆ ออกมา
        pytorch_model = model.model
        
        # เตรียมภาพ
        tensor_img = torch.from_numpy(dummy_img).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        tensor_img = torch.nn.functional.interpolate(tensor_img, size=(224, 224), mode='bilinear')
        tensor_img = tensor_img.to(device)
        
        features = None
        def hook_fn(module, input, output):
            global features
            features = output.clone().detach()

        # classification header ปกติจะอยู่ตัวท้ายๆ
        layer = list(pytorch_model.children())[-1] # ปกติ classification layer
        if hasattr(layer, 'linear'):
            target_layer = layer.linear
        else:
            target_layer = layer
            
        handle = list(pytorch_model.children())[-2].register_forward_hook(hook_fn)
        
        with torch.no_grad():
            _ = pytorch_model(tensor_img)
            
        handle.remove()
        
        if features is not None:
             print(f"✅ สำเร็จ! แงะ Vector ด้วย Hook ได้")
             print(f"📊 ขนาดของ Vector (1D Array): {features.shape}")
             print(f"ตัวอย่างค่า 5 ตัวแรก: {features.cpu().numpy().flatten()[:5]}")
        else:
             print("❌ Hook ไม่ทำงาน")

    except Exception as e2:
        print(f"❌ วิธีที่ 2 พังเพราะ: {e2}")

