import torch
from torch import nn


class TemporalCNN(nn.Module):
    def __init__(self, input_dim, hidden_channels=32, device="cpu"):
        super().__init__()
        self.device = torch.device(device)
        self.net = nn.Sequential(
            nn.Conv1d(input_dim, hidden_channels, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(hidden_channels, hidden_channels, kernel_size=3, padding=1),
            nn.ReLU(),
        ).to(self.device)
        self.classifier = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(hidden_channels, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        ).to(self.device)

    def forward(self, x):
        x = x.permute(0, 2, 1)
        x = self.net(x.to(self.device))
        return self.classifier(x).view(-1, 1)

    def get_optimizer(self, name="adam", lr=0.001):
        if name == "sgd":
            return torch.optim.SGD(self.parameters(), lr=lr)
        if name == "adagrad":
            return torch.optim.Adagrad(self.parameters(), lr=lr)
        if name == "rmsprop":
            return torch.optim.RMSprop(self.parameters(), lr=lr)
        return torch.optim.Adam(self.parameters(), lr=lr)
