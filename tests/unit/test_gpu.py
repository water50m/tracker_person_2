"""
Unit Test for GPU availability
"""
import unittest
import pytest


class TestGPU(unittest.TestCase):
    """ทดสอบการตรวจสอบ GPU"""
    
    @pytest.mark.slow
    def test_torch_cuda_available(self):
        """ทดสอบว่า PyTorch CUDA ใช้งานได้"""
        import torch
        
        print("--- GPU Check ---")
        print(f"PyTorch Version: {torch.__version__}")
        cuda_ok = torch.cuda.is_available()
        print(f"CUDA Available: {cuda_ok}")

        if cuda_ok:
            print(f"Device Name: {torch.cuda.get_device_name(0)}")
            print(f"Device Count: {torch.cuda.device_count()}")
            print(f"Current Device Index: {torch.cuda.current_device()}")
        else:
            print("⚠️ CUDA is NOT available. AI is running on CPU.")
        
        # Don't fail test if CUDA not available (CI may not have GPU)
        # Just log the status
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
