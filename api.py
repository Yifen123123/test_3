import json, urllib.request, sys

# === 把這三個變數改成你的固定值 ===
HOST   = "http://YOUR_OLLAMA_HOST:11434"   # 例： http://10.0.0.5:11434 或 http://your.domain/ollama
MODEL  = "qwen2.5:7b-instruct"              # 例： llama3.2 / qwen2.5:14b-instruct
PROMPT = "why is the sky blue?"             # 你要問的內容（可改成任何字串）

def main():
    url = HOST.rstrip("/") + "/api/chat"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False  # 非串流：一次回完整結果
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print((data.get("message") or {}).get("content", ""))
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr); sys.exit(2)

if __name__ == "__main__":
    main()
