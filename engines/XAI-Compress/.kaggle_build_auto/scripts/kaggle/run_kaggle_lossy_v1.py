import os,runpy
from pathlib import Path
os.environ["XAI_TRAINING_FAMILY"]="lossy_v1"
runpy.run_path(str(Path(__file__).with_name("run_kaggle_training.py")),run_name="__main__")
