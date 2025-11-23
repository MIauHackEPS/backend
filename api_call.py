import openai
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = openai.Client(api_key=OPENAI_API_KEY, base_url="https://innwater.eurecatprojects.com/lite-llm/")

print(client.models.list())

available_models = ["gpt-4o-mini", "qwen2-7b-instruct"]

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain SMOTE in 3 bullets."},
    ],
)

print(resp.choices[0].message.content)
