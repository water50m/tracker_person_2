# YOLO11s person_conf 0.45 full pipeline summary

## Config
- Source video: `E:\ALL_CODE\my-project\temp_videos\YTDown.com_YouTube_LIVE-footage-Bangkok-Earthquake-28-03-25_Media_I5jaBKWPy6g_001_1080p.mp4`
- Detector: `E:\ALL_CODE\my-project\yolo11s.pt`
- Clothing model: `E:\ALL_CODE\my-project\models\prepare_dataset.pt`
- Device: `cuda`
- Person conf: `0.45`
- Clothing conf: `0.25`
- IoU dedupe threshold: `0.5`
- Re-ID: clothing class + color only, threshold `0.7`, confirm `10/30`

## Result
- Processed frames: `3600`
- Output FPS: `2.1464`
- Person rows before IoU dedupe: `11941`
- Person rows after IoU dedupe: `11871`
- Suppressed by IoU dedupe: `70`
- New ByteTrack IDs after IoU dedupe: `243`
- Display IDs after Re-ID: `234`
- Recovered track events: `9`
- Recovered person rows: `2616`
- Final outfit voted IDs: `234`
- SQLite DB: `E:\ALL_CODE\my-project\track_result\bangkok_earthquake_predict_2min_yolo11s_pc045_63color\prediction_results.sqlite`
- Images dir: `E:\ALL_CODE\my-project\track_result\bangkok_earthquake_predict_2min_yolo11s_pc045_63color\images`
- Viewer: `E:\ALL_CODE\my-project\track_result\bangkok_earthquake_predict_2min_yolo11s_pc045_63color\video_prediction_viewer.html`

## Person Conf 0.45 vs Baseline 0.25
- Baseline file: `E:\ALL_CODE\my-project\track_result\bangkok_earthquake_predict_2min_yolo11s\prediction_results.json`
- Baseline person rows after IoU: `17389` -> new `11871` ลดลง `5518` (`31.73%`)
- Baseline unique IDs after IoU: `432` -> new `243` ลดลง `189` (`43.75%`)

## Re-ID Summary
- ByteTrack new ID count: `243`
- System recovered count: `9`
- Recovered person rows: `2616`
- Color feature source: `detailed_colors_63`

