import torch
from torch import nn


class SimpleViT(nn.Module):
    def __init__(self, input_dim=18, embed_dim=32, device="cpu"):
        super().__init__()
        self.device = torch.device(device)
        self.proj = nn.Linear(input_dim, embed_dim).to(self.device)
        self.classifier = nn.Sequential(
            nn.Linear(embed_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        ).to(self.device)

    def forward(self, x):
        x = self.proj(x.to(self.device))
        x = x.mean(dim=1)
        return self.classifier(x).view(-1, 1)
