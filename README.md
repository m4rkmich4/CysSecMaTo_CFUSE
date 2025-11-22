# C-FUSE  
**Cybersecurity Framework Understanding & Semantic Embedding**

C-FUSE ist ein prototypisches, vollständig lokal ausführbares KI-System  
zur Analyse, Bewertung und zum semantischen Mapping von Cybersecurity-Standards.

Der Prototyp kombiniert:

- eine **Qt-GUI** (Start über `app.py`)
- eine **Neo4j-Graphdatenbank** (Docker)
- **Ollama + Mistral** als lokales LLM
- Python-basierte Module für Import, Embeddings, Retrieval und Mapping
- eine vollständige technische Dokumentation (Sphinx)

Das System ist vollständig reproduzierbar auf macOS, Windows und Linux.

---

# 🚀 Schnellstart

## **1. Repository klonen**
```bash
git clone https://github.com/m4rkmich4/CysSecMaTo_CFUSE.git
cd CysSecMaTo_CFUSE


2. Python-Umgebung einrichten (Python 3.11 erforderlich)
macOS / Linux
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
