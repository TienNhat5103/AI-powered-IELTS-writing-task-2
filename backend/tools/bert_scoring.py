import os
import threading

import joblib
import numpy as np
import torch
import torch.nn as nn
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download, login
from sklearn.preprocessing import StandardScaler
from transformers import BertModel, BertTokenizer


class BERTWithExtraFeature(nn.Module):
    def __init__(self, pretrained_model_name="bert-base-uncased", dropout_prob=0.2, num_trainable_layers=1):
        super(BERTWithExtraFeature, self).__init__()
        self.bert = BertModel.from_pretrained(pretrained_model_name)

        for param in self.bert.parameters():
            param.requires_grad = False

        for layer in self.bert.encoder.layer[-num_trainable_layers:]:
            for param in layer.parameters():
                param.requires_grad = True

        self.concat_input_dim = 768 + 1
        self.fc0 = nn.Linear(self.concat_input_dim, 512)
        self.relu0 = nn.ReLU()
        self.fc1 = nn.Linear(512, 256)
        self.relu1 = nn.ReLU()
        self.fc2 = nn.Linear(256, 128)
        self.relu2 = nn.ReLU()
        self.fc3 = nn.Linear(128, 64)
        self.relu3 = nn.ReLU()
        self.output_layer = nn.Linear(64, 1)

    def forward(self, input_ids, attention_mask, extra_number):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        pooled_output = outputs.pooler_output

        if extra_number.dim() == 1:
            extra_number = extra_number.unsqueeze(1)

        concat = torch.cat((pooled_output, extra_number), dim=1)

        x = self.fc0(concat)
        x = self.relu0(x)
        x = self.fc1(x)
        x = self.relu1(x)
        x = self.fc2(x)
        x = self.relu2(x)
        x = self.fc3(x)
        x = self.relu3(x)

        return self.output_layer(x)


def tokenize_inputs_pt(questions, essays, tokenizer, print_stats=False, max_length=512):
    input_ids_list = []
    attention_masks_list = []
    lengths_token = []
    lengths_sequences = []
    num_overflow = 0
    id_list = np.arange(len(questions))

    for item_id, question, essay in zip(id_list, questions, essays):
        encoding = tokenizer(
            question,
            essay,
            padding="max_length",
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        input_ids_list.append(encoding["input_ids"].squeeze(0))
        attention_masks_list.append(encoding["attention_mask"].squeeze(0))
        lengths_token.append(len(encoding["input_ids"]))

    if print_stats:
        print(f"Max length: {max(lengths_token)}")
        print(f"Min length: {min(lengths_token)}")
        print(f"Average length: {sum(lengths_token) / len(lengths_token):.2f}")
        print(f"Number of overflowed sequences: {num_overflow}")
        print(f"Overflowed sequences ratio: {num_overflow / len(lengths_token):.2%}")
        for length in lengths_sequences:
            print(f"Question length: {length[0]}, Essay length: {length[1]} , Score: {length[2]}, ID: {length[3]}")

    return {
        "input_ids": torch.stack(input_ids_list, dim=0),
        "attention_mask": torch.stack(attention_masks_list, dim=0),
        "lengths_token": lengths_token,
        "lengths_sequences": lengths_sequences,
    }


def preprocess_inputs_pt(question, answer, bert_tokenizer, scaler: StandardScaler, device, max_length=512):
    extra_number = len(question.split()) + len(answer.split())
    tokenize_output = tokenize_inputs_pt([question], [answer], bert_tokenizer, max_length=max_length)
    input_ids = tokenize_output["input_ids"].to(device)
    attention_mask = tokenize_output["attention_mask"].to(device)
    numerical_features_val_std = scaler.transform([[extra_number]])
    numerical_features_val_std = torch.tensor(numerical_features_val_std, dtype=torch.float32).to(device)
    return input_ids, attention_mask, numerical_features_val_std


def round_to_nearest_half_np(x, method="nearest"):
    x = np.asarray(x)

    if method == "nearest":
        return np.round(x * 2) / 2
    if method == "up":
        return np.ceil(x * 2) / 2
    if method == "down":
        return np.floor(x * 2) / 2
    raise ValueError("Method must be 'nearest', 'up', or 'down'")


load_dotenv()

MODEL_REPOSITORY = "Tiennhat123/IELTS_BERT_FINETUNE"
device = "cpu"
_runtime = None
_runtime_lock = threading.Lock()
_inference_lock = threading.Lock()


def _load_runtime():
    global _runtime

    if _runtime is not None:
        return _runtime

    with _runtime_lock:
        if _runtime is not None:
            return _runtime

        token = os.getenv("IELTS_HUGGINGFACE_API_KEY")
        if token:
            login(token=token)

        bert_tokenizer = BertTokenizer.from_pretrained(
            MODEL_REPOSITORY,
            token=token,
        )
        model = BERTWithExtraFeature()
        model_path = hf_hub_download(
            repo_id=MODEL_REPOSITORY,
            filename="pytorch_model.bin",
            token=token,
        )
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.to(device)

        scaler_path = hf_hub_download(
            repo_id=MODEL_REPOSITORY,
            filename="scaler.pkl",
            token=token,
        )
        scaler = joblib.load(scaler_path)
        _runtime = (bert_tokenizer, model, scaler)

    return _runtime


def get_overall_score(question, answer):
    bert_tokenizer, model, scaler = _load_runtime()
    input_ids, attention_mask, extra_number = preprocess_inputs_pt(
        question,
        answer,
        bert_tokenizer,
        scaler,
        device,
        max_length=512,
    )

    with _inference_lock:
        model.eval()
        with torch.no_grad():
            output = model(input_ids, attention_mask, extra_number)
            output = output.cpu().numpy()
            score = round_to_nearest_half_np(output, method="nearest")

    return np.clip(score[0][0], 0, 9)


def score_essay(question: str, answer: str) -> float:
    """Estimate the overall IELTS band score using the fine-tuned BERT model."""
    return float(get_overall_score(question, answer))
