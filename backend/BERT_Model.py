import torch
import torch.nn as nn
from transformers import BertModel
import numpy as np
from sklearn.preprocessing import StandardScaler
class BERTWithExtraFeature(nn.Module):
    def __init__(self, pretrained_model_name='bert-base-uncased', dropout_prob=0.2, num_trainable_layers=1):
        super(BERTWithExtraFeature, self).__init__()
        self.bert = BertModel.from_pretrained(pretrained_model_name)

        # Freeze all layers in the BERT model
        for param in self.bert.parameters():
            param.requires_grad = False

        # Unfreeze the last `num_trainable_layers` layers
        for layer in self.bert.encoder.layer[-num_trainable_layers:]:
            for param in layer.parameters():
                param.requires_grad = True

        # BatchNorm for numerical input
        self.num_feature_norm = nn.BatchNorm1d(1)

        # Combined input size: 768 (BERT) + 1 (extra num)
        self.concat_input_dim = 768 + 1

        # New feed-forward layer stack
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
        normalized_num = self.num_feature_norm(extra_number)

        concat = torch.cat((pooled_output, normalized_num), dim=1)

        x = self.fc0(concat)
        x = self.relu0(x)
        x = self.fc1(x)
        x = self.relu1(x)
        x = self.fc2(x)
        x = self.relu2(x)
        x = self.fc3(x)
        x = self.relu3(x)
        
        output = self.output_layer(x)

        return output
def preprocess_inputs_pt(question, answer, bert_tokenizer, scaler: StandardScaler, device, max_length=512):
    extra_number = len(question.split()) + len(answer.split())
    tokenize_output = tokenize_inputs_pt([question], [answer],  bert_tokenizer, max_length=512)
    input_ids = tokenize_output['input_ids'].to(device)
    attention_mask = tokenize_output['attention_mask'].to(device)
    extra_number = torch.tensor([extra_number], dtype=torch.float32).to(device)
    numerical_features_val_std = scaler.transform([extra_number])
    numerical_features_val_std = torch.tensor(numerical_features_val_std, dtype=torch.float32).to(device)
    return input_ids, attention_mask, numerical_features_val_std
def tokenize_inputs_pt(questions, essays, tokenizer, print_stats=False, max_length=512):
    input_ids_list = []
    attention_masks_list = []
    lengths_token = []
    lengths_sequences = []
    num_overflow = 0
    id_list = np.arange(len(questions))
    
    for id, q, e in zip(id_list, questions, essays):
        encoding = tokenizer(
            q, e,
            padding="max_length",  # Padding to ensure uniform length
            truncation=True,  # Ensuring truncation for longer inputs
            max_length=max_length,  # Optional: set max_length explicitly
            return_tensors="pt"  # Return in tensor format
        )
        input_ids_list.append(encoding["input_ids"].squeeze(0))  # Remove batch dimension
        attention_masks_list.append(encoding["attention_mask"].squeeze(0))  # Remove batch dimension
        
        lengths_token.append(len(encoding["input_ids"]))

    if print_stats:
        print(f"Max length: {max(lengths_token)}")
        print(f"Min length: {min(lengths_token)}")
        print(f"Average length: {sum(lengths_token) / len(lengths_token):.2f}")
        print(f"Number of overflowed sequences: {num_overflow}")
        print(f"Overflowed sequences ratio: {num_overflow / len(lengths_token):.2%}")
        for length in lengths_sequences:
            print(f"Question length: {length[0]}, Essay length: {length[1]} , Score: {length[2]}, ID: {length[3]}")

    # Convert list of tensors into a single tensor
    input_ids_tensor = torch.stack(input_ids_list, dim=0)  # Stack along batch dimension
    attention_mask_tensor = torch.stack(attention_masks_list, dim=0)
    
    return {
        "input_ids": input_ids_tensor,
        "attention_mask": attention_mask_tensor,
        "lengths_token": lengths_token,
        "lengths_sequences": lengths_sequences,
    }
def round_to_nearest_half_np(x, method='nearest'):
    """
    Vectorized rounding to nearest 0.5 for NumPy arrays.

    Parameters:
        x (array-like): Input number or array of numbers.
        method (str): 'nearest', 'up', or 'down'

    Returns:
        np.ndarray: Rounded numbers
    """
    x = np.asarray(x)  # Ensure input is a NumPy array

    if method == 'nearest':
        return np.round(x * 2) / 2
    elif method == 'up':
        return np.ceil(x * 2) / 2
    elif method == 'down':
        return np.floor(x * 2) / 2
    else:
        raise ValueError("Method must be 'nearest', 'up', or 'down'")