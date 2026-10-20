import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 8,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
})

# ---- Fig 1: detector comparison (gpt-4o-mini, n=1, temperature 0) ----
metrics = ["Precision", "Recall", "F1", "False-alarm rate"]
data = {
    "SpecGuard (retrieval + verification)": [0.67, 0.58, 0.62, 0.63],
    "Whole-file prompting":                 [0.91, 0.17, 0.29, 0.04],
    "Keyword matching":                     [0.33, 0.08, 0.14, 0.37],
}
x = np.arange(len(metrics)); w = 0.26
fig, ax = plt.subplots(figsize=(3.4, 2.1), dpi=400)
greys = ["0.25", "0.55", "0.80"]
for i, (name, vals) in enumerate(data.items()):
    b = ax.bar(x + (i - 1) * w, vals, w, label=name, color=greys[i],
               edgecolor="black", linewidth=0.5)
    ax.bar_label(b, fmt="%.2f", fontsize=5.2, padding=1)
ax.set_xticks(x); ax.set_xticklabels(metrics, fontsize=7)
ax.set_ylabel("Value", fontsize=7.5); ax.set_ylim(0, 1.08)
ax.legend(fontsize=5.6, frameon=False, loc="upper right", handlelength=1.2)
ax.spines[["top", "right"]].set_visible(False)
ax.tick_params(labelsize=6.5)
fig.tight_layout(pad=0.3)
fig.savefig("fig1.png", bbox_inches="tight")

# ---- Fig 2: Stage 1 Recall@3 per drift category ----
cats = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"]
r3 = [0.83, 0.67, 0.50, 1.00, 1.00, 0.67, 0.83, 0.33, 1.00]
fig, ax = plt.subplots(figsize=(3.4, 1.9), dpi=400)
b = ax.bar(cats, r3, 0.6, color="0.55", edgecolor="black", linewidth=0.5)
ax.bar_label(b, fmt="%.2f", fontsize=5.5, padding=1)
ax.axhline(0.78, linestyle="--", linewidth=0.7, color="black")
ax.text(8.6, 0.80, "overall 0.78", fontsize=5.8, ha="right")
ax.set_ylabel("Recall@3", fontsize=7.5); ax.set_ylim(0, 1.12)
ax.set_xlabel("Drift category", fontsize=7.5)
ax.spines[["top", "right"]].set_visible(False)
ax.tick_params(labelsize=6.5)
fig.tight_layout(pad=0.3)
fig.savefig("fig2.png", bbox_inches="tight")
print("figures written")
