# ระบบจัดการสี (Color System)

เอกสารนี้อธิบายระบบวิเคราะห์และจัดกลุ่มสีที่ใช้ในโปรเจกต์

## ภาพรวม

ระบบสีประกอบด้วย 2 ระดับ:
1. **สีละเอียด (Detailed Colors)** - 63 สี สำหรับการ tracking ที่ต้องการความแม่นยำสูง
2. **กลุ่มสี (Color Groups)** - 22 กลุ่ม สำหรับการค้นหาที่ต้องการความกว้างขวาง

ระบบใช้ **Competitive Grouping Algorithm** ทำให้เปอร์เซ็นต์รวมของทุกกลุ่มเท่ากับ **100%** พอดี

---

## สีละเอียด (Detailed Colors) - 63 สี

สีละเอียดถูกกำหนดใน HSV Color Space (Hue: 0-179, Saturation: 0-255, Value: 0-255)

### 1. โทนสีแดง (Red) - 5 สี
| สี | ช่วง H | ช่วง S | ช่วง V | คำอธิบาย |
|---|---|---|---|---|
| red | 0-10 | 100-255 | 50-255 | แดงมาตรฐาน |
| dark_red | 0-10 | 50-255 | 20-80 | แดงเข้ม |
| crimson | 0-8 | 150-255 | 80-180 | คริมสัน |
| scarlet | 0-8 | 200-255 | 150-255 | สการ์เล็ต |
| maroon | 0-10 | 100-200 | 30-90 | มาลูน |

### 2. โทนสีส้ม (Orange) - 5 สี
| สี | ช่วง H | ช่วง S | ช่วง V | คำอธิบาย |
|---|---|---|---|---|
| orange | 10-25 | 100-255 | 80-255 | ส้มมาตรฐาน |
| dark_orange | 10-25 | 100-255 | 50-120 | ส้มเข้ม |
| amber | 20-35 | 150-255 | 150-255 | อำพัน |
| peach | 8-20 | 50-150 | 180-255 | พีช |
| coral | 8-15 | 150-255 | 180-255 | ปะการัง |

### 3. โทนสีเหลือง (Yellow) - 5 สี
| สี | ช่วง H | ช่วง S | ช่วง V | คำอธิบาย |
|---|---|---|---|---|
| yellow | 20-40 | 100-255 | 150-255 | เหลืองมาตรฐาน |
| gold | 25-40 | 150-255 | 150-220 | ทอง |
| light_yellow | 20-40 | 30-100 | 200-255 | เหลืองอ่อน |
| mustard | 25-40 | 100-200 | 100-180 | มัสตาร์ด |
| khaki | 20-35 | 30-100 | 150-220 | กากี |

### 4. โทนสีเขียว (Green) - 8 สี
| สี | ช่วง H | ช่วง S | ช่วง V | คำอธิบาย |
|---|---|---|---|---|
| green | 35-85 | 50-255 | 50-255 | เขียวมาตรฐาน |
| dark_green | 35-85 | 50-255 | 20-80 | เขียวเข้ม |
| light_green | 35-85 | 30-150 | 150-255 | เขียวอ่อน |
| olive | 35-65 | 30-100 | 50-150 | โอลีฟ |
| lime | 35-55 | 150-255 | 150-255 | มะนาว |
| forest_green | 40-70 | 80-200 | 30-100 | เขียวป่า |
| mint | 70-85 | 30-100 | 180-255 | มิ้นต์ |
| teal | 75-95 | 100-255 | 80-180 | ฟ้าเขียว |

### 5. โทนสีน้ำเงิน (Blue) - 9 สี
| สี | ช่วง H | ช่วง S | ช่วง V | คำอธิบาย |
|---|---|---|---|---|
| blue | 85-135 | 50-255 | 50-255 | น้ำเงินมาตรฐาน |
| dark_blue | 85-135 | 50-255 | 20-80 | น้ำเงินเข้ม |
| light_blue | 85-135 | 30-150 | 180-255 | ฟ้าอ่อน |
| navy | 95-125 | 100-255 | 20-70 | กรมท่า |
| sky_blue | 85-105 | 100-200 | 180-255 | ฟ้าสด |
| royal_blue | 100-120 | 150-255 | 80-180 | น้ำเงินราชา |
| cobalt | 105-125 | 150-255 | 100-200 | โคบอลต์ |
| turquoise | 80-100 | 100-200 | 150-255 | ฟ้าคราม |

