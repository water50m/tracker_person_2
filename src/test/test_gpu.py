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
    print("❌ CUDA is NOT available. AI is running on CPU.")