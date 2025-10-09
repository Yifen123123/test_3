from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PROMPTS = BASE / "prompts"

def load_prompt(text: str, doc_class: str) -> str:
    core = (PROMPTS / "core_extract.prompt").read_text(encoding="utf-8")
    core = core.replace("{{TEXT}}", text)
    addon_path = PROMPTS / "addons" / f"{doc_class}.prompt"
    addon = ""
    if addon_path.exists():
        addon = "\n\n" + addon_path.read_text(encoding="utf-8")
    return core + addon
