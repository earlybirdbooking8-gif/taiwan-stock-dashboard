import os
import sys

# 讓排程與腳本能以絕對路徑導入
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.pipeline import main

if __name__ == "__main__":
    main()
