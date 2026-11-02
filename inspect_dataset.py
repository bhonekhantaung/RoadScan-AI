from pathlib import Path

dataset_path = Path(r"C:\Users\User\OneDrive\Desktop\RoadVision AI\Datasets\RDD_SPLIT")

#print("Dataset exists:", dataset_path.exists())
#print("Dataset location:", dataset_path.resolve())

images = []

for file in dataset_path.rglob("*"):
    if file.suffix.lower() in [".jpg", ".jpeg", ".png"]:
        images.append(file)

print("Total images:", len(images))