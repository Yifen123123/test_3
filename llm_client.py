# src/llm_client.py
import os, json, requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

def chat_ollama_raw(prompt: str, model: str, temperature: float = 0.2, timeout: int = 600) -> str:
    url = f"{OLLAMA_HOST}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        # 關鍵：關掉串流，避免中間設備因為 chunked/SSE 斷線
        "stream": False,
        "options": {"temperature": temperature}
    }
    # 一些防斷線小技巧
    headers = {"Connection": "close"}  # 避免 keep-alive 在某些代理上出事
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]

def chat_ollama_json(prompt: str, model: str, temperature: float = 0.2) -> dict:
    text = chat_ollama_raw(prompt, model=model, temperature=temperature)
    # JSON 修復嘗試
    for _ in range(2):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if "```" in text:
                parts = text.split("```")
                text = max(parts, key=len).strip()
            else:
                s = text.find("{"); e = text.rfind("}")
                if s != -1 and e != -1 and e > s:
                    text = text[s:e+1]
                else:
                    break
    return json.loads(text)
