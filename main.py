import argparse, json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from .router import load_prompt
from .llm_client import chat_ollama_json
from .utils import validate_tw_id, today_fields

BASE = Path(__file__).resolve().parents[1]

class Person(BaseModel):
    name: str
    alias: List[str] = []
    tw_id: Optional[str] = None
    id_valid: bool = False

def post_validate(payload: Dict[str, Any]) -> Dict[str, Any]:
    # 身分證檢核
    targets = payload.get("targets", [])
    out = []
    for p in targets:
        twid = p.get("tw_id")
        p["id_valid"] = bool(twid and validate_tw_id(twid))
        out.append(p)
    payload["targets"] = out
    return payload

def render_reply(payload: Dict[str, Any], *, company_name: str, company_short: str,
                 contact_dept: str, contact_person: str, contact_phone: str, contact_email: str,
                 serial_no: str) -> str:
    env = Environment(loader=FileSystemLoader(str(BASE / "templates")), trim_blocks=True, lstrip_blocks=True)
    tpl = env.get_template("reply_letter.txt.j2")
    today = today_fields()
    text = tpl.render(
        company_name=company_name,
        company_short=company_short,
        agency=payload.get("agency"),
        reference_date=payload.get("reference_date"),
        targets=payload.get("targets", []),
        policies=payload.get("policies", []),
        class_specific=payload.get("class_specific", {}),
        contact_dept=contact_dept,
        contact_person=contact_person,
        contact_phone=contact_phone,
        contact_email=contact_email,
        serial_no=serial_no,
        **today
    )
    return text

def infer_class_from_path(p: Path) -> str:
    # 假設你的資料結構為 data/<類別>/<檔名>.txt
    return p.parent.name

def main():
    ap = argparse.ArgumentParser(description="Gov letter router → LLM extract → reply text")
    ap.add_argument("--data-dir", default=str(BASE / "data"), help="資料夾路徑（內含已分類好的 .txt 檔）")
    ap.add_argument("--model", default="qwen2.5:7b-instruct", help="Ollama 模型名稱")
    ap.add_argument("--out-dir", default=str(BASE / "outputs"), help="輸出回文純文字的資料夾")
    ap.add_argument("--company-name", default="○○人壽保險股份有限公司")
    ap.add_argument("--company-short", default="○○壽")
    ap.add_argument("--contact-dept", default="客服科")
    ap.add_argument("--contact-person", default="張○○")
    ap.add_argument("--contact-phone", default="(02)1234-5678")
    ap.add_argument("--contact-email", default="service@example.com")
    ap.add_argument("--serial-no", default="000001")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    txt_files = list(data_dir.glob("*/*.txt"))
    if not txt_files:
        print(f"[WARN] 在 {data_dir} 底下未找到任何 txt（預期結構：data/<類別>/<檔名>.txt）")
        return

    for fp in txt_files:
        doc_class = infer_class_from_path(fp)
        text = fp.read_text(encoding="utf-8", errors="ignore")
        prompt = load_prompt(text, doc_class=doc_class)

        print(f"[INFO] 處理：{fp.name}（類別：{doc_class}）… 送 LLM 抽取")
        payload = chat_ollama_json(prompt, model=args.model, temperature=0.1)
        payload = post_validate(payload)

        reply = render_reply(
            payload,
            company_name=args.company_name,
            company_short=args.company_short,
            contact_dept=args.contact_dept,
            contact_person=args.contact_person,
            contact_phone=args.contact_phone,
            contact_email=args.contact_email,
            serial_no=args.serial_no
        )

        out_path = out_dir / (fp.stem + ".reply.txt")
        out_path.write_text(reply, encoding="utf-8")
        print(f"[OK] 已輸出：{out_path}")

if __name__ == "__main__":
    main()
