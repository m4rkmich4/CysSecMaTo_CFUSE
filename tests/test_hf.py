# Dateiname: test_hf.py

import logging
import requests
from transformers import AutoTokenizer
from sentence_transformers import SentenceTransformer
from huggingface_hub.utils import HfHubHTTPError

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# --- VERWENDE DEN VOLLSTÄNDIGEN IDENTIFIER ---
model_name = "sentence-transformers/all-MiniLM-L6-v2"
# --- ---

print(f"\n--- Hugging Face Download Test für Modell: '{model_name}' ---")

# --- Test 1: Tokenizer laden ---
print(f"\n[Test 1] Versuche Tokenizer zu laden: AutoTokenizer.from_pretrained('{model_name}')")
tokenizer_ok = False
try:
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    print(">>> ERFOLG: Tokenizer erfolgreich geladen!")
    tokenizer_ok = True
except (requests.exceptions.ConnectionError, HfHubHTTPError) as e_net:
    print(f">>> FEHLER (Netzwerk): {type(e_net).__name__} - {e_net}")
    logging.error(f"Netzwerkfehler beim Tokenizer-Download für '{model_name}'", exc_info=True)
except OSError as e_os:
    print(f">>> FEHLER (OSError): {e_os}")
    logging.error(f"OSError beim Tokenizer-Download/-Zugriff für '{model_name}'", exc_info=True)
except Exception as e_gen:
    print(f">>> FEHLER (Allgemein): {type(e_gen).__name__} - {e_gen}")
    logging.error(f"Allgemeiner Fehler beim Tokenizer-Laden für '{model_name}'", exc_info=True)

# --- Test 2: SentenceTransformer Modell laden ---
print(f"\n[Test 2] Versuche Modell zu laden: SentenceTransformer('{model_name}')")
model_ok = False
try:
    model = SentenceTransformer(model_name)
    print(">>> ERFOLG: SentenceTransformer-Modell erfolgreich geladen!")
    token_limit = getattr(model, 'max_seq_length', 'Nicht verfügbar')
    print(f"    (Token Limit: {token_limit})") # Erwarten wir jetzt eher 512?
    model_ok = True
except (requests.exceptions.ConnectionError, HfHubHTTPError) as e_net:
    print(f">>> FEHLER (Netzwerk): {type(e_net).__name__} - {e_net}")
    logging.error(f"Netzwerkfehler beim Modell-Download für '{model_name}'", exc_info=True)
except OSError as e_os:
    print(f">>> FEHLER (OSError): {e_os}")
    logging.error(f"OSError beim Modell-Download/-Zugriff für '{model_name}'", exc_info=True)
except Exception as e_gen:
    print(f">>> FEHLER (Allgemein): {type(e_gen).__name__} - {e_gen}")
    logging.error(f"Allgemeiner Fehler beim Modell-Laden für '{model_name}'", exc_info=True)

# --- Zusammenfassung ---
print("\n--- Testergebnis ---")
if tokenizer_ok and model_ok:
    print("✅ Sowohl Tokenizer als auch Modell konnten geladen werden.")
elif tokenizer_ok and not model_ok:
    print("⚠️ Tokenizer geladen, aber das SentenceTransformer-Modell nicht.")
elif not tokenizer_ok and model_ok:
     print("⚠️ SentenceTransformer-Modell geladen, aber der explizite Tokenizer nicht.")
else:
     print("❌ Weder Tokenizer noch Modell konnten erfolgreich geladen werden.")

print("--- Test Ende ---")