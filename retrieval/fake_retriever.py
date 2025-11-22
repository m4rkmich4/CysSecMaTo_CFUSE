from sentence_transformers import SentenceTransformer
from retrieval.utils import load_documents, save_documents

class FakeRetriever:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.docs = load_documents()

    def recompute_embeddings(self):
        """If embeddings are not yet present, generate and save them.""" # Translated from "Falls noch keine Embeddings vorhanden sind, generiere und speichere sie."
        updated = False
        for doc in self.docs:
            if doc.get("embedding") is None:
                # Converts ndarray to a JSON-compatible list # Translated from "Wandelt ndarray in JSON-kompatible Liste um"
                embedding = self.model.encode(doc["description"], convert_to_tensor=False)
                doc["embedding"] = embedding.tolist()
                updated = True

        if updated:
            save_documents(self.docs)

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