### 6. โทนสีม่วง (Purple) - 8 สี
| สี | ช่วง H | ช่วง S | ช่วง V | คำอธิบาย |
|---|---|---|---|---|
| purple | 125-165 | 50-255 | 50-255 | ม่วงมาตรฐาน |
| dark_purple | 125-165 | 50-255 | 20-80 | ม่วงเข้ม |
| light_purple | 125-165 | 30-150 | 180-255 | ม่วงอ่อน |
| violet | 130-150 | 100-255 | 100-255 | ไวโอเล็ต |
| lavender | 130-155 | 30-100 | 180-255 | ลาเวนเดอร์ |
| magenta | 145-165 | 150-255 | 150-255 | แมเจนต้า |
| fuchsia | 150-165 | 200-255 | 150-255 | ฟุเชีย |
| plum | 140-160 | 100-200 | 80-180 | พลัม |

### 7. โทนสีน้ำตาล (Brown) - 6 สี
| สี | ช่วง H | ช่วง S | ช่วง V | คำอธิบาย |
|---|---|---|---|---|
| brown | 0-25 | 50-150 | 30-120 | น้ำตาลมาตรฐาน |
| dark_brown | 0-25 | 50-150 | 15-60 | น้ำตาลเข้ม |
| light_brown | 0-25 | 30-100 | 100-180 | น้ำตาลอ่อน |
| tan | 15-35 | 30-80 | 120-200 | แทน |
| beige | 20-40 | 20-60 | 180-255 | เบจ |
| camel | 20-35 | 40-100 | 100-180 | คาเมล |

### 8. โทนสีชมพู (Pink) - 6 สี
| สี | ช่วง H | ช่วง S | ช่วง V | คำอธิบาย |
|---|---|---|---|---|
| pink | 160-180 | 50-255 | 150-255 | ชมพูมาตรฐาน |
| light_pink | 160-180 | 30-150 | 200-255 | ชมพูอ่อน |
| hot_pink | 165-180 | 150-255 | 150-255 | ชมพูสด |
| rose | 165-180 | 100-200 | 120-200 | กุหลาบ |
| salmon | 0-15 | 100-200 | 150-255 | แซลมอน |

### 9. โทนสีเทา/ขาว/ดำ (Grayscale) - 7 สี
| สี | ช่วง H | ช่วง S | ช่วง V | คำอธิบาย |
|---|---|---|---|---|
| black | 0-180 | 0-50 | 0-40 | ดำ |
| dark_gray | 0-180 | 0-30 | 40-100 | เทาเข้ม |
| gray | 0-180 | 0-30 | 100-180 | เทา |
| light_gray | 0-180 | 0-30 | 180-220 | เทาอ่อน |
| white | 0-180 | 0-30 | 220-255 | ขาว |
| silver | 0-180 | 0-20 | 180-230 | เงิน |

---

## กลุ่มสี (Color Groups) - 22 กลุ่ม

กลุ่มสีใช้สำหรับการค้นหาที่กว้างขึ้น โดยรวมสีละเอียดหลายสีเข้าด้วยกัน

### 1. กลุ่มตามโทนสีหลัก (8 กลุ่ม)

| กลุ่ม | สีที่รวม | จำนวน |
|---|---|---|
| **red_tones** | red, dark_red, crimson, scarlet, maroon, pink, hot_pink, rose, salmon | 9 |
| **orange_tones** | orange, dark_orange, amber, peach, coral, gold, mustard, khaki | 8 |
| **yellow_tones** | yellow, gold, light_yellow, mustard, khaki, beige, tan, camel | 8 |
| **green_tones** | green, dark_green, light_green, olive, lime, forest_green, mint, teal | 8 |
| **blue_tones** | blue, dark_blue, light_blue, navy, sky_blue, royal_blue, cobalt, turquoise | 8 |
| **purple_tones** | purple, dark_purple, light_purple, violet, lavender, magenta, fuchsia, plum | 8 |
| **brown_tones** | brown, dark_brown, light_brown, tan, beige, camel, olive, khaki | 8 |
| **pink_tones** | pink, light_pink, hot_pink, rose, salmon, lavender, fuchsia | 7 |

