import torch
from torch import nn


class ANNClassifier(nn.Module):
    def __init__(self, input_dim, hidden_units=64, output_dim=1, dropout=0.1, device="cpu"):
        super().__init__()
        self.device = torch.device(device)
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_units),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_units, hidden_units),
            nn.ReLU(),
            nn.Linear(hidden_units, output_dim),
            nn.Sigmoid(),
        ).to(self.device)

    def forward(self, x):
        return self.net(x.to(self.device)).view(-1, 1)

    def get_optimizer(self, name="adam", lr=0.001):
        if name == "sgd":
            return torch.optim.SGD(self.parameters(), lr=lr)
        if name == "adagrad":
            return torch.optim.Adagrad(self.parameters(), lr=lr)
        if name == "rmsprop":
            return torch.optim.RMSprop(self.parameters(), lr=lr)
        return torch.optim.Adam(self.parameters(), lr=lr)
