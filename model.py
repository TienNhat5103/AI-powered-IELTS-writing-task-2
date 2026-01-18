import torch
import torch.nn as nn
from transformers import BertModel
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
        normalized_num = extra_number

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