### 2. กลุ่มตามความสว่าง (3 กลุ่ม)

| กลุ่ม | สีที่รวม | คำอธิบาย |
|---|---|---|
| **light_colors** | white, light_gray, silver, light_yellow, light_green, light_blue, light_purple, light_pink, sky_blue, mint, peach, beige | สีสว่าง |
| **dark_colors** | black, dark_gray, dark_red, dark_orange, dark_green, dark_blue, dark_purple, dark_brown, navy, maroon, forest_green | สีเข้ม |
| **medium_colors** | gray, red, orange, yellow, green, blue, purple, brown, pink, tan, camel, olive, teal, turquoise, violet, plum | สีปานกลาง |

### 3. กลุ่มตามความสดใส (3 กลุ่ม)

| กลุ่ม | สีที่รวม | คำอธิบาย |
|---|---|---|
| **vibrant_colors** | red, orange, yellow, green, blue, purple, pink, crimson, scarlet, amber, lime, sky_blue, royal_blue, cobalt, violet, magenta, fuchsia, hot_pink, turquoise | สีสดใส |
| **muted_colors** | gray, dark_gray, light_gray, silver, olive, khaki, tan, beige, camel, maroon, navy, forest_green, plum | สีกลางๆ |
| **pastel_colors** | light_yellow, light_green, light_blue, light_purple, light_pink, mint, lavender, peach, beige | สีพาสเทล |

### 4. กลุ่มตามอุณหภูมิสี (3 กลุ่ม)

| กลุ่ม | สีที่รวม | คำอธิบาย |
|---|---|---|
| **warm_colors** | red, orange, yellow, pink, crimson, scarlet, amber, gold, peach, coral, mustard, khaki, brown, tan, beige, camel, rose, salmon, hot_pink | สีอุ่น |
| **cool_colors** | green, blue, purple, cyan, teal, turquoise, sky_blue, royal_blue, cobalt, violet, lavender, magenta, fuchsia, plum, mint, navy, forest_green | สีเย็น |
| **neutral_colors** | black, white, gray, dark_gray, light_gray, silver, beige, tan, camel, khaki | สีกลาง |

### 5. กลุ่มสำหรับเสื้อผ้า (5 กลุ่ม)

| กลุ่ม | สีที่รวม | คำอธิบาย |
|---|---|---|
| **common_shirt_colors** | white, black, blue, gray, red, navy, light_blue, pink, purple, green, yellow, orange, brown, beige | สีเสื้อที่พบบ่อย (14 สี) |
| **common_pants_colors** | black, blue, gray, dark_blue, navy, brown, khaki, dark_gray, white, beige | สีกางเกง/กระโปรงที่พบบ่อย (10 สี) |
| **formal_colors** | black, white, gray, dark_gray, navy, dark_blue, brown | สีทางการ/ทำงาน |
| **casual_colors** | blue, green, red, yellow, orange, pink, purple, teal, turquoise, coral, mint, lavender | สีลำลอง/เที่ยว |

---

## Competitive Grouping Algorithm

### หลักการทำงาน

1. **แต่ละ pixel จะถูกกำหนดให้สีเดียว** - ไม่มีการซ้อนทับ
2. **Priority System** - สีที่มี priority สูงกว่าจะชนะเมื่อมีการทับซ้อน
3. **Normalization** - เปอร์เซ็นต์รวมจะถูกปรับให้เท่ากับ 100% เสมอ

### Priority Order สำหรับ Detailed Colors

สีจะถูกจัดเรียงตาม **confidence score** ซึ่งคำนวณจาก:
- ความใกล้เคียงกับกึ่งกลางของช่วง HSV
- ยิ่งใกล้กึ่งกลางยิ่งมี confidence สูง

