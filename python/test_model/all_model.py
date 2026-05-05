import cv2
import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
from ultralytics import YOLO
from tqdm import tqdm
from collections import Counter
import numpy as np

# ==========================================
# 1. การตั้งค่าและ Input
# ==========================================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"🚀 Benchmarking on: {device}")

# ❗️ กำหนดไฟล์วิดีโอทดสอบ
VIDEO_PATH = r"E:\ALL_CODE\my-project\tracked_results\combined_results\combined_target_ids.mp4"

# ❗️ กำหนดผลเฉลย (Ground Truth) ให้สะกดตรงกับชื่อคลาสเป๊ะๆ
GT_UPPER = "ShortSleeve"  # เช่น 'ShortSleeve' หรือ 'LongSleeve'
GT_LOWER = "Shorts"       # เช่น 'Trousers', 'Shorts', 'Skirt&Dress'

# ❗️ กำหนดรายการโมเดลที่ต้องการทดสอบ (ใส่กี่อันก็ได้)
MODELS_TO_TEST = {
    "Model_A_Epoch10": r"E:\ALL_CODE\my-project\models\resnet18_epoch_10.pth",
    "Model_B_ResNet34_Epoch3": r"E:\ALL_CODE\my-project\models\resnet34_focused_epoch_3.pth",
    "Model_C_ResNet34_Epoch16": r"E:\ALL_CODE\my-project\models\resnet34_focused_epoch_16.pth",
    # "Model_D_Best_ResNet18_PA100K": r"E:\ALL_CODE\my-project\models\best_resnet18_pa100k.pth",
    # "Model_E_ResNet18_PA100K_Epoch1": r"E:\ALL_CODE\my-project\models\resnet18_pa100k_epoch_1.pth",
    # "Model_F_ResNet18_PA100K_Epoch36": r"E:\ALL_CODE\my-project\models\resnet18_focused_epoch_36.pth",
    # "Model_G_ResNet18_PA100K_Epoch10_1": r"E:\ALL_CODE\my-project\models\resnet18_focused_epoch_10_1.pth",
    # "Model_H_ResNet18_FOCUSED_Epoch1": r"E:\ALL_CODE\my-project\models\resnet18_focused_epoch_1.pth",
    "Model_I_ResNet18_FOCUSED_Epoch2": r"E:\ALL_CODE\my-project\models\resnet18_focused_epoch_10.pth",
    # "Model_J_Resnet50_custom_dataset": r"E:\ALL_CODE\my-project\models\best_clothing_model.pth",
    "Model_K_resnet50_full_dataset": r"E:\ALL_CODE\my-project\models\resnet50_focused_epoch_2.pth",
    "Model_L_resnet50_full_dataset_epoch_10": r"E:\ALL_CODE\my-project\models\resnet50_focused_epoch_10.pth",
    "Model_M_resnet50_full_dataset_epoch_20": r"E:\ALL_CODE\my-project\models\resnet50_focused_epoch_20.pth",
    "Model_N_resnet50_full_dataset_epoch_36": r"E:\ALL_CODE\my-project\models\resnet50_focused_epoch_36.pth",
    "Model_O_resnet50_full_dataset_epoch_35": r"E:\ALL_CODE\my-project\models\resnet50_focused_epoch_35.pth",
    "Model_P_resnet50_full_dataset_epoch_30": r"E:\ALL_CODE\my-project\models\resnet50_focused_epoch_30.pth"
    # "Model_C": "...",
}

ATTRIBUTES_26 = [
    'Female', 'AgeOver60', 'Age18-60', 'AgeLess18', 'Front', 'Side', 'Back', 
    'Hat', 'Glasses', 'HandBag', 'ShoulderBag', 'Backpack', 'HoldObjectsInFront', 
    'ShortSleeve', 'LongSleeve', 'UpperStripe', 'UpperLogo', 'UpperPlaid', 
    'UpperSplice', 'LowerStripe', 'LowerPattern', 'LongCoat', 'Trousers', 
    'Shorts', 'Skirt&Dress', 'boots'
]

ATTRIBUTES_20 = [
    'Age18-60', 'AgeLess18', 'AgeOver60', 'Female', 'LongCoat', 'LongSleeve', 
    'LowerPattern', 'LowerStripe', 'ShortSleeve', 'Shorts', 'Skirt&Dress', 
    'Trousers', 'UpperLogo', 'UpperPlaid', 'UpperSplice', 'UpperStride', 
    'boots', 'bottom_capri', 'dress', 'skirt'
]

ATTRIBUTES_5 = ['ShortSleeve', 'LongSleeve', 'Trousers', 'Shorts', 'Skirt&Dress']

