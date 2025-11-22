# C-FUSE  
**Cybersecurity Framework Unification & Standard Evaluation**

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
```

---

## 2. Python-Umgebung einrichten (Python 3.11 erforderlich)

### macOS / Linux  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE/`):
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Windows (PowerShell)  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE\`):
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Neo4j starten (Docker)
Ausführen im Ordner `CysSecMaTo_CFUSE/docker/`:
```bash
cd docker
docker compose up -d
cd ..
```

Zugriff:

- Neo4j Browser: http://localhost:7474  
- Bolt: `bolt://localhost:7687`  

Standard-Login:

```
User: neo4j
Passwort: CfUsE_2025
```

---

## 4. Ollama installieren und Mistral bereitstellen

### Ollama installieren  
Download-Seite:  
https://ollama.com/download

### Modell `mistral:7b` herunterladen  
Ausführen im Terminal / PowerShell:
```bash
ollama pull mistral:7b
```

### Installation prüfen
```bash
curl http://localhost:11434/api/tags
```

---

# C-FUSE starten

## macOS / Linux  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE/`):
```bash
source .venv/bin/activate
python app.py
```

## Windows  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE\`):
```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

Die Qt-Oberfläche startet automatisch.

---

# Dokumentation

Die fertige Dokumentation liegt unter:

```
CysSecMaTo_CFUSE/build/html/index.html
```

Einfach im Browser öffnen.

---

# Projektstruktur (Kurzüberblick)

```
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
├── source/             # Sphinx-Dokumentation (Quellen)
├── build/html/         # Kompilierte HTML-Dokumentation
├── requirements.txt
└── README.md
```

---

# Hinweise für Reviewer / Gutachter

Zur vollständigen Ausführung:

1. Repository klonen  
2. Python-Umgebung mit **Python 3.11** erstellen  
3. Abhängigkeiten aus `requirements.txt` installieren  
4. Neo4j über Docker starten  
5. Ollama installieren und `mistral:7b` bereitstellen  
6. Anwendung starten:

### macOS / Linux
```bash
source .venv/bin/activate
python3 app.py
```

### Windows
```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```


---