```
Confidence = 1.0 - (H_dist + S_dist + V_dist) / 3.0
```

### Priority Order สำหรับ Color Groups

| ลำดับ | กลุ่ม | ความสำคัญ |
|---|---|---|
| 1 | formal_colors, casual_colors | บริบทการใช้งาน |
| 2 | vibrant_colors, pastel_colors | ความสดใส |
| 3 | red_tones, blue_tones, green_tones, ... | โทนสีหลัก |
| 4 | light_colors, dark_colors, medium_colors | ความสว่าง |
| 5 | warm_colors, cool_colors, neutral_colors | อุณหภูมิสี |
| 6 | common_shirt_colors, common_pants_colors | ประเภทเสื้อผ้า |

---

## ตาราง detection_colors (Detection Colors Table)

ตารางใหม่สำหรับเก็บข้อมูลสีแบบละเอียดและจัดกลุ่มตามหมวดหมู่

```sql
CREATE TABLE detection_colors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    detection_id UUID REFERENCES detections(id) ON DELETE CASCADE,
    
    -- Top 3 colors: [{"name": "red", "percentage": 45.5}, ...]
    top_colors JSONB NOT NULL DEFAULT '[]',
    
    -- 5 category columns for color groups
    tone_groups JSONB DEFAULT '{}',        -- {"red_tones": 45.5, "blue_tones": 30.0}
    brightness_groups JSONB DEFAULT '{}',  -- {"light_colors": 15.2}
    vibrancy_groups JSONB DEFAULT '{}',    -- {"vibrant_colors": 45.5}
    temperature_groups JSONB DEFAULT '{}', -- {"warm_colors": 45.5}
    clothing_groups JSONB DEFAULT '{}',    -- {"common_shirt_colors": 45.5}
    
    -- Summary for indexing
    primary_color VARCHAR(50),
    primary_tone_group VARCHAR(50),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_detection_colors_detection_id ON detection_colors(detection_id);
CREATE INDEX idx_detection_colors_primary_color ON detection_colors(primary_color);
CREATE INDEX idx_detection_colors_primary_tone ON detection_colors(primary_tone_group);
CREATE INDEX idx_detection_colors_top_colors ON detection_colors USING gin (top_colors);
CREATE INDEX idx_detection_colors_tone_groups ON detection_colors USING gin (tone_groups);
CREATE INDEX idx_detection_colors_brightness ON detection_colors USING gin (brightness_groups);
CREATE INDEX idx_detection_colors_vibrancy ON detection_colors USING gin (vibrancy_groups);
CREATE INDEX idx_detection_colors_temperature ON detection_colors USING gin (temperature_groups);
```

---

## พจนานุกรม อังกฤษ-ไทย (English-Thai Dictionary)

