# แผนทดสอบความแม่นยำ Model เสื้อผ้า

## เป้าหมาย

ทดสอบความแม่นยำของ clothing model โดยสรุปผลทั้งจาก:

1. Dataset รูปภาพที่มี label เฉลย
2. Video test 2 ชุด

ผลลัพธ์ต้องตอบได้ว่า:

- model ทายทั้งหมดกี่ครั้ง
- ทายถูกกี่ครั้ง
- ทายผิดกี่ครั้ง
- class จริงนี้ถูกทายเป็น class อื่นกี่ครั้ง
- class อื่นถูกทายผิดมาเป็น class นี้กี่ครั้ง
- แต่ละ class precision / recall / f1 เป็นเท่าไหร่
- confusion matrix เป็นอย่างไร
- เก็บรูปที่ทายผิดไว้ตรวจด้วยตา

## Dataset สำหรับทดสอบ

Dataset path:

```text
C:\Users\pmach\Downloads\clothing_me.v1i.yolov11\train
```

Class definition file:

```text
C:\Users\pmach\Downloads\clothing_me.v1i.yolov11\data.yaml
```

`data.yaml` ระบุ class ทั้งหมด `13` class:

```text
0  long_sleeve_dress
1  long_sleeve_outwear
2  long_sleeve_top
3  short_sleeve_dress
4  short_sleeve_outwear
5  short_sleeve_top
6  shorts
7  skirt
8  sling
9  sling_dress
10 trousers
11 vest
12 vest_dress
```

## Class Mapping

Dataset มี 13 class แต่ model ในระบบใช้ 6 class:

```text
0 short sleeve top
1 long sleeve top
2 short
3 trousers
4 skirt
5 dress
```

ดังนั้นต้อง map class จาก dataset ไปเป็น class ระบบก่อนคำนวณผล

| Dataset Class | Dataset ID | Target Class | System ID |
|---|---:|---|---:|
| `long_sleeve_top` | `2` | `long_sleeve` | `1` |
| `long_sleeve_outwear` | `1` | `long_sleeve` | `1` |
| `short_sleeve_outwear` | `4` | `short_sleeve` | `0` |
| `short_sleeve_top` | `5` | `short_sleeve` | `0` |
| `sling` | `8` | `short_sleeve` | `0` |
| `vest` | `11` | `short_sleeve` | `0` |
| `vest_dress` | `12` | `dress` | `5` |
| `long_sleeve_dress` | `0` | `dress` | `5` |
| `short_sleeve_dress` | `3` | `dress` | `5` |
| `sling_dress` | `9` | `dress` | `5` |
| `skirt` | `7` | `skirt` | `4` |
| `shorts` | `6` | `shorts` | `2` |
| `trousers` | `10` | `trousers` | `3` |

Target class list:

```text
0 short_sleeve
1 long_sleeve
2 shorts
3 trousers
4 skirt
5 dress
```

## Test ชุดที่ 1: Image Dataset Evaluation

### Input

ใช้ dataset:

```text
C:\Users\pmach\Downloads\clothing_me.v1i.yolov11\train
```

โครงสร้าง YOLO dataset ที่คาดไว้:

```text
train/
  images/
    *.jpg
  labels/
    *.txt
```

label format:

```text
class_id x_center y_center width height
```

### วิธีทดสอบ

สำหรับแต่ละ image:

1. อ่าน label เฉลยจาก `.txt`
2. map label เฉลยจาก 13 class เป็น 6 class ของระบบ
3. ส่งภาพเข้า clothing model ของระบบ
4. รับ prediction จาก model
5. map prediction ให้เป็น 6 class เช่นเดียวกัน
6. เทียบ prediction กับ ground truth
7. บันทึกผลถูก/ผิด
8. ถ้าผิด ให้ crop/เก็บรูปไว้ในโฟลเดอร์ wrong predictions

### กรณีภาพมีหลาย object

ถ้าภาพหนึ่งมีหลาย label:

- ต้องนับผลเป็นราย object ไม่ใช่ราย image
- ใช้ bbox จาก label เฉลย crop object ออกมาก่อน
- ส่ง crop เข้า model เพื่อทาย class
- เทียบ class prediction กับ label ของ object นั้น

เหตุผล: model เสื้อผ้าควรถูกวัดจาก object crop แต่ละชิ้น ไม่ใช่ทั้งภาพรวม

## Test ชุดที่ 2: Video Evaluation

มี video test 2 อัน:

1. Video ที่มีเฉพาะ:
   - เสื้อแขนยาว
   - กางเกงขายาว
2. Video ที่มีเฉพาะ:
   - เสื้อแขนสั้น
   - กางเกงขาสั้น

### Expected Class ของแต่ละ video

Video 1:

```text
allowed_classes = long_sleeve, trousers
wrong_if_predicted = short_sleeve, shorts, skirt, dress
```

Video 2:

```text
allowed_classes = short_sleeve, shorts
wrong_if_predicted = long_sleeve, trousers, skirt, dress
```

### วิธีทดสอบ Video

สำหรับแต่ละ frame ที่เลือกทดสอบ:

1. ใช้ YOLO person detector หา person crop
2. ใช้ clothing model ทายเสื้อผ้าจาก person crop
3. map class เป็น 6 class ของระบบ
4. ตรวจว่า prediction อยู่ใน allowed classes ของ video นั้นไหม
5. ถ้าอยู่นอก allowed classes ให้ถือเป็น wrong prediction
6. เก็บ crop ที่ผิดไว้ดูด้วยตา

