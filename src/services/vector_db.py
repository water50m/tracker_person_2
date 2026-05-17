"""
Vector Database Service for PostgreSQL with pgvector
Handles embeddings storage and similarity search operations
"""

import psycopg2
import psycopg2.extras
import numpy as np
from typing import List, Optional, Tuple, Dict, Any
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class VectorDB:
    """PostgreSQL pgvector service for embeddings"""
    
    def __init__(self, host='localhost', port=5432, database='mydatabase', 
                 user='admin', password='mypassword'):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.conn = None
        
    def connect(self):
        """เชื่อมต่อกับ database"""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            logger.info(f"Connected to PostgreSQL database: {self.database}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            return False
    
    def disconnect(self):
        """ปิดการเชื่อมต่อ"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def save_embedding(self, detection_id: str, embedding: List[float], 
                      metadata: Optional[Dict] = None) -> str:
        """
        บันทึก embedding ลง database
        
        Args:
            detection_id: ID ของ detection ที่เกี่ยวข้อง
            embedding: List ของ embedding values
            metadata: ข้อมูลเพิ่มเติม (optional)
            
        Returns:
            UUID ของ embedding ที่บันทึก
        """
        if not self.conn:
            if not self.connect():
                raise Exception("Cannot connect to database")
        
        try:
            with self.conn.cursor() as cursor:
                # แปลง embedding เป็น string format สำหรับ pgvector
                embedding_str = f"[{','.join(map(str, embedding))}]"
                
                # สร้าง UUID สำหรับ embedding
                embedding_id = str(uuid.uuid4())
                
                query = """
                INSERT INTO embeddings (id, detection_id, embedding, created_at)
                VALUES (%s, %s, %s::vector, %s)
                """
                
                cursor.execute(query, (embedding_id, detection_id, embedding_str, datetime.now()))
                self.conn.commit()
                
                logger.info(f"Saved embedding {embedding_id} for detection {detection_id}")
                return embedding_id
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to save embedding: {e}")
            raise
    
    def save_embeddings_batch(self, embeddings_data: List[Dict]) -> List[str]:
        """
        บันทึก embeddings หลายรายการพร้อมกัน
        
        Args:
            embeddings_data: List ของ dict ที่มี detection_id และ embedding
            
        Returns:
            List ของ UUIDs ที่บันทึก
        """
        if not self.conn:
            if not self.connect():
                raise Exception("Cannot connect to database")
        
        embedding_ids = []
        
        try:
            with self.conn.cursor() as cursor:
                for data in embeddings_data:
                    detection_id = data['detection_id']
                    embedding = data['embedding']
                    
                    embedding_str = f"[{','.join(map(str, embedding))}]"
                    embedding_id = str(uuid.uuid4())
                    
                    query = """
                    INSERT INTO embeddings (id, detection_id, embedding, created_at)
                    VALUES (%s, %s, %s::vector, %s)
                    """
                    
                    cursor.execute(query, (embedding_id, detection_id, embedding_str, datetime.now()))
                    embedding_ids.append(embedding_id)
                
                self.conn.commit()
                logger.info(f"Saved {len(embedding_ids)} embeddings in batch")
                return embedding_ids
                
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to save batch embeddings: {e}")
            raise
    
    def find_similar_embeddings(self, query_embedding: List[float], 
                                limit: int = 10, threshold: float = 0.8) -> List[Dict]:
        """
        ค้นหา embeddings ที่คล้ายกัน
        
        Args:
            query_embedding: Embedding ที่ต้องการค้นหา
            limit: จำนวนผลลัพธ์สูงสุด
            threshold: ค่าความคล้ายขั้นต่ำ (cosine similarity)
            
        Returns:
            List ของ embeddings ที่คล้ายกัน พร้อม distance
        """
        if not self.conn:
            if not self.connect():
                raise Exception("Cannot connect to database")
        
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                embedding_str = f"[{','.join(map(str, query_embedding))}]"
                
                # ใช้ cosine distance (1 - cosine similarity)
                query = """
                SELECT 
                    id,
                    detection_id,
                    embedding,
                    created_at,
                    (1 - (embedding <=> %s::vector)) AS similarity,
                    (embedding <=> %s::vector) AS cosine_distance
                FROM embeddings
                WHERE (embedding <=> %s::vector) < %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """
                
                # threshold เป็น cosine distance ดังนั้น 1 - threshold = max distance
                max_distance = 1 - threshold
                
                cursor.execute(query, (embedding_str, embedding_str, embedding_str, 
                                     max_distance, embedding_str, limit))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'id': row['id'],
                        'detection_id': row['detection_id'],
                        'embedding': row['embedding'],
                        'similarity': float(row['similarity']),
                        'cosine_distance': float(row['cosine_distance']),
                        'created_at': row['created_at']
                    })
                
                logger.info(f"Found {len(results)} similar embeddings")
                return results
                
        except Exception as e:
            logger.error(f"Failed to find similar embeddings: {e}")
            raise
    
    def get_embedding_by_detection_id(self, detection_id: str) -> Optional[Dict]:
        """
        ดึง embedding ตาม detection_id
        
        Args:
            detection_id: ID ของ detection
            
        Returns:
            Embedding data หรือ None ถ้าไม่พบ
        """
        if not self.conn:
            if not self.connect():
                raise Exception("Cannot connect to database")
        
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                query = """
                SELECT id, detection_id, embedding, created_at
                FROM embeddings
                WHERE detection_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """
                
                cursor.execute(query, (detection_id,))
                row = cursor.fetchone()
                
                if row:
                    return {
                        'id': row['id'],
                        'detection_id': row['detection_id'],
                        'embedding': row['embedding'],
                        'created_at': row['created_at']
                    }
                return None
                
        except Exception as e:
            logger.error(f"Failed to get embedding by detection_id: {e}")
            raise
    
    def delete_embedding(self, embedding_id: str) -> bool:
        """
        ลบ embedding ตาม ID
        
        Args:
            embedding_id: ID ของ embedding
            
        Returns:
            True ถ้าสำเร็จ, False ถ้าไม่พบ
        """
        if not self.conn:
            if not self.connect():
                raise Exception("Cannot connect to database")
        
        try:
            with self.conn.cursor() as cursor:
                query = "DELETE FROM embeddings WHERE id = %s"
                cursor.execute(query, (embedding_id,))
                
                if cursor.rowcount > 0:
                    self.conn.commit()
                    logger.info(f"Deleted embedding {embedding_id}")
                    return True
                else:
                    logger.warning(f"Embedding {embedding_id} not found")
                    return False
                    
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to delete embedding: {e}")
            raise
    
    def get_stats(self) -> Dict:
        """
        ดูสถิติของ embeddings table
        
        Returns:
            Dictionary ของสถิติ
        """
        if not self.conn:
            if not self.connect():
                raise Exception("Cannot connect to database")
        
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # นับ embeddings ทั้งหมด
                cursor.execute("SELECT COUNT(*) as total_embeddings FROM embeddings")
                total = cursor.fetchone()['total_embeddings']
                
                # ดู embeddings ล่าสุด
                cursor.execute("""
                    SELECT created_at 
                    FROM embeddings 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """)
                latest = cursor.fetchone()
                
                return {
                    'total_embeddings': total,
                    'latest_embedding': latest['created_at'] if latest else None
                }
                
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            raise


# สร้าง instance สำหรับใช้งาน
vector_db = VectorDB()

# Helper functions สำหรับใช้งานง่ายๆ
def save_embedding(detection_id: str, embedding: List[float], metadata: Optional[Dict] = None) -> str:
    """บันทึก embedding ง่ายๆ"""
    return vector_db.save_embedding(detection_id, embedding, metadata)

def find_similar(query_embedding: List[float], limit: int = 10, threshold: float = 0.8) -> List[Dict]:
    """ค้นหา embeddings ที่คล้ายกัน"""
    return vector_db.find_similar_embeddings(query_embedding, limit, threshold)

def get_embedding(detection_id: str) -> Optional[Dict]:
    """ดึง embedding ตาม detection_id"""
    return vector_db.get_embedding_by_detection_id(detection_id)