| English | ภาษาไทย | Category | คำอธิบาย |
|---------|---------|----------|----------|
| **red_tones** | โทนสีแดง | Tone Group | รวมสีแดงทั้งหมด |
| **orange_tones** | โทนสีส้ม | Tone Group | รวมสีส้มทั้งหมด |
| **yellow_tones** | โทนสีเหลือง | Tone Group | รวมสีเหลืองทั้งหมด |
| **green_tones** | โทนสีเขียว | Tone Group | รวมสีเขียวทั้งหมด |
| **blue_tones** | โทนสีน้ำเงิน | Tone Group | รวมสีน้ำเงินทั้งหมด |
| **purple_tones** | โทนสีม่วง | Tone Group | รวมสีม่วงทั้งหมด |
| **brown_tones** | โทนสีน้ำตาล | Tone Group | รวมสีน้ำตาลทั้งหมด |
| **pink_tones** | โทนสีชมพู | Tone Group | รวมสีชมพูทั้งหมด |
| **light_colors** | สีสว่าง | Brightness | สีที่มีความสว่างสูง |
| **dark_colors** | สีเข้ม | Brightness | สีที่มีความมืด/เข้ม |
| **medium_colors** | สีปานกลาง | Brightness | สีที่มีความสว่างปานกลาง |
| **vibrant_colors** | สีสดใส | Vibrancy | สีที่มีความสดใส/อิ่มตัวสูง |
| **muted_colors** | สีกลางๆ | Vibrancy | สีที่มีความอิ่มตัวปานกลาง |
| **pastel_colors** | สีพาสเทล | Vibrancy | สีที่มีความอ่อน/ซีด |
| **warm_colors** | สีอุ่น | Temperature | สีในตระกูลอุ่น (แดง, ส้ม, เหลือง) |
| **cool_colors** | สีเย็น | Temperature | สีในตระกูลเย็น (เขียว, น้ำเงิน, ม่วง) |
| **neutral_colors** | สีกลาง | Temperature | สีที่ไม่อุ่นไม่เย็น (ขาว, ดำ, เทา, น้ำตาลอ่อน) |
| **common_shirt_colors** | สีเสื้อทั่วไป | Clothing | สีเสื้อที่พบบ่อยในชีวิตประจำวัน |
| **common_pants_colors** | สีกางเกงทั่วไป | Clothing | สีกางเกงที่พบบ่อย |
| **formal_colors** | สีทางการ | Clothing | สีที่เหมาะกับชุดทางการ |
| **casual_colors** | สีลำลอง | Clothing | สีที่เหมาะกับชุดลำลอง |

---

## โครงสร้างข้อมูล (Data Structure)

### ก่อนแก้ไข (Old Structure)

```json
{
  "detailed_colors": {
    "red": 45.5,
    "dark_red": 12.3,
    "blue": 30.2
  },
  "color_groups": {
    "red_tones": {
      "colors": ["red", "dark_red"],
      "percentage": 57.8,
      "individual": {"red": 45.5, "dark_red": 12.3}
    },
    "blue_tones": {
      "colors": ["blue"],
      "percentage": 30.2,
      "individual": {"blue": 30.2}
    }
  }
}
// ปัญหา: เปอร์เซ็นต์รวม > 100%
```

### หลังแก้ไข (New Structure)

```json
{
  "detailed_colors": {
    "red": 60.0,
    "blue": 40.0
  },
  "color_groups": {
    "red_tones": 60.0,
    "blue_tones": 40.0
  },
  "primary_detailed_color": "red",
  "primary_color_group": "red_tones"
}
// เปอร์เซ็นต์รวม = 100% พอดี
```

---

## Database Schema

### ตาราง detections

| Column | Type | คำอธิบาย |
|---|---|---|
| id | UUID | Primary Key |
| track_id | INT | ID สำหรับ tracking |
| timestamp | TIMESTAMP | เวลาที่บันทึก |
| camera_id | VARCHAR(50) | รหัสกล้อง |
| image_path | TEXT | ที่อยู่รูปภาพ |
| clothing_category | VARCHAR(50) | ประเภทเสื้อผ้า |
| class_name | VARCHAR(100) | ชื่อ class |
| detailed_colors | JSONB | สีละเอียด |
| color_groups | JSONB | กลุ่มสี |
| primary_detailed_color | VARCHAR(50) | สีหลัก |
| primary_color_group | VARCHAR(50) | กลุ่มสีหลัก |
| clothes | JSONB | รายการเสื้อผ้า |
| bbox | JSONB | Bounding box |
| video_time_offset | DOUBLE | เวลาในวิดีโอ |
| video_id | TEXT | รหัสวิดีโอ |
| embedding | JSONB | Re-ID embedding |

### Index ที่สร้าง

```sql
CREATE INDEX idx_detailed_colors ON detections USING gin (detailed_colors);
CREATE INDEX idx_color_groups ON detections USING gin (color_groups);
CREATE INDEX idx_primary_detailed_color ON detections (primary_detailed_color);
CREATE INDEX idx_primary_color_group ON detections (primary_color_group);
```

---

## การใช้งาน (Usage)

### 1. วิเคราะห์สีจากรูปภาพ

