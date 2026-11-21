import json
import os
import random
import subprocess
import time

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import hana_sim  # type: ignore

from game import HanasimGame
from hanabi import make_player
from utils import NullStream


# ======================================================================
# Configuration
# ======================================================================

AGENTS = {
    "baseline": "full",                  # SelfIntentionalPlayer V0
    "case_based": "case",                # CaseBasedPlayer
    "self_intentional_v19": "full/19",   # SelfIntentionalPlayer V19
}

NUM_PLAYERS = 3
N_GAMES = 1000
SEEDS = list(range(1, N_GAMES + 1))
OUT_ROOT = "results"


# ======================================================================
# Behavioral metrics
# ======================================================================
def _sum_over_players(metrics, key):
    """Sum a per-player count over all seats."""
    return sum(metrics[key][p] for p in range(NUM_PLAYERS))


def ipp(metrics):
    """Mean IPP over all IPP observations in the game (NaN if none)."""
    values = [v for p in range(NUM_PLAYERS) for v in metrics["ipp_list"][p]]
    return float(np.mean(values)) if values else np.nan


def discard_playable(metrics):
    """Number of known playable discards in the game."""
    return _sum_over_players(metrics, "known_discards")


def play_playable(metrics):
    """Number of known playable plays in the game."""
    return _sum_over_players(metrics, "known_playable_plays")


def play_unplayable(metrics):
    """Number of known unplayable plays in the game."""
    return _sum_over_players(metrics, "known_unplayable_plays")


def communicativeness(metrics):
    """Hints given / turns where a hint was possible, pooled over seats (NaN if none)."""
    possible = _sum_over_players(metrics, "hint_possible")
    return _sum_over_players(metrics, "hint_frequency") / possible if possible > 0 else np.nan


BEHAVIORAL_METRICS = {
    "IPP": ipp,
    "Discard Playable": discard_playable,
    "Play Playable": play_playable,
    "Play Unplayable": play_unplayable,
    "Communicativeness": communicativeness,
}


# ======================================================================
# Simulation
# ======================================================================

def build_players(spec):
    """Build NUM_PLAYERS copies of an agent from a spec like "case" or "full/19"."""
    players = []
    for i in range(NUM_PLAYERS):
        if "/" in spec:
            base, version = spec.split("/")
            players.append(make_player(base, i, int(version)))
        else:
            players.append(make_player(spec, i))
    return players


def evaluate_agent(label, spec):
    """Run all seeded games for one agent; return a per-game DataFrame."""
    print(f"\n--- Evaluating {label} ({spec}) over {len(SEEDS)} games ---")
    players = build_players(spec)
    rows = []
    for k, seed in enumerate(SEEDS):
        if (k + 1) % 100 == 0:
            print(f"  game {k + 1}/{len(SEEDS)}")
        random.seed(seed)
        hana_sim.set_deck_seed(seed)
        game = HanasimGame(players, NullStream(), True)
        score = game.run()
        row = {"seed": seed, "score": score}
        for metric_name, fn in BEHAVIORAL_METRICS.items():
            row[metric_name] = fn(game.metric_dict)
        rows.append(row)
    return pd.DataFrame(rows)


# ======================================================================
# Part 1: Summary statistics
# ======================================================================

def score_summary_table(per_game):
    """One row per agent: mean, median, std, min, max, Q1, Q3, IQR of scores."""
    rows = {}
    for label, df in per_game.items():
        s = df["score"]
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        rows[label] = {
            "mean": s.mean(), "median": s.median(), "std": s.std(),
            "min": s.min(), "max": s.max(),
            "Q1": q1, "Q3": q3, "IQR": q3 - q1,
        }
    return pd.DataFrame(rows).T


def paired_score_differences(per_game, baseline_label):
    """Per-seed score differences vs the baseline (valid because seeds are shared)."""
    base = per_game[baseline_label].set_index("seed")["score"]
    rows = {}
    for label, df in per_game.items():
        if label == baseline_label:
            continue
        diff = df.set_index("seed")["score"] - base
        rows[label] = {
            "mean diff vs baseline": diff.mean(),
            "SE": diff.std() / np.sqrt(len(diff)),
            "games better": int((diff > 0).sum()),
            "games worse": int((diff < 0).sum()),
        }
    return pd.DataFrame(rows).T


