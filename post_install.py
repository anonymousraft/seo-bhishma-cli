import subprocess
import sys

def install_spacy_model():
    try:
        import spacy
        spacy.load('en_core_web_sm')
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "spacy"])
        import spacy
    except OSError:
        subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])

if __name__ == "__main__":
    install_spacy_model()