```python
from src.ai.color_system import (
    analyze_detailed_colors,
    get_color_groups,
    get_primary_detailed_color,
    get_primary_color_group
)

# วิเคราะห์สี
image = cv2.imread("person.jpg")
detailed_colors = analyze_detailed_colors(image)

# จัดกลุ่มสี
color_groups = get_color_groups(detailed_colors)

# หาสีหลัก
primary_color = get_primary_detailed_color(detailed_colors)
primary_group = get_primary_color_group(color_groups)

print(f"สีหลัก: {primary_color}")
print(f"กลุ่มสีหลัก: {primary_group}")
print(f"รายละเอียดสี: {detailed_colors}")
print(f"กลุ่มสี: {color_groups}")
```

### 2. ค้นหาจากฐานข้อมูล

```python
from src.services.database import DatabaseService

db = DatabaseService()

# ค้นหาด้วยสีละเอียด
results = db.search_by_detailed_color("red", limit=10)

# ค้นหาด้วยกลุ่มสี
results = db.search_by_color_group("warm_colors", limit=10)

# ค้นหาด้วยเสื้อผ้า
results = db.search_by_clothes("Shirt", limit=10)
```

### 3. ค้นหาใน Track History

```python
from src.ai.color_system import search_by_color_group, search_by_detailed_color

# ค้นหาคนที่ใส่เสื้อสีแดง
results = search_by_detailed_color(
    track_history, 
    color_name="red", 
    min_percentage=5.0
)

# ค้นหาคนที่ใส่เสื้อสีอุ่น
results = search_by_color_group(
    track_history, 
    group_name="warm_colors", 
    min_percentage=10.0
)
```

---

## Migration

### รัน Migration เพื่อลบ color_profile column

```bash
python migrations/remove_color_profile.py
```

Migration นี้จะ:
1. ตรวจสอบว่า column `color_profile` มีอยู่หรือไม่
2. ลบ column ถ้ามีอยู่
3. ลบ index `idx_color_profile` ถ้ามีอยู่

---

## สรุป

| รายการ | จำนวน/รายละเอียด |
|---|---|
| สีละเอียด | 63 สี |
| กลุ่มสี | 22 กลุ่ม |
| กลุ่มตามโทนสีหลัก | 8 กลุ่ม |
| กลุ่มตามความสว่าง | 3 กลุ่ม |
| กลุ่มตามความสดใส | 3 กลุ่ม |
| กลุ่มตามอุณหภูมิสี | 3 กลุ่ม |
| กลุ่มสำหรับเสื้อผ้า | 5 กลุ่ม |
| ระบบแบ่งกลุ่ม | Competitive Grouping |
| ผลรวมเปอร์เซ็นต์ | 100% พอดี |

---

## ไฟล์ที่เกี่ยวข้อง

- `src/ai/color_system.py` - ระบบวิเคราะห์สีหลัก
- `src/services/database.py` - การจัดเก็บข้อมูล (รวมถึง detection_colors methods)
- `src/services/ai_processor.py` - การประมวลผลวิดีโอ
- `migrations/create_detection_colors_table.py` - Migration สร้างตาราง detection_colors
- `migrations/remove_color_profile.py` - Migration ลบ color_profile column

---

## API การค้นหาสี (Color Search API)

### ค้นหาด้วยโทนสี (Tone Group)
```python
from src.services.database import DatabaseService
db = DatabaseService()
results = db.search_by_tone_group("red_tones", limit=10, min_percentage=10.0)
```

### ค้นหาด้วยอุณหภูมิสี (Temperature)
```python
results = db.search_by_temperature("warm", limit=10)  # warm, cool, neutral
```

### ค้นหาด้วยความสดใส (Vibrancy)
```python
results = db.search_by_vibrancy("vibrant", limit=10)  # vibrant, muted, pastel
```

### ค้นหาด้วยความสว่าง (Brightness)
```python
results = db.search_by_brightness("light", limit=10)  # light, dark, medium
```

### ค้นหาขั้นสูง (Advanced Search)
```python
results = db.search_by_color_advanced(
    tone_groups=["red_tones", "orange_tones"],
    temperature="warm",
    brightness="light",
    vibrancy="vibrant",
    limit=10
)
```
