import argparse
import json
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

# 針對特定類別，若模型沒給 note 就補一句預設（你可自行擴充）
DEFAULT_NOTES = {
    "保單查詢": "本案為保單查詢註記",
    "保單查詢＋註記": "本案為保單查詢註記",
}

def _has_addon(doc_class: str) -> bool:
    return (PROMPTS_DIR / f"{doc_class}.prompt").exists()

def _ensure_class_specific_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    """把 class_specific 轉成 dict（模型有時會回字串）。"""
    cs = payload.get("class_specific")
    if cs is None:
        cs = {}
    elif isinstance(cs, str):
        try:
            cs = json.loads(cs)
            if not isinstance(cs, dict):
                cs = {}
        except Exception:
            cs = {}
    payload["class_specific"] = cs
    return payload

def _best_effort_note(payload: Dict[str, Any], doc_class: str) -> None:
    """
    若 add-on 存在但模型沒給 note，兜底產生一句 note。
    盡量利用已抽到的 query_mode / policy_nos / insured_names / subtypes。
    """
    cs = payload.get("class_specific") or {}
    note = cs.get("note")

    if note:
        return  # 已有 note 無須處理

    # 只有當該類別真的有 add-on，我們才兜底
    if not _has_addon(doc_class):
        return

    # 嘗試用模型已有欄位組一句話
    qm = (cs.get("query_mode") or "").strip()
    pnos = cs.get("policy_nos") or []
    inames = cs.get("insured_names") or []
    subs = cs.get("subtypes") or []
    # 中文映射
    subtype_map = {
        "contract_change": "契約變更",
        "policyholder_change": "要保人變更",
        "claim_history": "給付紀錄",
        "loan_history": "借還款紀錄",
    }
    subs_zh = [subtype_map.get(s, s) for s in subs if s]

    parts = ["本案為保單查詢註記"]
    if qm == "by_policy_no" and pnos:
        parts.append(f"（以保單號查詢：{pnos[0]}）")
    elif qm == "by_person" and inames:
        parts.append(f"（以人別查詢：{inames[0]}）")

    if subs_zh:
        if len(parts) == 1:
            parts.append(f"（子類型：{subs_zh[0]}）")
        else:
            parts[-1] = parts[-1].rstrip("）") + f"；子類型：{subs_zh[0]}）"

    cs["note"] = "".join(parts)
    payload["class_specific"] = cs

def post_validate(payload: Dict[str, Any], raw_text: str, doc_class: str) -> Dict[str, Any]:
    # 0) class_specific 先確保是 dict（避免字串嵌套）
    payload = _ensure_class_specific_dict(payload)

    # 1) 身分證檢核
    targets = payload.get("targets", []) or []
    for p in targets:
        twid = p.get("tw_id")
        p["id_valid"] = bool(twid and validate_tw_id(twid))
    payload["targets"] = targets

    # 2) officer / phone / doc_no / doc_date 的 fallback
    if not payload.get("officer_role") and not payload.get("officer_name"):
        role, name = extract_officer(raw_text)
        payload["officer_role"] = role
        payload["officer_name"] = name

    if not payload.get("contact_phone"):
        phone = extract_phone(raw_text)
        if phone:
            payload["contact_phone"] = phone

    if not payload.get("doc_no"):
        doc_no = extract_doc_no(raw_text)
        if doc_no:
            payload["doc_no"] = doc_no

    if not payload.get("doc_date"):
        dd = extract_doc_date(raw_text)
        if dd:
            payload["doc_date"] = dd

    # 3) ★ 若有對應 add-on，且模型沒給 note，兜底補 note
    _best_effort_note(payload, doc_class=doc_class)

    # 4) ★ Debug：看模型到底回了什麼
    print("DEBUG class_specific:", payload.get("class_specific"))
    print("DEBUG policies:", payload.get("policies"))

    return payload

def render_reply(payload: Dict[str, Any]) -> str:
    from datetime import datetime
    env = Environment(loader=FileSystemLoader(str(BASE / "templates")), trim_blocks=True, lstrip_blocks=True)
    tpl = env.get_template("reply_letter.txt.j2")

    today = today_fields()
    doc_date_iso = payload.get("doc_date") or today["today_iso"]
    try:
        dt = datetime.fromisoformat(doc_date_iso)
        display = {
            "display_yyyy": f"{dt.year}",
            "display_mm": f"{dt.month:02d}",
            "display_dd": f"{dt.day:02d}",
            "display_iso": dt.strftime("%Y-%m-%d"),
        }
    except Exception:
        display = {
            "display_yyyy": today["today_yyyy"],
            "display_mm": today["today_mm"],
            "display_dd": today["today_dd"],
            "display_iso": today["today_iso"],
        }

    text = tpl.render(
        agency=payload.get("agency"),
        reference_date=payload.get("reference_date"),
        doc_no=payload.get("doc_no"),
        officer_role=payload.get("officer_role"),
        officer_name=payload.get("officer_name"),
        contact_phone=payload.get("contact_phone"),
        targets=payload.get("targets", []),
        policies=payload.get("policies", []),
        class_specific=payload.get("class_specific", {}),  # ★ 一定傳進模板
        display_yyyy=display["display_yyyy"],
        display_mm=display["display_mm"],
        display_dd=display["display_dd"],
        display_iso=display["display_iso"],
    )
    return text

def infer_class_from_path(p: Path) -> str:
    # 預期 data/<類別>/<檔名>.txt
    return p.parent.name

def main():
    ap = argparse.ArgumentParser(description="Gov letter router → LLM extract → reply text")
    ap.add_argument("--data-dir", default=str(BASE / "data"))
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--out-dir", default=str(BASE / "outputs"))
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    txt_files = list(data_dir.glob("*/*.txt"))
    if not txt_files:
        print(f"[WARN] 在 {data_dir} 未找到 txt（預期：data/<類別>/<檔名>.txt）")
        return

    for fp in txt_files:
        doc_class = infer_class_from_path(fp)
        raw_text = fp.read_text(encoding="utf-8", errors="ignore")
        prompt = load_prompt(raw_text, doc_class=doc_class)

        print(f"[INFO] 處理：{fp.name}（類別：{doc_class}）… 送 LLM 抽取")
        payload = chat_ollama_json(prompt, model=args.model, temperature=0.1)

        payload = post_validate(payload, raw_text=raw_text, doc_class=doc_class)
        reply = render_reply(payload)

        out_path = out_dir / (fp.stem + ".reply.txt")
        out_path.write_text(reply, encoding="utf-8")
        print(f"[OK] 已輸出：{out_path}")

if __name__ == "__main__":
    main()
