# src/main.py
import argparse, json
from pathlib import Path
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader

from .router import load_prompt
from .llm_client import chat_ollama_json
from .utils import (
    validate_tw_id, today_fields,
    extract_officer, extract_phone, extract_doc_no, extract_doc_date
)

BASE = Path(__file__).resolve().parents[1]
PROMPTS_DIR = BASE / "prompts" / "addons"

# --- 最小後處理：不再產 note，note 完全交給 add-on prompt ---
def post_validate(payload: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    # class_specific 若被模型回成「字串」，轉回 dict（避免模板 .get 失效）
    cs = payload.get("class_specific")
    if isinstance(cs, str):
        try:
            cs = json.loads(cs)
        except Exception:
            cs = {}
        payload["class_specific"] = cs

    # 身分證檢核（只驗證，不增刪）
    for p in payload.get("targets", []) or []:
        twid = p.get("tw_id")
        p["id_valid"] = bool(twid and validate_tw_id(twid))

    # officer / phone / doc_no / doc_date 的輕量 fallback（有就不覆蓋）
    if not payload.get("officer_role") and not payload.get("officer_name"):
        role, name = extract_officer(raw_text); payload["officer_role"] = role; payload["officer_name"] = name
    if not payload.get("contact_phone"):
        phone = extract_phone(raw_text)
        if phone: payload["contact_phone"] = phone
    if not payload.get("doc_no"):
        doc_no = extract_doc_no(raw_text)
        if doc_no: payload["doc_no"] = doc_no
    if not payload.get("doc_date"):
        dd = extract_doc_date(raw_text)
        if dd: payload["doc_date"] = dd

    return payload

def render_reply(payload: Dict[str, Any]) -> str:
    """把資料丟進模板。確保 class_specific / policies 一定有傳入。"""
    from datetime import datetime
    env = Environment(loader=FileSystemLoader(str(BASE / "templates")),
                      trim_blocks=True, lstrip_blocks=True)
    tpl = env.get_template("reply_letter.txt.j2")

    # 日期顯示：優先公文的 doc_date，沒有才用今天
    today = today_fields()
    iso = payload.get("doc_date") or today["today_iso"]
    try:
        dt = datetime.fromisoformat(iso)
        display = {
            "display_yyyy": f"{dt.year}", "display_mm": f"{dt.month:02d}",
            "display_dd": f"{dt.day:02d}", "display_iso": dt.strftime("%Y-%m-%d"),
        }
    except Exception:
        display = {
            "display_yyyy": today["today_yyyy"], "display_mm": today["today_mm"],
            "display_dd": today["today_dd"], "display_iso": today["today_iso"],
        }

    return tpl.render(
        agency=payload.get("agency"),
        reference_date=payload.get("reference_date"),
        doc_no=payload.get("doc_no"),
        officer_role=payload.get("officer_role"),
        officer_name=payload.get("officer_name"),
        contact_phone=payload.get("contact_phone"),
        targets=payload.get("targets", []),
        policies=payload.get("policies", []),
        class_specific=payload.get("class_specific", {}),  # ← 關鍵：帶進模板
        display_yyyy=display["display_yyyy"],
        display_mm=display["display_mm"],
        display_dd=display["display_dd"],
        display_iso=display["display_iso"],
    )

def infer_class_from_path(p: Path) -> str:
    return p.parent.name  # 預期 data/<類別>/<檔案>.txt

def main():
    ap = argparse.ArgumentParser(description="Gov letter → LLM extract → reply text")
    ap.add_argument("--data-dir", default=str(BASE / "data"))
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--out-dir", default=str(BASE / "outputs"))
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    txt_files = list(data_dir.glob("*/*.txt"))
    if not txt_files:
        print(f"[WARN] 在 {data_dir} 未找到 txt（預期：data/<類別>/<檔名>.txt）"); return

    for fp in txt_files:
        doc_class = infer_class_from_path(fp)
        raw_text = fp.read_text(encoding="utf-8", errors="ignore")
        prompt = load_prompt(raw_text, doc_class=doc_class)

        print(f"[INFO] 處理：{fp.name}（類別：{doc_class}）…")
        payload = chat_ollama_json(prompt, model=args.model, temperature=0.1)

        payload = post_validate(payload, raw_text)
        reply = render_reply(payload)

        (out_dir / f"{fp.stem}.reply.txt").write_text(reply, encoding="utf-8")
        print(f"[OK] 已輸出：{fp.stem}.reply.txt")

if __name__ == "__main__":
    main()
