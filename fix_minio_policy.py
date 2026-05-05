#!/usr/bin/env python3
"""
Fix MinIO bucket policy to allow public read access
"""

from minio import Minio
import os
from dotenv import load_dotenv

load_dotenv()

# MinIO configuration
endpoint = os.getenv("MINIO_ENDPOINT", "myserver:9000")
access_key = os.getenv("MINIO_ACCESS_KEY", "admin")
secret_key = os.getenv("MINIO_SECRET_KEY", "password1234")
bucket_name = os.getenv("MINIO_BUCKET", "cctv-images")

# Public read-only policy
public_read_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": "*"},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
        }
    ]
}

def fix_bucket_policy():
    try:
        # Connect to MinIO
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False  # http
        )
        
        print(f"🔧 Connecting to MinIO at {endpoint}")
        
        # Check if bucket exists
        if not client.bucket_exists(bucket_name):
            print(f"❌ Bucket '{bucket_name}' does not exist")
            return False
            
        print(f"✅ Bucket '{bucket_name}' exists")
        
        # Set public read policy
        import json
        policy_json = json.dumps(public_read_policy)
        
        client.set_bucket_policy(bucket_name, policy_json)
        print(f"✅ Set public read policy for bucket '{bucket_name}'")
        
        # Verify policy
        current_policy = client.get_bucket_policy(bucket_name)
        print(f"📋 Current policy: {current_policy}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = fix_bucket_policy()
    if success:
        print("\n🎉 Bucket policy fixed! Try accessing the image URL again.")
    else:
        print("\n💥 Failed to fix bucket policy")
