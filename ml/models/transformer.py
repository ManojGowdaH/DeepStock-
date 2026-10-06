import torch
from torch import nn


class TemporalTransformer(nn.Module):
    def __init__(self, input_dim, d_model=32, nhead=4, num_layers=2, device="cpu"):
        super().__init__()
        self.device = torch.device(device)
        self.embedding = nn.Linear(input_dim, d_model).to(self.device)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 2,
            dropout=0.1,
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers).to(self.device)
        self.output = nn.Sequential(
            nn.Linear(d_model, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        ).to(self.device)

    def forward(self, x):
        x = self.embedding(x.to(self.device))
        x = self.encoder(x)
        x = x[:, -1, :]
        return self.output(x).view(-1, 1)

    def get_optimizer(self, name="adam", lr=0.001):
        if name == "sgd":
            return torch.optim.SGD(self.parameters(), lr=lr)
        if name == "adagrad":
            return torch.optim.Adagrad(self.parameters(), lr=lr)
        if name == "rmsprop":
            return torch.optim.RMSprop(self.parameters(), lr=lr)
        return torch.optim.Adam(self.parameters(), lr=lr)
