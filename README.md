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

C-FUSE ist vollständig reproduzierbar auf macOS, Windows und Linux.

---

# Schnellstart

## 1. Repository klonen
Ausführen im gewünschten Zielordner (macOS, Linux, Windows gleichermaßen):

```bash
git clone https://github.com/m4rkmich4/CysSecMaTo_CFUSE.git
cd CysSecMaTo_CFUSE
```

---

## 2. Python-Umgebung einrichten (Python 3.11 erforderlich)

Stellen Sie sicher, dass Python 3.11 installiert ist.  
Empfohlen: Offizieller Download von https://www.python.org/downloads/

### 2.1 macOS / Linux  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE/`):

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.2 Windows (PowerShell)  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE\`):
teras-Paket nicht vergessen sonst läuft sentence-transformers unter windows nicht.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
pip install tf-keras
```

### 2.3 Windows (Eingabeaufforderung / CMD)  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE\`):

```cmd
py -3.11 -m venv .venv
.\.venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
```

Hinweis: Unter Windows sollte bei der Git-Installation sichergestellt sein,  
dass Git sowohl in PowerShell als auch in der Eingabeaufforderung (CMD) verfügbar ist.

---

## 3. Neo4j starten (Docker)

Voraussetzung: Docker / Docker Desktop ist installiert und lauffähig.

Ausführen im Ordner `CysSecMaTo_CFUSE/docker/` (macOS, Linux, Windows):

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

Es wird empfohlen, das Passwort beim ersten Login im Neo4j-Browser zu ändern.

---

## 4. Ollama installieren und Mistral bereitstellen

### 4.1 Ollama installieren  
Download-Seite:  
https://ollama.com/download

Ollama installieren und den Dienst starten.

### 4.2 Modell `mistral:7b` herunterladen  
Ausführen im Terminal / PowerShell / CMD:

```bash
ollama pull mistral:7b
```

### 4.3 Installation prüfen

```bash
curl http://localhost:11434/api/tags
```

Wenn `mistral:7b` in der Ausgabe erscheint, ist das Modell bereit.

---

## 5. Lokale Embedding-Modelle herunterladen (Pfad: `./models/`)

Die Anwendung lädt Embedding-Modelle ausschließlich **lokal** aus dem Ordner `models/`.  
Es erfolgt **kein automatischer Download** zur Laufzeit.  
Folgende Modelle werden erwartet:

- `models/all-MiniLM-L6-v2`
- `models/all-mpnet-base-v2`

Zum Herunterladen wird **Git** und **Git LFS (Large File Storage)** benötigt.

### 5.1 Git installieren (macOS, Linux, Windows)

1. Git-Installer herunterladen:  
   https://git-scm.com/downloads

2. Betriebssystemspezifisch installieren:

   - **Windows**:  
     - Installer ausführen  
     - Während der Installation sicherstellen, dass Git zur PATH-Umgebungsvariable hinzugefügt wird  
       (Optionen wie „Git from the command line and also from 3rd-party software“ auswählen).
   - **macOS**:  
     - Entweder den macOS-Installer von git-scm.com verwenden  
     - oder über die Xcode Command Line Tools installieren:  
       ```bash
       xcode-select --install
       ```
   - **Linux (Debian/Ubuntu-Beispiel)**:  
       ```bash
       sudo apt-get update
       sudo apt-get install git
       ```

Andere Distributionen können den jeweils passenden Paketmanager verwenden  
(z. B. `dnf`, `zypper`, `pacman`).

### 5.2 Git LFS installieren

Git LFS wird benötigt, um große Modell-Dateien korrekt zu verwalten.

1. Git LFS-Installer herunterladen:  
   https://git-lfs.com/

2. Installation durchführen entsprechend dem Betriebssystem.

3. Anschließend Git LFS global initialisieren (einmalig):

   ```bash
   git lfs install
   ```

Dieser Befehl kann in macOS-Terminal, Linux-Shell, Windows PowerShell oder CMD ausgeführt werden.

### 5.3 Modelle in den Ordner `models` klonen

Ausführen im Projektverzeichnis `CysSecMaTo_CFUSE/` (macOS, Linux, Windows):

```bash
cd models
```

Nun die beiden Sentence Transformer-Modelle klonen  
(diese Befehle sind für alle Betriebssysteme gleich, sofern Git und Git LFS installiert sind):

```bash
git clone https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
git clone https://huggingface.co/sentence-transformers/all-mpnet-base-v2
```

Nach erfolgreichem Klonen sollten folgende Pfade existieren:

- `CysSecMaTo_CFUSE/models/all-MiniLM-L6-v2`
- `CysSecMaTo_CFUSE/models/all-mpnet-base-v2`

Anschließend wieder zurück ins Projektverzeichnis wechseln:

```bash
cd ..
```

Ab diesem Zeitpunkt können die Embedding-Funktionen der Anwendung vollständig offline arbeiten,  
sofern keine weiteren externen Modelle verwendet werden.

---

# C-FUSE starten

## 6. Anwendung starten

### 6.1 macOS / Linux  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE/`):

```bash
source .venv/bin/activate
python app.py
```

### 6.2 Windows (PowerShell)  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE\`):

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

### 6.3 Windows (Eingabeaufforderung / CMD)  
Ausführen im Projektverzeichnis (`CysSecMaTo_CFUSE\`):

```cmd
.\.venv\Scriptsctivate.bat
python app.py
```

Die Qt-Oberfläche startet automatisch.

---

# Dokumentation

Die fertige Dokumentation liegt unter:

```text
CysSecMaTo_CFUSE/build/html/index.html
```

Einfach im Browser öffnen.

---

# Projektstruktur (Kurzüberblick)

```text
CysSecMaTo_CFUSE/
├── app.py              # Einstiegspunkt der Qt-Anwendung
├── assets/             # Styles, SVGs, Markdown
├── config/             # Prompt-/Konfigurationen
├── db/                 # Neo4j-Connector, Queries, Importlogik
├── docker/             # Docker Compose für Neo4j
├── files/              # Standards, JSON, OSCAL-Daten
├── logic/              # Embeddings, LLM, Mapping, RAG
├── models/             # Lokale Embedding-Modelle (all-MiniLM-L6-v2, all-mpnet-base-v2)
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
6. Embedding-Modelle in `./models` herunterladen (Git + Git LFS, siehe Abschnitt 5)  
7. Anwendung starten

## Startbefehle im Überblick

### macOS / Linux

```bash
source .venv/bin/activate
python app.py
```

### Windows (PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

### Windows (Eingabeaufforderung / CMD)

```cmd
.\.venv\Scripts\activate.bat
python app.py
```

Damit ist C-FUSE vollständig lokal und reproduzierbar ausführbar.
