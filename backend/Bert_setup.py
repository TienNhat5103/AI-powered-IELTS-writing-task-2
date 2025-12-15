from transformers import  BertTokenizer
import torch
import os
import joblib
from huggingface_hub import login, hf_hub_download
from dotenv import load_dotenv
from bert_model import BERTWithExtraFeature, round_to_nearest_half_np, preprocess_inputs_pt
# from transformers import AutoConfig
load_dotenv()
login(os.getenv("IELTS_HUGGINGFACE_API_KEY"))
bert_tokenizer = BertTokenizer.from_pretrained("Tiennhat123/IELTS_BERT_FINETUNE")
model = BERTWithExtraFeature()
device = "cpu"
model_path = hf_hub_download(
    repo_id="Tiennhat123/IELTS_BERT_FINETUNE",
    filename="pytorch_model.bin"
)
model.load_state_dict(torch.load(model_path, map_location="cpu"))
scaler_path = hf_hub_download(
    repo_id="Tiennhat123/IELTS_BERT_FINETUNE",
    filename="scaler.pkl"
)
scaler = joblib.load(scaler_path)

def get_overall_score(question, answer):
    # preprocess the input
    input_ids, attention_mask, extra_number = preprocess_inputs_pt(question, answer, bert_tokenizer, scaler, device, max_length=512)

    model.eval()  # Set the model to evaluation mode
    with torch.no_grad():  # No gradient computation during testing
        output = model(input_ids, attention_mask, extra_number)
        output = output.cpu().numpy()
        score = round_to_nearest_half_np(output, method='nearest')
        
    return score[0][0]