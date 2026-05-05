import torch

weights_path = r'E:\ALL_CODE\my-project\models\resnet50_focused_epoch_30.pth'
print("กำลังตรวจสอบไฟล์โมเดล...")
checkpoint = torch.load(weights_path, map_location='cpu')
state_dict = checkpoint['model_state_dict'] if 'model_state_dict' in checkpoint else checkpoint

has_nan = False
for name, param in state_dict.items():
    if torch.isnan(param).any():
        print(f"❌ พัง! ตรวจพบค่า NaN ฝังอยู่ใน Layer: {name}")
        has_nan = True
        break # เจออันเดียวก็พังแล้ว หยุดหาได้เลย

if not has_nan:
    print("✅ รอด! น้ำหนักโมเดลปกติ ไม่มีค่า NaN ฝังอยู่")