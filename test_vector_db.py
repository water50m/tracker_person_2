"""
Test script for Vector Database Service
ทดสอบการทำงานของ pgvector functions
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.services.vector_db import VectorDB, save_embedding, find_similar, get_embedding
import numpy as np
import uuid

def test_vector_db():
    """ทดสอบฟังก์ชันต่างๆ ของ VectorDB"""
    
    print("=== Testing Vector Database ===")
    
    # สร้าง instance
    db = VectorDB()
    
    # ทดสอบการเชื่อมต่อ
    print("1. Testing connection...")
    if db.connect():
        print("✅ Connected successfully")
    else:
        print("❌ Connection failed")
        return
    
    try:
        # ทดสองการบันทึก embedding
        print("\n2. Testing save embedding...")
        detection_id = str(uuid.uuid4())
        test_embedding = np.random.rand(512).tolist()  # สร้าง random embedding 512 dims
        
        embedding_id = db.save_embedding(detection_id, test_embedding)
        print(f"✅ Saved embedding: {embedding_id}")
        
        # บันทึกอีก 2-3 embeddings สำหรับทดสอบการค้นหา
        print("\n3. Creating more test embeddings...")
        for i in range(3):
            det_id = str(uuid.uuid4())
            # สร้าง embedding ที่คล้ายกับตัวแรก
            similar_embedding = test_embedding + np.random.normal(0, 0.1, 512).tolist()
            db.save_embedding(det_id, similar_embedding)
        
        print("✅ Created test embeddings")
        
        # ทดสอบการดึง embedding ตาม detection_id
        print("\n4. Testing get embedding by detection_id...")
        retrieved = db.get_embedding_by_detection_id(detection_id)
        if retrieved:
            print(f"✅ Retrieved embedding: {retrieved['id']}")
        else:
            print("❌ Failed to retrieve embedding")
        
        # ทดสอบการค้นหา embeddings ที่คล้ายกัน
        print("\n5. Testing similar embeddings search...")
        similar_results = db.find_similar_embeddings(test_embedding, limit=5, threshold=0.5)
        print(f"✅ Found {len(similar_results)} similar embeddings")
        
        for i, result in enumerate(similar_results[:3]):  # แสดง 3 อันแรก
            print(f"   Result {i+1}: similarity={result['similarity']:.3f}")
        
        # ทดสอบ batch insert
        print("\n6. Testing batch insert...")
        batch_data = []
        for i in range(5):
            batch_data.append({
                'detection_id': str(uuid.uuid4()),
                'embedding': np.random.rand(512).tolist()
            })
        
        batch_ids = db.save_embeddings_batch(batch_data)
        print(f"✅ Batch inserted {len(batch_ids)} embeddings")
        
        # ทดสอบสถิติ
        print("\n7. Testing stats...")
        stats = db.get_stats()
        print(f"✅ Total embeddings: {stats['total_embeddings']}")
        if stats['latest_embedding']:
            print(f"   Latest: {stats['latest_embedding']}")
        
        # ทดสอบ helper functions
        print("\n8. Testing helper functions...")
        test_det_id = str(uuid.uuid4())
        test_emb = np.random.rand(512).tolist()
        
        helper_id = save_embedding(test_det_id, test_emb)
        print(f"✅ Helper save_embedding: {helper_id}")
        
        helper_results = find_similar(test_emb, limit=3)
        print(f"✅ Helper find_similar: {len(helper_results)} results")
        
        helper_get = get_embedding(test_det_id)
        if helper_get:
            print(f"✅ Helper get_embedding: {helper_get['id']}")
        
        print("\n=== All tests completed successfully! ===")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.disconnect()

if __name__ == "__main__":
    test_vector_db()
