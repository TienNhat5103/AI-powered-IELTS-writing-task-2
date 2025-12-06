from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import os
from huggingface_hub import login
from dotenv import load_dotenv
from mistral_model import PromptMistral
load_dotenv()
login(os.getenv("IELTS_HUGGINGFACE_API_KEY_2"))


model_id = "Tiennhat123/MISTRAL_FINETUNE"

tokenizer = AutoTokenizer.from_pretrained(model_id)

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=torch.float16,   # hoặc float32 nếu CPU
    device_map="cpu"             # hoặc "auto"
)
inputs = tokenizer(
[
    PromptMistral(band,question, essay)
], return_tensors = "pt").to("cpu")
outputs = model.generate(**inputs, max_new_tokens=5)
generated_text = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]