# ==========================================
# 2. ฟังก์ชันโหลดโมเดลอัตโนมัติ
# ==========================================
def load_smart_model(weights_path):
    checkpoint = torch.load(weights_path, map_location=device)
    state_dict = checkpoint['model_state_dict'] if 'model_state_dict' in checkpoint else checkpoint
    
    # เช็คจำนวนคลาส
    num_classes = state_dict['fc.weight'].shape[0]
    
    # --- อัปเกรดการเช็คสถาปัตยกรรม (ResNet18, 34, 50) ---
    # ResNet50 เป็นตระกูล Bottleneck จะมีชั้น conv3 แทรกอยู่
    is_resnet50 = 'layer1.0.conv3.weight' in state_dict
    # ResNet34 จะมี block ที่ 3 ใน layer4 (layer4.2)
    is_resnet34 = 'layer4.2.conv1.weight' in state_dict and not is_resnet50
    
    if is_resnet50:
        model = models.resnet50(weights=None)
        # print("   -> ตรวจพบสถาปัตยกรรม: ResNet50")
    elif is_resnet34:
        model = models.resnet34(weights=None)
        # print("   -> ตรวจพบสถาปัตยกรรม: ResNet34")
    else:
        model = models.resnet18(weights=None)
        # print("   -> ตรวจพบสถาปัตยกรรม: ResNet18")

    model.fc = nn.Linear(model.fc.in_features, num_classes)
    model.load_state_dict(state_dict)
    model.to(device).eval()
    # if torch.cuda.is_available(): model = model.half()
    
    # --- เลือกลิสต์คลาสและตั้งค่า Index แบบไดนามิก ---
    if num_classes == 26:
        attrs = ATTRIBUTES_26
        sleeve_idx = [attrs.index('ShortSleeve'), attrs.index('LongSleeve')]
        bottom_idx = [attrs.index('Trousers'), attrs.index('Shorts'), attrs.index('Skirt&Dress')]
    elif num_classes == 20:
        attrs = ATTRIBUTES_20
        # หา Index ของท่อนบนและท่อนล่างอัตโนมัติ
        sleeve_idx = [attrs.index('ShortSleeve'), attrs.index('LongSleeve')]
        bottom_idx = [
            attrs.index('Trousers'), attrs.index('Shorts'), 
            attrs.index('bottom_capri'), attrs.index('dress'), attrs.index('skirt')
        ]
    else:
        # Default เป็น 5 คลาส
        attrs = ATTRIBUTES_5
        sleeve_idx = [attrs.index('ShortSleeve'), attrs.index('LongSleeve')]
        bottom_idx = [attrs.index('Trousers'), attrs.index('Shorts'), attrs.index('Skirt&Dress')]
    
    return model, attrs, sleeve_idx, bottom_idx

# โหลดโมเดลทั้งหมดเตรียมไว้ใน Dict
loaded_models = {}
for name, path in MODELS_TO_TEST.items():
    print(f"⏳ กำลังโหลด {name}...")
    loaded_models[name] = load_smart_model(path)

print("⏳ Loading YOLO11 Detection...")
yolo_model = YOLO('yolo11s.pt') 

