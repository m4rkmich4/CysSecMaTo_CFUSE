import json
import os

DATA_PATH = os.path.join("files", "rag.json")

def load_documents():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"{DATA_PATH} does not exist.")
    with open(DATA_PATH, "r") as f:
        return json.load(f)

def save_documents(docs):
    with open(DATA_PATH, "w") as f:
        json.dump(docs, f, indent=4)