#!/usr/bin/env python3
"""Render nine research figures solely from published aggregate result tables.

The plotting functions preserve the study's selected estimates, group order,
confidence intervals and visual style. This renderer reads only aggregate estimates and performs no statistical
estimation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import warnings

import numpy as np
import pandas as pd

PROFILE_RELATIVE = "primary/descriptive_profiles.csv"

AGE = ["18–29", "30–39", "40–49", "50–59", "60–69", "70以上"]

EDU = ["小學及以下", "國初中", "高中職", "專科及以上"]

AREA = {0: "全體", 1: "數位成熟區", 2: "非數位成熟區"}

COLORS = ["#087f86", "#6d7584", "#cc8536", "#9684b1", "#d7dbdc", "#923e4d", "#c6b79f"]

LABELS = {"photography_weekly": "經常拍照", "video_recording_weekly": "經常錄影", "sharing_with_contacts_weekly": "經常分享給親友", "sharing_with_unspecified_audiences_weekly": "經常向不特定對象分享", "joint_sharing": "曾分享的對象組合", "personal_files_nonproduction": "回答不產製檔案", "personal_files_locations": "主要存放位置"}

EXPECTED_FIGURES = (
    "age_frequency", "education_frequency", "sharing_experience",
    "region_frequency", "region_other_frequency", "file_answers",
    "nonproduction", "nonproduction_regions", "file_locations",
)

ENGLISH_LABELS = {
    "70以上": "70+",
    "小學及以下": "Primary or less",
    "國初中": "Junior high",
    "高中職": "Senior high / vocational",
    "專科及以上": "Junior college or higher",
    "全體": "All adults",
    "數位成熟區": "Digitally mature areas",
    "非數位成熟區": "Non-mature areas",
    "拍照": "Taking photos",
    "錄影": "Recording videos",
    "分享給親友": "Sharing with family/friends",
    "向不特定對象分享": "Sharing with an unspecified audience",
    "加權比例（%）": "Weighted proportion (%)",
    "組內加權比例（%）": "Within-group weighted proportion (%)",
    "年齡組（歲）": "Age group (years)",
    "年齡組": "Age groups",
    "教育程度": "Education",
    "（a）拍攝": "(a) Taking photos and recording videos",
    "（b）分享": "(b) Sharing photos and videos",
    "（a）年齡組（歲）": "(a) Age groups (years)",
    "（b）教育程度": "(b) Education",
    "親友與不特定對象都曾分享": "Shared with both audiences",
    "只曾分享給親友": "Shared with family/friends only",
    "兩者皆未曾": "Shared with neither audience",
    "只曾向不特定對象分享": "Shared with an unspecified audience only",
    "原設備": "Original device",
    "個人電腦或硬碟": "Personal computer or hard drive",
    "其他媒體或列印": "Other media or printouts",
    "雲端": "Cloud storage",
    "其他": "Other",
    "不產製檔案": "Does not produce digital files",
    "不考慮保存": "Does not consider file preservation",
}

def english_label(text: str, *, horizontal_categories: bool = False) -> str:
    """Translate visible source labels, keeping counts and numeric text intact."""
    if text in ENGLISH_LABELS:
        translated = ENGLISH_LABELS[text]
        if horizontal_categories:
            translated = translated.replace("Senior high / vocational", "Senior high /\nvocational")
            translated = translated.replace("Junior college or higher", "Junior college\nor higher")
            translated = translated.replace("Primary or less", "Primary\nor less")
        return translated
    count_label = re.fullmatch(r"(.+)（n=(\d+)）", text)
    if count_label:
        return english_label(count_label[1]) + f" (n={count_label[2]})"
    if "／" in text:
        return " / ".join(english_label(part) for part in text.split("／"))
    if any("\u3400" <= character <= "\u9fff" for character in text):
        raise ValueError("Untranslated figure label: " + text)
    return text

def english_figure(fig, name: str) -> None:
    """Apply English text and spacing after the original numerical plot is built."""
    from matplotlib.text import Text

    # Education labels need two lines on horizontal axes. Tick formatters must
    # be updated, since a later layout draw regenerates their Text objects.
    for ax in fig.axes:
        xlabels = [english_label(label.get_text(), horizontal_categories=True)
                   for label in ax.get_xticklabels()]
        ylabels = [english_label(label.get_text()) for label in ax.get_yticklabels()]
        ax.set_xticks(ax.get_xticks(), xlabels)
        ax.set_yticks(ax.get_yticks(), ylabels)
    for artist in fig.findobj(Text):
        artist.set_text(english_label(artist.get_text()))

    # English labels are longer than the archived Chinese labels. Increase
    # space, while preserving data, scales, category order, colors and marks.
    sizes = {
        "age_frequency": (10.8, 4.4),
        "education_frequency": (10.8, 4.6),
        "sharing_experience": (10.8, 7.4),
        "region_frequency": (10.8, 6.5),
        "region_other_frequency": (10.8, 6.5),
        "file_answers": (10.8, 5.5),
        "nonproduction": (10.8, 4.4),
        "nonproduction_regions": (10.8, 4.5),
        "file_locations": (10.8, 7.4),
    }
    fig.set_size_inches(*sizes[name])

    if name in {"age_frequency", "education_frequency"}:
        for ax in fig.axes:
            legend = ax.get_legend()
            if legend is not None:
                legend.set_loc("upper center")
                legend.set_bbox_to_anchor((0.5, -0.24))
    if name in {"region_frequency", "region_other_frequency"}:
        for ax in fig.axes:
            title = ax.get_title(loc="left")
            activity, factor = title.rsplit(" / ", 1)
            ax.set_title(activity + "\n" + factor, loc="left", fontsize=12)

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def configure_font(requested: str, font_manager) -> tuple[str, Path]:
    candidate = Path(requested).expanduser()
    if candidate.is_file():
        font_path = candidate.resolve()
        font_manager.fontManager.addfont(str(font_path))
        family = font_manager.FontProperties(fname=str(font_path)).get_name()
    else:
        if candidate.suffix.lower() in {".otf", ".ttf", ".ttc"} or "/" in requested or "\\" in requested:
            raise FileNotFoundError("Requested font file does not exist: " + requested)
        family = requested
        try:
            font_path = Path(font_manager.findfont(font_manager.FontProperties(family=[family]), fallback_to_default=False)).resolve()
        except ValueError as exc:
            raise ValueError("Requested font family is unavailable; supply an installed font family or font file: " + family) from exc
    return family, font_path

def axes_format(ax, factor, ylabel="加權比例（%）"):
    labels = AGE if factor == "age" else EDU
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylim(0, 102)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_ylabel(ylabel)
    ax.set_xlabel("年齡組（歲）" if factor == "age" else "教育程度")
    ax.grid(axis="y", color="#e4e6e8", lw=.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    for sp in ["left", "bottom"]:
        ax.spines[sp].set_color("#aeb5ba")

class FigureRenderer:
    """Keep selections and output provenance local to one figure run."""

    def __init__(self, profiles: pd.DataFrame, output_dir: Path, pyplot, charmap: dict):
        self.profiles = profiles
        self.output_dir = output_dir
        self.plt = pyplot
        self.charmap = charmap
        self.used: set[str] = set()
        self.current_ids: set[str] = set()
        self.figures: dict[str, dict] = {}

    def finish(self, fig, name: str) -> None:
        from matplotlib.text import Text

        if name not in EXPECTED_FIGURES or name in self.figures:
            raise RuntimeError("Unexpected or repeated figure: " + name)
        english_figure(fig, name)
        texts = [artist for artist in fig.findobj(Text)
                 if artist.get_visible() and artist.get_text()]
        missing = sorted({character for artist in texts for character in artist.get_text()
                          if not character.isspace() and ord(character) not in self.charmap})
        if missing:
            raise ValueError("Requested font lacks figure characters: " + "".join(missing))
        with warnings.catch_warnings():
            warnings.filterwarnings("error", message="Glyph .* missing from font")
            fig.savefig(self.output_dir / f"{name}.pdf", bbox_inches="tight",
                        metadata={"CreationDate": None, "ModDate": None})
            fig.savefig(self.output_dir / f"{name}.png", dpi=150, bbox_inches="tight")
            self.plt.close(fig)
        self.figures[name] = {
            "selected_estimate_ids": sorted(self.current_ids),
            "selected_rows": len(self.current_ids),
            "axes": len(fig.axes), "text_artists": len(texts),
            "font_missing_characters": [],
            "display_labels": sorted({artist.get_text() for artist in texts}),
            "files": {f"{name}.{suffix}": digest(self.output_dir / f"{name}.{suffix}")
                      for suffix in ("pdf", "png")},
        }
        self.current_ids.clear()

    def select(self, outcome, factor='age', area=0, category=1):
        d = self.profiles[(self.profiles.outcome == outcome) & (self.profiles.factor == factor) & (self.profiles.area == area) & (self.profiles.category == category)].sort_values('level')
        assert len(d) == {'age': 6, 'education': 4, 'all': 1}[factor], (outcome, factor, area, category)
        self.used.update(d.estimate_id)
        self.current_ids.update(d.estimate_id)
        return d

    def line(self, ax, outcome, factor, area=0, color=None, label=None, ci=True, offset=0):
        d = self.select(outcome, factor, area)
        x = np.arange(len(d)) + offset
        y = d.estimate.to_numpy() * 100
        if ci:
            lo, hi = (d.conf_low.to_numpy() * 100, d.conf_high.to_numpy() * 100)
            ax.errorbar(x, y, yerr=[y - lo, hi - y], color=color, marker='o', ms=4, lw=1.5, elinewidth=0.8, capsize=2, label=label)
        else:
            ax.plot(x, y, color=color, marker='o', ms=4, lw=1.6, label=label)
        axes_format(ax, factor)

    def frequency_figure(self, factor, name):
        fig, axs = self.plt.subplots(1, 2, figsize=(7.6, 3.5), layout='constrained')
        for ax, outcomes, title in zip(axs, [('photography_weekly', 'video_recording_weekly'), ('sharing_with_contacts_weekly', 'sharing_with_unspecified_audiences_weekly')], ['（a）拍攝', '（b）分享']):
            for i, o in enumerate(outcomes):
                self.line(ax, o, factor, color=COLORS[i], label=LABELS[o].replace('經常', ''), offset=(i - 0.5) * 0.06)
            ax.set_title(title, loc='left', fontsize=12)
            ax.legend(loc='upper right', frameon=False, fontsize=10)
        self.finish(fig, name)

    def stacks(self, name, outcome, categories, labels, factors=('age', 'education'), colors=None, show_n=False, label_size=10, axis_label_size=11):
        colors = colors or COLORS[:len(categories)]
        fig, axs = self.plt.subplots(len(factors), 1, figsize=(7.6, 4.3 if len(factors) == 1 else 6.4), layout='constrained')
        axs = np.atleast_1d(axs)
        for j, (ax, factor) in enumerate(zip(axs, factors)):
            gs = AGE if factor == 'age' else EDU
            if show_n:
                counts = self.select(outcome, factor, category=categories[0]).n
                gs = [f'{label}（n={int(n)}）' for label, n in zip(gs, counts)]
            left = np.zeros(len(gs))
            for c, lab, color in zip(categories, labels, colors):
                vals = self.select(outcome, factor, category=c).estimate.to_numpy() * 100
                ax.barh(np.arange(len(gs)), vals, left=left, color=color, height=0.66, label=lab)
                for k, val in enumerate(vals):
                    if val >= 8:
                        ax.text(left[k] + val / 2, k, f'{val:.1f}', ha='center', va='center', fontsize=label_size, color='white' if color in [COLORS[0], COLORS[1], COLORS[5]] else '#17292f')
                left += vals
            assert np.allclose(left, 100)
            ax.set_yticks(range(len(gs)), gs)
            ax.invert_yaxis()
            ax.set_xlim(0, 100)
            ax.set_xticks([0, 20, 40, 60, 80, 100])
            ax.set_xlabel('組內加權比例（%）', fontsize=axis_label_size)
            ax.tick_params(labelsize=label_size)
            ax.set_title('（a）年齡組（歲）' if factor == 'age' else '（b）教育程度' if len(factors) > 1 else '教育程度', loc='left', fontsize=12)
            ax.spines[['top', 'right', 'left']].set_visible(False)
            if j == len(axs) - 1:
                ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.25), frameon=False, ncol=2 if len(labels) > 4 else 2, fontsize=label_size)
        self.finish(fig, name)

    def render(self):
        self.frequency_figure('age', 'age_frequency')
        self.frequency_figure('education', 'education_frequency')
        self.stacks('sharing_experience', 'joint_sharing', [1, 2, 3, 4], ['親友與不特定對象都曾分享', '只曾分享給親友', '兩者皆未曾', '只曾向不特定對象分享'])
        for name, outcomes in [('region_frequency', ['photography_weekly', 'sharing_with_contacts_weekly']), ('region_other_frequency', ['video_recording_weekly', 'sharing_with_unspecified_audiences_weekly'])]:
            fig, axs = self.plt.subplots(2, 2, figsize=(7.6, 5.05), layout='constrained')
            for row, o in enumerate(outcomes):
                for col, f in enumerate(['age', 'education']):
                    ax = axs[row, col]
                    for area, color in [(1, COLORS[0]), (2, COLORS[2])]:
                        self.line(ax, o, f, area, color, AREA[area], offset=(area - 1.5) * 0.07)
                    title = LABELS[o].replace('經常', '')
                    ax.set_title(title + ('／年齡組' if f == 'age' else '／教育程度'), loc='left', fontsize=13)
                    ax.tick_params(labelsize=11)
                    ax.xaxis.label.set_size(12)
                    ax.yaxis.label.set_size(12)
            handles, labels = axs[0, 0].get_legend_handles_labels()
            fig.legend(handles, labels, loc='outside upper center', ncol=2, frameon=False, fontsize=12)
            self.finish(fig, name)
        self.stacks('file_answers', 'personal_files_answers', list(range(1, 8)), ['原設備', '個人電腦或硬碟', '其他媒體或列印', '雲端', '其他', '不產製檔案', '不考慮保存'], factors=('education',), label_size=11, axis_label_size=12)
        for name, areas in [('nonproduction', [(0, COLORS[1])]), ('nonproduction_regions', [(1, COLORS[0]), (2, COLORS[2])])]:
            fig, axs = self.plt.subplots(1, 2, figsize=(7.6, 5.0 if name == 'nonproduction' else 3.8), layout='constrained')
            for ax, f in zip(axs, ['age', 'education']):
                for area, color in areas:
                    self.line(ax, 'personal_files_nonproduction', f, area, color, AREA[area], offset=0 if len(areas) == 1 else (area - 1.5) * 0.07)
                ax.set_title('年齡組' if f == 'age' else '教育程度', loc='left', fontsize=12)
                if name == 'nonproduction':
                    ax.tick_params(labelsize=11)
                    ax.xaxis.label.set_size(12)
                    ax.yaxis.label.set_size(12)
            if len(areas) > 1:
                handles, labels = axs[0].get_legend_handles_labels()
                fig.legend(handles, labels, loc='outside upper center', ncol=2, frameon=False, fontsize=12)
            self.finish(fig, name)
        self.stacks('file_locations', 'personal_files_locations', [1, 2, 3, 4], ['原設備', '個人電腦或硬碟', '其他媒體或列印', '雲端'], show_n=True, label_size=11, axis_label_size=12)


def build(results_root: Path, output_dir: Path, font: str) -> dict:
    """Render aggregate profiles and record exactly which rows were displayed."""
    if sys.flags.optimize or os.environ.get("PYTHONOPTIMIZE"):
        raise RuntimeError("Python optimization is unsupported; plotting assertions must remain enabled")
    results_root, output_dir = results_root.resolve(), output_dir.resolve()
    profiles_path = results_root / PROFILE_RELATIVE
    if not profiles_path.is_file():
        raise FileNotFoundError("Missing aggregate profiles: " + str(profiles_path))
    if output_dir.exists():
        raise FileExistsError("Refusing to overwrite a figure directory: " + str(output_dir))
    profiles = pd.read_csv(profiles_path)
    if len(profiles) != 1683 or not profiles.estimate_id.is_unique:
        raise ValueError("Expected the complete 1,683 unique primary-analysis profile rows")
    profiles_hash = digest(profiles_path)
    output_dir.mkdir(parents=True)
    os.environ["MPLCONFIGDIR"] = str(output_dir / ".matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.ft2font import FT2Font

    family, font_path = configure_font(font, font_manager)
    charmap = FT2Font(str(font_path)).get_charmap()
    plt.rcParams.update({"font.family": family, "font.size": 11, "xtick.labelsize": 10,
                         "ytick.labelsize": 10, "axes.unicode_minus": False, "pdf.fonttype": 3})
    renderer = FigureRenderer(profiles, output_dir, plt, charmap)
    try:
        renderer.render()
    finally:
        plt.close("all")
    if tuple(renderer.figures) != EXPECTED_FIGURES:
        raise AssertionError("Expected exactly the nine research figures")
    selected = profiles.set_index("estimate_id").loc[sorted(renderer.used)].reset_index()
    selection_path = output_dir / "selected_profiles.csv"
    selected.to_csv(selection_path, index=False, encoding="utf-8-sig", float_format="%.15g")
    if digest(profiles_path) != profiles_hash:
        raise AssertionError("Aggregate estimates changed while plotting")
    report = {
        "status": "pass", "statistical_reestimation": False,
        "manuscript_read": False, "tex_or_ppt_compiled": False,
        "renderer_sha256": digest(Path(__file__)),
        "input": {"path": PROFILE_RELATIVE, "sha256": profiles_hash,
                  "rows": len(profiles), "analysis": "primary"},
        "font": {"requested": font, "family": family,
                 "resolved_file": str(font_path), "sha256": digest(font_path)},
        "runtime": {"python": sys.version.split()[0], "numpy": np.__version__,
                    "pandas": pd.__version__, "matplotlib": matplotlib.__version__},
        "figures": renderer.figures, "figure_count": len(renderer.figures),
        "selected_rows": len(selected), "display_language": "en",
        "selected_profiles_sha256": digest(selection_path),
        "scope": "Nine research figures from published aggregate profiles. No survey statistics or sensitivity analyses are reestimated.",
        "qa": {"missing_font_characters": 0, "pdf_and_png_written": 18,
               "visual_review": "not performed by this program; inspect all nine PNGs"},
    }
    (output_dir / "figures_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True,
                        help="Directory containing published aggregate tables")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New directory for nine PDF/PNG figures and provenance")
    parser.add_argument("--font", required=True,
                        help="Font file (.otf/.ttf/.ttc) or installed family")
    args = parser.parse_args()
    report = build(args.results_root, args.output_dir, args.font)
    print(json.dumps({key: report[key] for key in (
        "status", "figure_count", "selected_rows", "statistical_reestimation", "runtime")},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
