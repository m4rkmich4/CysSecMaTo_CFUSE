# C-FUSE  
**Cybersecurity Framework Understanding & Semantic Embedding**

C-FUSE ist ein prototypisches, vollständig lokal ausführbares KI-System  
zur Analyse, Bewertung und zum semantischen Mapping von Cybersecurity-Standards.

Das System kombiniert:

- eine Qt-GUI (Start über `app.py`)
- eine Neo4j-Graphdatenbank (Docker)
- eine lokale LLM-Anbindung über Ollama
- das Modell `mistral:7b`
- Python-Module für Import, Embeddings, Retrieval und Mapping
- eine umfangreiche technische Dokumentation (Sphinx)

C-FUSE ist vollständig reproduzierbar auf macOS, Windows und Linux.

---

# Schnellstart

## 1. Repository klonen
```bash
git clone https://github.com/m4rkmich4/CysSecMaTo_CFUSE.git
cd CysSecMaTo_CFUSE

2. Python-Umgebung einrichten (Python 3.11 erforderlich)
macOS / Linux
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
Windows (PowerShell)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

3. Neo4j starten (Docker)
cd docker
docker compose up -d
cd ..
Zugriff:
Neo4j Browser: http://localhost:7474
Bolt: bolt://localhost:7687
Standard-Login (laut docker-compose.yml):
User: neo4j
Passwort: CfUsE_2025

4. Ollama installieren und Mistral bereitstellen
Ollama installieren
Download-Seite:
https://ollama.com/download
Für macOS, Windows und Linux verfügbar.

Modell mistral:7b herunterladen
ollama pull mistral:7b
Installation prüfen
curl http://localhost:11434/api/tags

5. C-FUSE starten
macOS / Linux
source .venv/bin/activate
python app.py
Windows
.\.venv\Scripts\Activate.ps1
python app.py
Die Qt-Oberfläche öffnet sich automatisch.

Dokumentation
Die generierte technische Dokumentation befindet sich unter:
build/html/index.html

Dokumentation neu generieren
macOS / Linux:
make html

Windows:
.\make.bat html

Projektstruktur (Kurzüberblick)
CysSecMaTo_CFUSE/
├── app.py              # Einstiegspunkt der Qt-Anwendung
├── assets/             # Styles, SVGs, Markdown
├── config/             # Prompt-/Konfigurationen
├── db/                 # Neo4j-Connector, Queries, Importlogik
├── docker/             # Docker Compose für Neo4j
├── files/              # Standards, JSON, OSCAL-Daten
├── logic/              # Embeddings, LLM, Mapping, RAG
├── retrieval/          # Fake-RAG-Pipeline
├── ui/                 # Qt Views
├── source/             # Sphinx-Dokumentation
├── build/html/         # Kompilierte HTML-Dokumentation
├── requirements.txt
└── README.md

Hinweise für Reviewer 

Für vollständige Reproduktion:

Repository klonen
Python-Umgebung mit Python 3.11 erstellen
Abhängigkeiten via requirements.txt installieren
Neo4j über Docker starten
Ollama installieren und Modell mistral:7b bereitstellen
Anwendung starten:
python app.py
Damit lässt sich die komplette C-FUSE-Umgebung vollständig lokal ausführen.
