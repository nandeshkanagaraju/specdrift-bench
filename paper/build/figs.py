import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 8,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
})

# ---- Fig 1: detector comparison (gpt-4o-mini, temperature 0) ----
# Bars are run 1 (the values in Table IV); whiskers are bootstrap 95% intervals over cases,
# pooling SpecGuard's three runs (the baselines were run once). Source: results-snapshot/.
metrics = ["Precision", "Recall", "F1", "False-alarm rate"]
data = {
    "SpecGuard (retrieval + verification)": [0.65, 0.54, 0.59, 0.63],
    "Whole-file prompting":                 [0.91, 0.17, 0.29, 0.04],
    "Keyword matching":                     [0.33, 0.08, 0.14, 0.37],
}
ci = {
    "SpecGuard (retrieval + verification)": [(0.51, 0.77), (0.41, 0.66), (0.47, 0.68), (0.47, 0.83)],
    "Whole-file prompting":                 [(0.70, 1.00), (0.08, 0.27), (0.15, 0.42), (0.00, 0.12)],
    "Keyword matching":                     [(0.10, 0.60), (0.02, 0.16), (0.03, 0.24), (0.19, 0.56)],
}
x = np.arange(len(metrics)); w = 0.26
fig, ax = plt.subplots(figsize=(3.4, 2.1), dpi=400)
greys = ["0.25", "0.55", "0.80"]
for i, (name, vals) in enumerate(data.items()):
    lows = [v - lo for v, (lo, hi) in zip(vals, ci[name])]
    highs = [hi - v for v, (lo, hi) in zip(vals, ci[name])]
    pos = x + (i - 1) * w
    ax.bar(pos, vals, w, label=name, color=greys[i], edgecolor="black", linewidth=0.5,
           yerr=[np.clip(lows, 0, None), np.clip(highs, 0, None)],
           error_kw={"elinewidth": 0.6, "capsize": 1.2, "capthick": 0.6})
    for px, v, (lo, hi) in zip(pos, vals, ci[name]):
        ax.text(px, hi + 0.02, f"{v:.2f}", ha="center", fontsize=5.0)
ax.set_xticks(x); ax.set_xticklabels(metrics, fontsize=7)
ax.set_ylabel("Value", fontsize=7.5); ax.set_ylim(0, 1.15)
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
