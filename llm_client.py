import os, json, requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

def chat_ollama_raw(prompt: str, model: str, temperature: float = 0.2, timeout: int = 180) -> str:
    url = f"{OLLAMA_HOST}/api/chat"
    resp = requests.post(url, json={
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": temperature}
    }, timeout=timeout)
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
                cand = max(parts, key=len)
                text = cand.strip()
            else:
                s = text.find("{"); e = text.rfind("}")
                if s != -1 and e != -1 and e > s:
                    text = text[s:e+1]
                else:
                    break
    return json.loads(text)
