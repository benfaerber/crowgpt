"""Phase 4 scaling infra: a small MLP trained on the GPU (torch).

At n~117 this will NOT beat the linear model — it's here to (a) exercise the
GPU path and (b) be ready when the corpus grows to thousands, where a nonlinear
head starts to pay off. Runs in system python (torch + CUDA); loads the same
cached BirdNET embeddings.

  python3 gpu_mlp.py
"""

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
FEATURES = HERE.parent / "representation" / "results" / "birdnet_features.npz"


class MLP(nn.Module):
    def __init__(self, dim, n_classes):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim, 128), nn.ReLU(), nn.Dropout(0.5),
            nn.Linear(128, n_classes),
        )

    def forward(self, x):
        return self.net(x)


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device == "cuda" else ""))
    torch.manual_seed(0)

    d = np.load(FEATURES, allow_pickle=True)
    X, y = d["X"], d["y"].astype(str)
    classes = sorted(set(y))
    yi = np.array([classes.index(c) for c in y])

    X_tr, X_tmp, y_tr, y_tmp = train_test_split(
        X, yi, test_size=0.3, stratify=yi, random_state=0)
    X_val, X_te, y_val, y_te = train_test_split(
        X_tmp, y_tmp, test_size=0.5, stratify=y_tmp, random_state=0)

    scaler = StandardScaler().fit(X_tr)
    to_t = lambda a: torch.tensor(scaler.transform(a), dtype=torch.float32, device=device)
    Xtr, Xval, Xte = to_t(X_tr), to_t(X_val), to_t(X_te)
    ytr = torch.tensor(y_tr, device=device)

    counts = np.bincount(y_tr, minlength=len(classes))
    weights = torch.tensor(len(y_tr) / (len(classes) * np.maximum(counts, 1)),
                           dtype=torch.float32, device=device)
    model = MLP(X.shape[1], len(classes)).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-3)
    loss_fn = nn.CrossEntropyLoss(weight=weights)

    best_f1, best_state, patience, since = -1.0, None, 40, 0
    for epoch in range(400):
        model.train()
        opt.zero_grad()
        loss = loss_fn(model(Xtr), ytr)
        loss.backward()
        opt.step()
        model.eval()
        with torch.no_grad():
            vpred = model(Xval).argmax(1).cpu().numpy()
        vf1 = f1_score(y_val, vpred, average="macro", zero_division=0)
        if vf1 > best_f1:
            best_f1, best_state, since = vf1, {k: v.cpu().clone() for k, v in model.state_dict().items()}, 0
        else:
            since += 1
            if since >= patience:
                break

    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        tpred = model(Xte).argmax(1).cpu().numpy()
    print(f"held-out test (n={len(y_te)}): "
          f"acc={accuracy_score(y_te, tpred):.3f} "
          f"macro-F1={f1_score(y_te, tpred, average='macro', zero_division=0):.3f}")
    print("(compare to logreg CV macro-F1 in train.py — expect linear to win at this n)")


if __name__ == "__main__":
    main()