## Final Outfit Votes
- ID `1`: `short_sleeve, shorts` (frames `0-246`, observations `239`)
- ID `2`: `long_sleeve, trousers` (frames `0-1412`, observations `1275`)
- ID `3`: `short_sleeve, shorts` (frames `0-198`, observations `149`)
- ID `5`: `long_sleeve, trousers` (frames `97-98`, observations `2`)
- ID `6`: `short_sleeve, trousers` (frames `110-116`, observations `7`)
- ID `7`: `short_sleeve, shorts` (frames `183-186`, observations `2`)
- ID `9`: `short_sleeve, shorts` (frames `200-338`, observations `66`)
- ID `12`: `long_sleeve, shorts` (frames `208-208`, observations `1`)
- ID `14`: `short_sleeve, shorts` (frames `226-233`, observations `8`)
- ID `16`: `trousers` (frames `241-241`, observations `1`)
- ID `17`: `short_sleeve, trousers` (frames `252-252`, observations `1`)
- ID `19`: `short_sleeve, shorts` (frames `281-283`, observations `2`)
- ID `21`: `short_sleeve, shorts` (frames `289-716`, observations `418`)
- ID `23`: `long_sleeve, trousers` (frames `305-309`, observations `5`)
- ID `24`: `long_sleeve, trousers` (frames `321-331`, observations `11`)
- ID `25`: `short_sleeve, trousers` (frames `309-532`, observations `158`)
- ID `29`: `long_sleeve` (frames `342-343`, observations `2`)
- ID `31`: `long_sleeve` (frames `345-345`, observations `1`)
- ID `34`: `long_sleeve` (frames `348-348`, observations `1`)
- ID `38`: `long_sleeve, trousers` (frames `354-356`, observations `3`)
- ID `39`: `long_sleeve, trousers` (frames `358-358`, observations `1`)
- ID `40`: `long_sleeve` (frames `360-360`, observations `1`)
- ID `42`: `long_sleeve` (frames `363-364`, observations `2`)
- ID `43`: `long_sleeve` (frames `370-370`, observations `1`)
- ID `44`: `long_sleeve` (frames `372-372`, observations `1`)
- ID `46`: `long_sleeve` (frames `375-375`, observations `1`)
- ID `47`: `long_sleeve` (frames `377-377`, observations `1`)
- ID `48`: `long_sleeve` (frames `379-380`, observations `2`)
- ID `49`: `long_sleeve` (frames `382-382`, observations `1`)
- ID `51`: `long_sleeve` (frames `384-387`, observations `4`)
- ID `52`: `shorts` (frames `384-390`, observations `7`)
- ID `53`: `long_sleeve` (frames `389-389`, observations `1`)
- ID `54`: `long_sleeve` (frames `391-392`, observations `2`)
- ID `56`: `long_sleeve` (frames `396-401`, observations `5`)
- ID `58`: `short_sleeve, shorts` (frames `399-613`, observations `209`)
- ID `60`: `long_sleeve, shorts` (frames `415-470`, observations `31`)
- ID `61`: `long_sleeve, trousers` (frames `470-791`, observations `179`)
- ID `63`: `short_sleeve, shorts` (frames `504-555`, observations `38`)
- ID `64`: `long_sleeve, shorts` (frames `517-517`, observations `1`)
- ID `68`: `long_sleeve` (frames `606-608`, observations `3`)
- ID `69`: `short_sleeve, shorts` (frames `612-801`, observations `184`)
- ID `70`: `long_sleeve, trousers` (frames `700-763`, observations `62`)
- ID `72`: `shorts` (frames `724-724`, observations `1`)
- ID `73`: `long_sleeve` (frames `734-734`, observations `1`)
- ID `76`: `unknown` (frames `779-779`, observations `1`)
- ID `77`: `long_sleeve, trousers` (frames `781-781`, observations `1`)
- ID `78`: `long_sleeve, trousers` (frames `788-831`, observations `15`)
- ID `79`: `long_sleeve` (frames `791-791`, observations `1`)
- ID `82`: `short_sleeve, trousers` (frames `812-875`, observations `62`)
- ID `83`: `short_sleeve, shorts` (frames `826-913`, observations `56`)
- ID `84`: `long_sleeve, trousers` (frames `833-851`, observations `19`)
- ID `86`: `long_sleeve, shorts` (frames `892-1189`, observations `285`)
- ID `87`: `long_sleeve, trousers` (frames `906-915`, observations `8`)
- ID `88`: `long_sleeve, trousers` (frames `921-959`, observations `39`)
- ID `89`: `long_sleeve, trousers` (frames `946-1036`, observations `56`)
- ID `90`: `long_sleeve, trousers` (frames `958-1133`, observations `176`)
- ID `92`: `long_sleeve, trousers` (frames `984-1036`, observations `16`)
- ID `93`: `long_sleeve, trousers` (frames `1041-1120`, observations `29`)
- ID `98`: `long_sleeve, trousers` (frames `1174-1270`, observations `84`)
- ID `100`: `short_sleeve, skirt` (frames `1227-1233`, observations `7`)
- ID `101`: `trousers` (frames `1274-1275`, observations `2`)
- ID `102`: `long_sleeve, trousers` (frames `1308-1386`, observations `79`)
- ID `103`: `short_sleeve, trousers` (frames `1393-1399`, observations `7`)
- ID `105`: `long_sleeve, trousers` (frames `1446-1457`, observations `10`)
- ID `107`: `short_sleeve` (frames `1500-1504`, observations `5`)
- ID `108`: `short_sleeve` (frames `1500-1500`, observations `1`)
- ID `109`: `short_sleeve` (frames `1506-1506`, observations `1`)
- ID `110`: `long_sleeve` (frames `1510-1510`, observations `1`)
- ID `111`: `long_sleeve, trousers` (frames `1512-1512`, observations `1`)
- ID `112`: `short_sleeve, shorts` (frames `1512-1533`, observations `21`)
- ID `113`: `short_sleeve, trousers` (frames `1514-1521`, observations `7`)
- ID `117`: `short_sleeve, shorts` (frames `1525-1591`, observations `61`)
- ID `119`: `short_sleeve, shorts` (frames `1535-1535`, observations `1`)
- ID `120`: `short_sleeve` (frames `1537-1539`, observations `3`)
- ID `121`: `short_sleeve` (frames `1541-1541`, observations `1`)
- ID `122`: `short_sleeve, trousers` (frames `1543-1591`, observations `49`)
- ID `126`: `short_sleeve, trousers` (frames `1631-2600`, observations `897`)
- ID `127`: `unknown` (frames `1676-1678`, observations `3`)
- ID `128`: `short_sleeve, trousers` (frames `1765-1933`, observations `115`)
- ID `129`: `long_sleeve, trousers` (frames `1767-2033`, observations `145`)
- ...อีก `154` IDs ดูเต็มใน `prediction_results.json` metadata.final_outfit_votes

## Result Clothing Counts
- short_sleeve: `6624`
- long_sleeve: `4680`
- shorts: `3848`
- trousers: `6526`
- skirt: `116`
- dress: `249`

## Raw Clothing Counts
- short_sleeve: `7639`
- long_sleeve: `5630`
- shorts: `4470`
- trousers: `7038`
- skirt: `184`
- dress: `265`

## Timings
- clip_cut: `141.731832` sec, count `1`, avg `141731.8323` ms
- clothing_postprocess: `754.649125` sec, count `11941`, avg `63.1982` ms
- clothing_predict: `307.55106` sec, count `11941`, avg `25.7559` ms
- detailed_color_analysis: `728.507304` sec, count `22169`, avg `32.8615` ms
- file_write: `31.147902` sec, count `1`, avg `31147.9024` ms
- final_outfit_vote: `0.207413` sec, count `1`, avg `207.4131` ms
- image_save: `99.047443` sec, count `11871`, avg `8.3436` ms
- iou_dedupe: `0.202276` sec, count `3600`, avg `0.0562` ms
- model_load: `1.152288` sec, count `1`, avg `1152.2884` ms
- person_detect_track: `297.336297` sec, count `3600`, avg `82.5934` ms
- reid_apply: `0.376622` sec, count `1`, avg `376.6216` ms
- sqlite_save: `4.067803` sec, count `1`, avg `4067.8026` ms
- total_without_file_db_write: `1642.012025` sec, count `1`, avg `1642012.0248` ms
- untracked_person_boxes_skipped: `0.0` sec, count `26`, avg `0.0` ms