classify_transform = transforms.Compose([
    transforms.Resize((256, 128)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

# ==========================================
# 3. เตรียมโครงสร้างเก็บสถิติ
# ==========================================
# โครงสร้างสำหรับเก็บผลลัพธ์ของแต่ละโมเดล
stats = {
    name: {
        'detect_count': 0,
        'upper_votes': Counter(),
        'lower_votes': Counter(),
        'gt_upper_conf_sum': 0.0,
        'gt_lower_conf_sum': 0.0,
        'history': [] # เก็บ log รายครั้ง
    } for name in MODELS_TO_TEST.keys()
}

# ==========================================
# 4. วิ่งวิดีโอเบื้องหลัง (Headless Video Loop)
# ==========================================
cap = cv2.VideoCapture(VIDEO_PATH)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"\n🎬 เริ่มการทดสอบวิดีโอแบบเบื้องหลัง ({total_frames} เฟรม)...")

# ใช้ tqdm สร้างหลอดโหลดแทนการเปิดหน้าต่างวิดีโอ
for _ in tqdm(range(total_frames), desc="Processing Video"):
    success, frame = cap.read()
    if not success: break
    
    # ให้ YOLO หาคน
    results = yolo_model.track(frame, classes=[0], persist=True, verbose=False, conf=0.3)
    
    if results[0].boxes:
        boxes = results[0].boxes.xyxy.cpu().numpy()
        for box in boxes:
            x1, y1, x2, y2 = map(int, box)
            person_crop = frame[max(0,y1):y2, max(0,x1):x2]
            if person_crop.size == 0: continue
            
            # เตรียมภาพให้พร้อมสำหรับ ResNet
            img_pil = Image.fromarray(cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB))
            tensor = classify_transform(img_pil).unsqueeze(0).to(device)
            # if torch.cuda.is_available(): tensor = tensor.half()
            
            # --- ส่งให้ทุกโมเดลทดสอบ ---
            for name, (model, attrs, sleeve_idx, bottom_idx) in loaded_models.items():
                with torch.no_grad():
                    outputs = model(tensor)
                    probs = torch.sigmoid(outputs.float()).squeeze().cpu().numpy()
                
                # 1. หาว่าโมเดลนี้เดา Upper และ Lower ว่าอะไร
                upper_probs = [probs[i] for i in sleeve_idx]
                max_up_idx = sleeve_idx[np.argmax(upper_probs)]
                pred_upper = attrs[max_up_idx]
                pred_upper_conf = probs[max_up_idx]
                
                lower_probs = [probs[i] for i in bottom_idx]
                max_low_idx = bottom_idx[np.argmax(lower_probs)]
                pred_lower = attrs[max_low_idx]
                pred_lower_conf = probs[max_low_idx]
                
                # 2. ดึงคะแนนความมั่นใจของหน้าเฉลย (Ground Truth)
                try:
                    gt_up_idx = attrs.index(GT_UPPER)
                    gt_upper_conf = probs[gt_up_idx]
                except ValueError:
                    gt_upper_conf = 0.0 # กรณีโมเดลนั้นไม่มีคลาสนี้
                    
                try:
                    gt_low_idx = attrs.index(GT_LOWER)
                    gt_lower_conf = probs[gt_low_idx]
                except ValueError:
                    gt_lower_conf = 0.0

                # 3. บันทึกสถิติ
                stats[name]['detect_count'] += 1
                stats[name]['upper_votes'][pred_upper] += 1
                stats[name]['lower_votes'][pred_lower] += 1
                stats[name]['gt_upper_conf_sum'] += gt_upper_conf
                stats[name]['gt_lower_conf_sum'] += gt_lower_conf
                
                # บันทึก log รายครั้ง
                log_entry = (f"Pred:[{pred_upper}({pred_upper_conf:.2f}), {pred_lower}({pred_lower_conf:.2f})] | "
                             f"GT_Conf:[{GT_UPPER}: {gt_upper_conf:.2f}, {GT_LOWER}: {gt_lower_conf:.2f}]")
                stats[name]['history'].append(log_entry)

cap.release()

# ==========================================
# 5. สรุปผลการทำงานเปรียบเทียบ (Summary Report)
# ==========================================
print("\n" + "="*60)
print(f"📊 สรุปผลการทดสอบ Benchmark (เฉลย: บน={GT_UPPER}, ล่าง={GT_LOWER})")
print("="*60)

for name, s in stats.items():
    count = s['detect_count']
    if count == 0:
        print(f"\n🏷️ โมเดล: {name}\n❌ ไม่พบการจับภาพบุคคลเลย")
        continue
        
    avg_gt_up_conf = s['gt_upper_conf_sum'] / count
    avg_gt_low_conf = s['gt_lower_conf_sum'] / count
    
    # ดึงผู้ชนะโหวตอันดับ 1
    best_upper = s['upper_votes'].most_common(1)[0]
    best_lower = s['lower_votes'].most_common(1)[0]

    print(f"\n🏷️ โมเดล: {name}")
    print(f"  ▪️ จำนวนครั้งที่ตรวจจับ: {count} ครั้ง")
    print(f"  ▪️ ผลโหวตส่วนบน (ชนะ): {best_upper[0]} ({best_upper[1]}/{count} ครั้ง)")
    print(f"  ▪️ ผลโหวตส่วนล่าง (ชนะ): {best_lower[0]} ({best_lower[1]}/{count} ครั้ง)")
    print(f"  ▪️ Confidence ของ '{GT_UPPER}' -> รวม: {s['gt_upper_conf_sum']:.2f} | เฉลี่ย: {avg_gt_up_conf:.2f}")
    print(f"  ▪️ Confidence ของ '{GT_LOWER}' -> รวม: {s['gt_lower_conf_sum']:.2f} | เฉลี่ย: {avg_gt_low_conf:.2f}")
    
    # โชว์ตัวอย่างการจับภาพ 3 ครั้งแรก
    print("  ▪️ ตัวอย่างผลลัพธ์รายครั้ง (3 เฟรมแรก):")
    for log in s['history'][:3]:
        print(f"      - {log}")

print("\n" + "="*60)
print("✅ การรัน Benchmark เสร็จสิ้น!")