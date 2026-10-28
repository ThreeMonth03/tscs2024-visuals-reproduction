"""The English presentation layer preserves data and group identifiers."""
import importlib.util
from pathlib import Path
import unittest

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("figure_helper", ROOT / "helpers/build_figures.py")
figures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(figures)


class EnglishFigureTests(unittest.TestCase):
    def test_aggregate_selection_keeps_scope_and_order(self):
        rows = [
            {"estimate_id": f"primary-{level}", "outcome": "photography_weekly",
             "factor": "age", "area": 0, "category": 1, "level": level,
             "estimate": level / 10}
            for level in reversed(range(1, 7))
        ]
        # A second area and a second response category must not enter this figure.
        rows += [dict(rows[0], estimate_id="other-area", area=1),
                 dict(rows[0], estimate_id="other-category", category=0)]
        renderer = figures.FigureRenderer(pd.DataFrame(rows), Path("unused"), plt, {})
        selected = renderer.select("photography_weekly", "age", area=0, category=1)
        self.assertEqual(selected.level.tolist(), list(range(1, 7)))
        self.assertEqual(renderer.used, {f"primary-{level}" for level in range(1, 7)})
        self.assertEqual(renderer.current_ids, renderer.used)

    def test_missing_group_stops_plotting(self):
        profiles = pd.DataFrame([
            {"estimate_id": "one-group", "outcome": "photography_weekly",
             "factor": "age", "area": 0, "category": 1, "level": 1}
        ])
        renderer = figures.FigureRenderer(profiles, Path("unused"), plt, {})
        with self.assertRaises(AssertionError):
            renderer.select("photography_weekly", "age")

    def test_count_labels_keep_the_original_count(self):
        self.assertEqual(figures.english_label("70以上（n=123）"), "70+ (n=123)")
        self.assertEqual(figures.english_label("小學及以下（n=45）"), "Primary or less (n=45)")

    def test_unknown_source_label_requires_review(self):
        with self.assertRaisesRegex(ValueError, "Untranslated figure label"):
            figures.english_label("新的分類")

    def test_display_translation_does_not_change_plotted_data_or_scales(self):
        fig, ax = plt.subplots()
        self.addCleanup(plt.close, fig)
        ax.errorbar([0, 1], [12.5, 77.2], yerr=[2, 3], label="分享給親友")
        ax.set_xticks([0, 1], ["小學及以下", "專科及以上"])
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.set_ylim(0, 102)
        ax.set_xlabel("教育程度")
        ax.set_ylabel("加權比例（%）")
        ax.legend()
        lines = [(line.get_xdata().copy(), line.get_ydata().copy()) for line in ax.lines]
        segments = [collection.get_segments() for collection in ax.collections]
        limits = (ax.get_xlim(), ax.get_ylim())
        figures.english_figure(fig, "education_frequency")
        for line, (x, y) in zip(ax.lines, lines, strict=True):
            np.testing.assert_array_equal(line.get_xdata(), x)
            np.testing.assert_array_equal(line.get_ydata(), y)
        for collection, original in zip(ax.collections, segments, strict=True):
            np.testing.assert_array_equal(collection.get_segments(), original)
        self.assertEqual((ax.get_xlim(), ax.get_ylim()), limits)
        self.assertEqual(ax.get_xlabel(), "Education")
        self.assertEqual(ax.get_xticklabels()[0].get_text(), "Primary\nor less")
        self.assertEqual(ax.get_legend().get_texts()[0].get_text(), "Sharing with family/friends")


if __name__ == "__main__":
    unittest.main()
