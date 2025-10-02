import requests

url = "http://YOUR_OLLAMA_HOST:11434/api/generate"

payload = {
    "model": "qwen2.5:7b-instruct",   # 換成你伺服器已經 pull 下來的模型
    "prompt": "請用繁體中文介紹一下台灣的小吃。",
    "stream": False
}

resp = requests.post(url, json=payload)
resp.raise_for_status()

print(resp.json()["response"])
