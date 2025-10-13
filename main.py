import argparse, json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from .router import load_prompt
from .llm_client import chat_ollama_json
from .utils import validate_tw_id, today_fields, extract_doc_no, extract_doc_date

BASE = Path(__file__).resolve().parents[1]
PROMPTS_DIR = BASE / "prompts" / "addons"

# 類別對應預設 note，可自由增減
DEFAULT_NOTES = {
    "保單查詢": "本案為保單查詢註記",
    "保單查詢＋註記": "本案為保單查詢註記",
    "扣押命令": "本案涉及保險金遭扣押，依規定辦理",
    "撤銷令": "本案為撤銷原有保險相關命令之函文",
    "通知函": "本案為通知性公文，依內容辦理相關作業",
    "收取令": "本案為法院或機關發出之收取保險金命令",
    "收取＋撤銷": "本案包含收取命令與撤銷指令之合併處理",
    "保單註記": "本案為保單註記查詢或異動",
    "保單查詢＋註記": "本案為保單查詢與註記之合併查詢"
}

def post_validate(payload, raw_text, doc_class):
    """簡版後處理，確保 class_specific.note 一定存在"""
    # class_specific 若是字串 → 轉成 dict
    cs = payload.get("class_specific") or {}
    if isinstance(cs, str):
        try: cs = json.loads(cs)
        except: cs = {}
    payload["class_specific"] = cs

    # 若模型沒給 note 且有對應 add-on → 補預設
    if not cs.get("note") and (PROMPTS_DIR / f"{doc_class}.prompt").exists():
        cs["note"] = DEFAULT_NOTES.get(doc_class, f"本案為{doc_class}函文")
    payload["class_specific"] = cs

    # 身分證檢核
    for p in payload.get("targets", []) or []:
        twid = p.get("tw_id")
        p["id_valid"] = bool(twid and validate_tw_id(twid))
    payload["targets"] = payload.get("targets", [])

    # 文號與日期 fallback
    for k, fn in {"doc_no": extract_doc_no, "doc_date": extract_doc_date}.items():
        if not payload.get(k):
            v = fn(raw_text)
            if v: payload[k] = v

    print("DEBUG class_specific:", payload.get("class_specific"))
    return payload

def render_reply(payload):
    """模板渲染"""
    env = Environment(loader=FileSystemLoader(str(BASE / "templates")),
                      trim_blocks=True, lstrip_blocks=True)
    tpl = env.get_template("reply_letter.txt.j2")
    today = today_fields()
    return tpl.render(
        agency=payload.get("agency"),
        reference_date=payload.get("reference_date"),
        doc_no=payload.get("doc_no"),
        targets=payload.get("targets", []),
        policies=payload.get("policies", []),
        class_specific=payload.get("class_specific", {}),
        display_yyyy=today["today_yyyy"],
        display_mm=today["today_mm"],
        display_dd=today["today_dd"],
        display_iso=today["today_iso"],
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(BASE / "data"))
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--out-dir", default=str(BASE / "outputs"))
    args = ap.parse_args()

    data_dir, out_dir = Path(args.data_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for fp in data_dir.glob("*/*.txt"):
        doc_class = fp.parent.name
        raw = fp.read_text(encoding="utf-8", errors="ignore")
        prompt = load_prompt(raw, doc_class)
        print(f"[INFO] {fp.name} ({doc_class})")
        payload = chat_ollama_json(prompt, model=args.model)
        payload = post_validate(payload, raw, doc_class)
        reply = render_reply(payload)
        (out_dir / (fp.stem + ".reply.txt")).write_text(reply, encoding="utf-8")
        print(f"[OK] → {fp.stem}.reply.txt")

if __name__ == "__main__":
    main()