def plot_score_histograms(per_game, out_dir):
    """Side-by-side score histograms, one panel per agent, shared axes."""
    n = len(per_game)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 4), sharey=True)
    for ax, (label, df) in zip(np.atleast_1d(axes), per_game.items()):
        ax.hist(df["score"], bins=range(0, 27), edgecolor="black")
        ax.set_title(label)
        ax.set_xlabel("Final score")
    np.atleast_1d(axes)[0].set_ylabel("Number of games")
    fig.suptitle(f"Score distribution over {len(SEEDS)} games")
    fig.tight_layout()
    path = os.path.join(out_dir, "score_histograms.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# ======================================================================
# Part 2: Behavioral metrics
# ======================================================================

def behavioral_summary_table(per_game):
    """Rows = behavioral metrics, columns = agents, cells = per-game mean (std)."""
    means = pd.DataFrame({
        label: df[list(BEHAVIORAL_METRICS)].mean() for label, df in per_game.items()
    })
    stds = pd.DataFrame({
        label: df[list(BEHAVIORAL_METRICS)].std() for label, df in per_game.items()
    })
    return means, stds


def plot_behavioral_bars(means, stds, out_dir):
    """One bar-chart panel per behavioral metric, one bar per agent."""
    metric_names = list(means.index)
    agent_labels = list(means.columns)
    n = len(metric_names)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4))
    for ax, metric in zip(np.atleast_1d(axes), metric_names):
        ax.bar(agent_labels, means.loc[metric], yerr=stds.loc[metric],
               capsize=4, edgecolor="black")
        ax.set_title(metric)
        ax.tick_params(axis="x", rotation=30)
    fig.suptitle("Behavioral metrics (per-game mean ± std)")
    fig.tight_layout()
    path = os.path.join(out_dir, "behavioral_metrics.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# Parameters needed to adjust the radar chart values

# +1 = higher is better, -1 = lower is better
METRIC_DIRECTION = {
    "IPP": +1,
    "Discard Playable": +1,
    "Play Playable": +1,
    "Play Unplayable": +1,
    "Communicativeness": +1,
}

RADAR_MAX_RATIO = 2.0   # clip ratios above this so one outlier can't squash the chart


def normalize_to_baseline(means, baseline_label, eps=1e-9, max_ratio=RADAR_MAX_RATIO):
    """
    Return a DataFrame (metrics x agents) where the baseline is 1.0 on every axis
    and values > 1 always mean "better than baseline".

      higher-is-better:  agent / baseline
      lower-is-better:   baseline / agent   (reciprocal, so "outward" = better)

    eps avoids division by zero (0/0 -> 1, i.e. "same as baseline").
    Returns (normalized, was_clipped) where was_clipped is a boolean DataFrame.
    """
    raw = pd.DataFrame(index=means.index, columns=means.columns, dtype=float)
    for metric in means.index:
        base = means.loc[metric, baseline_label]
        for agent in means.columns:
            val = means.loc[metric, agent]
            if METRIC_DIRECTION[metric] > 0:
                raw.loc[metric, agent] = (val + eps) / (base + eps)
            else:
                raw.loc[metric, agent] = (base + eps) / (val + eps)

    was_clipped = raw > max_ratio
    return raw.clip(upper=max_ratio), was_clipped


def _radar_tick_labels(metric_names, baseline_values):
    labels = []
    for m in metric_names:
        suffix = " (inverted)" if METRIC_DIRECTION[m] < 0 else ""
        labels.append(f"{m}{suffix}\nbaseline = {baseline_values[m]:.2f}")
    return labels


def _draw_radar(ax, norm, agents, title, colors, tick_labels, r_max):
    metrics = list(norm.index)
    angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
    closed = angles + angles[:1]

    # Reference ring at 1.0 = baseline performance
    ring = np.linspace(0, 2 * np.pi, 200)
    ax.plot(ring, np.ones_like(ring), color="black", linestyle="--",
            linewidth=1, alpha=0.7, label="Baseline (1.0)")

    single = len(agents) == 1
    for agent in agents:
        vals = norm[agent].tolist()
        vals += vals[:1]
        ax.plot(closed, vals, color=colors[agent], linewidth=2, label=agent)
        ax.fill(closed, vals, color=colors[agent], alpha=0.30 if single else 0.15)

    ax.set_xticks(angles)
    ax.set_xticklabels(tick_labels, fontsize=8)
    ax.set_ylim(0, r_max)
    ticks = np.arange(0.5, r_max + 1e-9, 0.5)
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{t:g}" for t in ticks], fontsize=7)
    ax.set_title(title, y=1.12)


def plot_behavioral_radars(means, out_dir, baseline_label, save_individual=False):
    """
    2x2 figure: one radar for each of the agents (baseline, case_based,
    self_intentional_v19) plus an overlay of all of them. All panels share the
    same radial scale so they are directly comparable.
    """
    norm, was_clipped = normalize_to_baseline(means, baseline_label)
    agents = list(means.columns)
    metrics = list(means.index)
    baseline_values = means[baseline_label]
    tick_labels = _radar_tick_labels(metrics, baseline_values)

    # Shared radial limit: at least 1.5, rounded up to the next 0.5
    r_max = max(1.5, float(np.ceil(norm.max().max() * 2) / 2))

    cmap = plt.get_cmap("tab10")
    colors = {a: cmap(i) for i, a in enumerate(agents)}

    panels = [[a] for a in agents] + [agents]
    titles = agents + ["All agents"]

    fig, axes = plt.subplots(2, 2, figsize=(12, 11), subplot_kw={"polar": True})
    flat = list(axes.flat)
    for ax, group, title in zip(flat, panels, titles):
        _draw_radar(ax, norm, group, title, colors, tick_labels, r_max)
    for ax in flat[len(panels):]:      # hide unused panels if < 3 agents
        ax.axis("off")
    flat[len(panels) - 1].legend(loc="upper right", bbox_to_anchor=(1.4, 1.15))

    note = ""
    if was_clipped.values.any():
        note = f"  |  values clipped at {RADAR_MAX_RATIO:g}x"
    fig.suptitle(
        f"Behavioral profile relative to {baseline_label} "
        f"(1.0 = baseline, outward = better){note}", fontsize=12)
    fig.tight_layout()
    path = os.path.join(out_dir, "behavioral_radars.png")
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    if save_individual:
        for group, title in zip(panels, titles):
            f, a = plt.subplots(figsize=(6, 6), subplot_kw={"polar": True})
            _draw_radar(a, norm, group, title, colors, tick_labels, r_max)
            a.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
            f.tight_layout()
            f.savefig(os.path.join(out_dir, f"radar_{title.replace(' ', '_')}.png"),
                      dpi=120, bbox_inches="tight")
            plt.close(f)

    norm.to_csv(os.path.join(out_dir, "behavioral_radar_normalized.csv"))
    if was_clipped.values.any():
        print("Note: these radar values were clipped at "
              f"{RADAR_MAX_RATIO:g}x:\n{was_clipped[was_clipped.any(axis=1)]}")
    return path


# ======================================================================
# Main
# ======================================================================

def main():
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(OUT_ROOT, f"eval_{timestamp}")
    os.makedirs(out_dir, exist_ok=True)
    saved = []

    # Record the run configuration for reproducibility
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        commit = "unknown"
    config = {"agents": AGENTS, "num_players": NUM_PLAYERS,
              "n_games": N_GAMES, "seeds": [SEEDS[0], SEEDS[-1]],
              "behavioral_metrics": list(BEHAVIORAL_METRICS),
              "git_commit": commit, "timestamp": timestamp}
    with open(os.path.join(out_dir, "run_config.json"), "w") as f:
        json.dump(config, f, indent=2)
    saved.append(os.path.join(out_dir, "run_config.json"))

    # Run simulations (same seeds for every agent)
    per_game = {}
    for label, spec in AGENTS.items():
        per_game[label] = evaluate_agent(label, spec)
        path = os.path.join(out_dir, f"per_game_{label}.csv")
        per_game[label].to_csv(path, index=False)
        saved.append(path)

    # ----- Part 1: summary statistics -----
    scores = score_summary_table(per_game)
    print("\n=== Summary statistics: scores ===")
    print(scores.round(2).to_string())
    scores.to_csv(os.path.join(out_dir, "summary_statistics.csv"))
    saved.append(os.path.join(out_dir, "summary_statistics.csv"))

    baseline_label = next(iter(AGENTS))
    paired = paired_score_differences(per_game, baseline_label)
    print(f"\n=== Paired score comparison (vs {baseline_label}, same seeds) ===")
    print(paired.round(3).to_string())
    paired.to_csv(os.path.join(out_dir, "paired_score_differences.csv"))
    saved.append(os.path.join(out_dir, "paired_score_differences.csv"))

    saved.append(plot_score_histograms(per_game, out_dir))

    # ----- Part 2: behavioral metrics -----
    means, stds = behavioral_summary_table(per_game)
    formatted = means.round(2).astype(str) + " (" + stds.round(2).astype(str) + ")"
    print("\n=== Behavioral metrics: per-game mean (std) ===")
    print(formatted.to_string())
    means.to_csv(os.path.join(out_dir, "behavioral_means.csv"))
    stds.to_csv(os.path.join(out_dir, "behavioral_stds.csv"))
    saved += [os.path.join(out_dir, "behavioral_means.csv"),
              os.path.join(out_dir, "behavioral_stds.csv")]

    saved.append(plot_behavioral_bars(means, stds, out_dir))
    saved.append(plot_behavioral_radars(means, out_dir, baseline_label))

    print("\nSaved:", *saved, sep="\n  ")


if __name__ == "__main__":
    main()
