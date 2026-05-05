"""
Test script สำหรับ Database Integration
ทดสอบการบันทึกและค้นหาข้อมูลสีละเอียดและกลุ่มสี
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'services'))
from database import DatabaseService

def test_database_connection():
    """ทดสอบการเชื่อมต่อฐานข้อมูล"""
    print("=" * 50)
    print("TEST 1: Database Connection")
    print("=" * 50)
    try:
        db = DatabaseService()
        print("✅ Database connection successful")
        return db
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def test_insert_detection(db):
    """ทดสอบการบันทึก detection พร้อมข้อมูลสี"""
    print("\n" + "=" * 50)
    print("TEST 2: Insert Detection with Color Data")
    print("=" * 50)
    
    test_data = {
        "detailed_colors": {
            "crimson_red": 35.5,
            "bright_red": 25.0,
            "dark_blue": 15.0,
            "navy_blue": 10.0,
            "pure_black": 14.5
        },
        "color_groups": {
            "red": 60.5,
            "blue": 25.0,
            "neutral": 14.5
        },
        "primary_detailed_color": "crimson_red",
        "primary_color_group": "red",
        "clothes": ["t-shirt", "jeans"],
        "bbox": [100, 150, 300, 450]
    }
    
    try:
        db.insert_detection(
            camera_id="TEST-CAM",
            track_id=999,
            class_name="person",
            image_path="test/path.jpg",
            category="person",
            detailed_colors=test_data["detailed_colors"],
            color_groups=test_data["color_groups"],
            primary_detailed_color=test_data["primary_detailed_color"],
            primary_color_group=test_data["primary_color_group"],
            clothes=test_data["clothes"],
            bbox=test_data["bbox"]
        )
        print("✅ Insert detection successful")
        print(f"   - Detailed colors: {test_data['detailed_colors']}")
        print(f"   - Color groups: {test_data['color_groups']}")
        print(f"   - Primary color: {test_data['primary_detailed_color']}")
        print(f"   - Clothes: {test_data['clothes']}")
        return True
    except Exception as e:
        print(f"❌ Insert detection failed: {e}")
        return False

def test_search_by_detailed_color(db):
    """ทดสอบการค้นหาตามสีละเอียด"""
    print("\n" + "=" * 50)
    print("TEST 3: Search by Detailed Color")
    print("=" * 50)
    
    try:
        results = db.search_by_detailed_color("crimson_red", limit=5)
        print(f"✅ Search by detailed color successful")
        print(f"   - Found {len(results)} results")
        if results:
            print(f"   - First result track_id: {results[0].get('track_id')}")
        return True
    except Exception as e:
        print(f"❌ Search by detailed color failed: {e}")
        return False

def test_search_by_color_group(db):
    """ทดสอบการค้นหาตามกลุ่มสี"""
    print("\n" + "=" * 50)
    print("TEST 4: Search by Color Group")
    print("=" * 50)
    
    try:
        results = db.search_by_color_group("red", limit=5)
        print(f"✅ Search by color group successful")
        print(f"   - Found {len(results)} results")
        if results:
            print(f"   - First result track_id: {results[0].get('track_id')}")
        return True
    except Exception as e:
        print(f"❌ Search by color group failed: {e}")
        return False

def test_search_by_clothes(db):
    """ทดสอบการค้นหาตามเสื้อผ้า"""
    print("\n" + "=" * 50)
    print("TEST 5: Search by Clothes")
    print("=" * 50)
    
    try:
        results = db.search_by_clothes("t-shirt", limit=5)
        print(f"✅ Search by clothes successful")
        print(f"   - Found {len(results)} results")
        if results:
            print(f"   - First result track_id: {results[0].get('track_id')}")
        return True
    except Exception as e:
        print(f"❌ Search by clothes failed: {e}")
        return False

def main():
    """รันทุก test"""
    print("\n" + "=" * 50)
    print("DATABASE INTEGRATION TEST SUITE")
    print("=" * 50)
    
    # Test 1: Connection
    db = test_database_connection()
    if db is None:
        print("\n❌ Cannot proceed with tests - database connection failed")
        return
    
    # Test 2: Insert
    insert_success = test_insert_detection(db)
    
    # Test 3-5: Search functions
    search_detailed_success = test_search_by_detailed_color(db)
    search_group_success = test_search_by_color_group(db)
    search_clothes_success = test_search_by_clothes(db)
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"Database Connection: {'✅ PASS' if db else '❌ FAIL'}")
    print(f"Insert Detection: {'✅ PASS' if insert_success else '❌ FAIL'}")
    print(f"Search by Detailed Color: {'✅ PASS' if search_detailed_success else '❌ FAIL'}")
    print(f"Search by Color Group: {'✅ PASS' if search_group_success else '❌ FAIL'}")
    print(f"Search by Clothes: {'✅ PASS' if search_clothes_success else '❌ FAIL'}")
    
    all_passed = all([db, insert_success, search_detailed_success, search_group_success, search_clothes_success])
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    # Cleanup
    db.close()
    print("\nDatabase connection closed")

if __name__ == "__main__":
    main()
