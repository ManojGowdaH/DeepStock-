import torch
from torch import nn


class SimpleRNNClassifier(nn.Module):
    def __init__(self, input_dim, hidden_size=32, device="cpu"):
        super().__init__()
        self.device = torch.device(device)
        self.rnn = nn.RNN(input_size=input_dim, hidden_size=hidden_size, batch_first=True).to(self.device)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        ).to(self.device)

    def forward(self, x):
        out, _ = self.rnn(x.to(self.device))
        return self.fc(out[:, -1, :]).view(-1, 1)

    def get_optimizer(self, name="adam", lr=0.001):
        if name == "sgd":
            return torch.optim.SGD(self.parameters(), lr=lr)
        if name == "adagrad":
            return torch.optim.Adagrad(self.parameters(), lr=lr)
        if name == "rmsprop":
            return torch.optim.RMSprop(self.parameters(), lr=lr)
        return torch.optim.Adam(self.parameters(), lr=lr)
