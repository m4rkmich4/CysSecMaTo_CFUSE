import os
import urllib3
from sentence_transformers import SentenceTransformer
from retrieval.utils import load_documents, save_documents

# HTTPS-Warnungen unterdrücken (falls du sie generell nicht sehen willst)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Projektbasis = Ordner "CysSecMaTo_CFUSE"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_MODEL_PATH = os.path.join(BASE_DIR, "models", "all-MiniLM-L6-v2")


class FakeRetriever:
    def __init__(self):
        try:
            print(f"Lade lokales Modell aus: {LOCAL_MODEL_PATH}")
            self.model = SentenceTransformer(LOCAL_MODEL_PATH)
            print("✅ Lokales Modell erfolgreich geladen.")
        except Exception as e:
            print(f"❌ Fehler beim Laden des lokalen Modells: {e}")
            self.model = None

        self.docs = load_documents()

    def recompute_embeddings(self):
        if self.model is None:
            print("❌ Kein Modell verfügbar. Embeddings können nicht berechnet werden.")
            return

        updated = False
        for doc in self.docs:
            if doc.get("embedding") is None:
                embedding = self.model.encode(doc["description"], convert_to_tensor=False)
                doc["embedding"] = embedding.tolist()
                updated = True

        if updated:
            save_documents(self.docs)
            print("✅ Embeddings wurden neu berechnet und gespeichert.")

    def get_titles(self):
        return [doc["title"] for doc in self.docs]

    def get_documents(self):
        return self.docs

    def get_document_by_title(self, title: str):
        for doc in self.docs:
            if doc.get("title") == title:
                return doc
        return None

    def get_description_by_title(self, title: str):
        doc = self.get_document_by_title(title)
        return doc.get("description", "") if doc else ""