### Metrics สำหรับ Video

รายงานต่อ video:

- total predictions
- correct predictions
- wrong predictions
- wrong rate
- predictions by class
- unexpected class count
- frame ที่ผิดมากที่สุด
- crop ตัวอย่างที่ผิด

รายงานรวม:

- Video 1 accuracy
- Video 2 accuracy
- overall video accuracy
- class ไหนมักถูกทายผิดใน video ที่ไม่ควรมี class นั้น

## Metrics ที่ต้องรายงาน

### 1. Overall Accuracy

```text
accuracy = correct_predictions / total_predictions
```

### 2. Per-Class Precision

ตอบว่า model ทาย class นี้แล้วถูกจริงกี่ครั้ง

```text
precision(class A) = true_positive_A / all_predicted_A
```

ใช้ดูกรณี:

```text
class อื่นถูกทายผิดมาเป็น class นี้กี่ครั้ง
```

### 3. Per-Class Recall

ตอบว่า class จริงนี้ model จับถูกกี่ครั้ง

```text
recall(class A) = true_positive_A / all_ground_truth_A
```

ใช้ดูกรณี:

```text
class ตัวเองถูกทายเป็น class อื่นกี่ครั้ง
```

### 4. F1 Score

```text
f1 = 2 * precision * recall / (precision + recall)
```

### 5. Confusion Matrix

ตาราง:

```text
ground_truth_class x predicted_class
```

ตัวอย่าง:

| True \ Pred | short_sleeve | long_sleeve | shorts | trousers | skirt | dress |
|---|---:|---:|---:|---:|---:|---:|
| short_sleeve | 0 | 0 | 0 | 0 | 0 | 0 |
| long_sleeve | 0 | 0 | 0 | 0 | 0 | 0 |
| shorts | 0 | 0 | 0 | 0 | 0 | 0 |
| trousers | 0 | 0 | 0 | 0 | 0 | 0 |
| skirt | 0 | 0 | 0 | 0 | 0 | 0 |
| dress | 0 | 0 | 0 | 0 | 0 | 0 |

### 6. False Positive Breakdown

สำหรับแต่ละ predicted class:

```text
model ทายว่าเป็น class นี้ทั้งหมดกี่ครั้ง
ในนั้นจริง ๆ เป็น class อะไรบ้าง
```

ตัวอย่าง:

```text
predicted long_sleeve:
  true long_sleeve: 120
  true short_sleeve: 18
  true dress: 5
```

### 7. False Negative Breakdown

สำหรับแต่ละ true class:

```text
class จริงนี้ทั้งหมดกี่ครั้ง
ถูกทายเป็นอะไรบ้าง
```

ตัวอย่าง:

```text
true long_sleeve:
  predicted long_sleeve: 120
  predicted short_sleeve: 22
  predicted dress: 4
```

### 8. Top-K Accuracy

ถ้า model คืน top-k predictions ได้ ให้รายงาน:

```text
top1 accuracy
top3 accuracy
top5 accuracy
```

เพื่อดูว่า model รู้อยู่แต่เลือกอันดับ 1 ผิด หรือไม่รู้เลย

### 9. Confidence Threshold Comparison

ทดสอบหลาย threshold:

```text
0.25
0.50
0.70
```

สำหรับแต่ละ threshold รายงาน:

- total accepted predictions
- correct
- wrong
- accuracy
- rejected / no prediction count

## Output ที่ต้องสร้าง

แนะนำ output:

```text
track_result/clothing_model_eval/
  summary.md
  metrics.json
  confusion_matrix.csv
  confusion_matrix.png
  per_class_metrics.csv
  false_positive_breakdown.csv
  false_negative_breakdown.csv
  wrong_predictions/
    true_long_sleeve_pred_short_sleeve/
    true_trousers_pred_shorts/
    ...
  video_tests/
    video_1_long_sleeve_trousers/
      summary.md
      wrong_predictions/
    video_2_short_sleeve_shorts/
      summary.md
      wrong_predictions/
```

## Summary ที่ต้องมี

`summary.md` ควรมีหัวข้อ:

1. Dataset path
2. Model path
3. Class mapping
4. Overall accuracy
5. Per-class precision / recall / f1
6. Confusion matrix
7. Top mistakes
8. False positive breakdown
9. False negative breakdown
10. Confidence threshold comparison
11. Video 1 result
12. Video 2 result
13. Wrong prediction crop examples

## Script ที่ควรสร้าง

แนะนำสร้าง:

```text
tests/evaluation/evaluate_clothing_model.py
```

Arguments:

```text
--dataset C:\Users\pmach\Downloads\clothing_me.v1i.yolov11\train
--data-yaml C:\Users\pmach\Downloads\clothing_me.v1i.yolov11\data.yaml
--output-dir track_result/clothing_model_eval
--model models/prepare_dataset.pt
--thresholds 0.25,0.50,0.70
--top-k 5
--video-long path/to/long_sleeve_trousers.mp4
--video-short path/to/short_sleeve_shorts.mp4
```

## เกณฑ์ยอมรับ

- อ่าน class order จาก `data.yaml` ได้
- map 13 dataset classes เป็น 6 system classes ได้ถูกต้อง
- รายงานผลแยกทุก class
- มี confusion matrix
- มี false positive / false negative breakdown
- มี crop รูปที่ทายผิด
- มีผลของ video ทั้ง 2 อัน
- สรุปผลทั้งหมดอยู่ใน `summary.md`
