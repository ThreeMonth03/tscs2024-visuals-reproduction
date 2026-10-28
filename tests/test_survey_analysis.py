"""Numerical and boundary checks with artificial records only."""
from pathlib import Path
import json
import unittest
import numpy as np
import pandas as pd
from helpers import survey_statistics as stats
from helpers.survey_analysis import Design, calibrate, correction, contrast_results, descriptives, omnibus


def artificial_records():
    rng = np.random.default_rng(530)
    n = 240
    data = pd.DataFrame({
        'age_group': np.tile(np.arange(1, 7), n // 6),
        'education_group': np.tile(np.arange(1, 5), n // 4),
        'sex_group': rng.integers(1, 3, n), 'area': rng.integers(1, 3, n),
        'stratum': np.repeat(np.arange(4), n // 4),
        'cluster': np.tile(np.repeat(np.arange(6), 10), 4),
        'primary_weight': rng.uniform(.4, 2, n),
        'alternative_weight': rng.uniform(.5, 1.9, n),
        'phone_holder': rng.integers(0, 2, n),
    })
    for item in stats.ITEMS:
        data[item] = rng.integers(1, 8 if item == 'personal_files' else 7, n)
    return data


class EstimatorTests(unittest.TestCase):
    def test_rao_scott_reduces_to_srs(self):
        table = np.array([[40., 20., 10.], [30., 60., 40.]])
        p = table.ravel() / table.sum()
        covariance = (np.diag(p) - np.outer(p, p)) / table.sum()
        result = stats.rao_scott(p, covariance, 2, 3, table.sum(), design_df=30)
        self.assertAlmostEqual(result['design_effect_min'], 1)
        self.assertAlmostEqual(result['design_effect_max'], 1)
        self.assertAlmostEqual(result['numerator_df'], 2)
        self.assertAlmostEqual(result['denominator_df'], 60)
        alternative = stats.rao_scott(p, covariance, 2, 3, table.sum(), basis='helmert', design_df=30)
        self.assertAlmostEqual(result['p_value'], alternative['p_value'])

    def test_by_keeps_unestimable_comparisons_in_family(self):
        p = np.array([.001, .03, np.nan, .03, .8])
        actual = correction(p, 5)
        filled = np.nan_to_num(p, nan=1)
        index = np.argsort(filled)
        raw = filled[index] * 5 * sum(1 / np.arange(1, 6)) / np.arange(1, 6)
        expected = np.empty(5)
        expected[index] = np.minimum(1, np.minimum.accumulate(raw[::-1])[::-1])
        np.testing.assert_allclose(actual, expected)
        with self.assertRaises(ValueError):
            correction(p, 266)

    def test_jkn_weights_and_nested_scaling(self):
        data = artificial_records()
        design = Design(data)
        weights, scales, deleted, df = design.replicates()
        self.assertEqual((weights.shape[0], df), (25, 20))
        np.testing.assert_allclose(scales, 5 / 6)
        mask = design.masks[0]
        other = (data.stratum == 0) & ~mask
        np.testing.assert_array_equal(weights[1, mask], 0)
        np.testing.assert_allclose(weights[1, other], data.primary_weight[other] * 6 / 5)
        nested, nested_scales, _, nested_df = design.replicates(outer=0)
        self.assertEqual(nested_df, 19)
        np.testing.assert_allclose(nested_scales[:5], 4 / 5)
        np.testing.assert_allclose(nested_scales[5:], 5 / 6)
        self.assertEqual(len(deleted), 25)

    def test_cluster_numbering_survives_string_labels(self):
        data = artificial_records()
        data['stratum'] = data.stratum.replace({0: 2, 1: 10, 2: 19, 3: 3})
        numeric = Design(data)
        labelled = data.copy()
        labelled['stratum'] = labelled.stratum.astype(str)
        labelled['cluster'] = labelled.stratum + ':unit:' + labelled.cluster.astype(str)
        strings = Design(labelled)
        for first, second in zip(numeric.masks, strings.masks):
            np.testing.assert_array_equal(first, second)

    def test_composite_cluster_order_retains_fixed_scenario_numbers(self):
        data = artificial_records()
        data['cluster'] = data.stratum.astype(str) + ':unit:' + data.cluster.replace({1: 10}).astype(str)
        expected = data[['stratum', 'cluster']].drop_duplicates().sort_values(['stratum', 'cluster']).reset_index(drop=True)
        design = Design(data)
        pd.testing.assert_frame_equal(design.units, expected)
        labelled = data.copy()
        labelled['stratum'] = labelled.stratum.astype(str)
        other = Design(labelled)
        for first, second in zip(design.masks, other.masks):
            np.testing.assert_array_equal(first, second)

    def test_outer_deletion_uses_active_sample_size(self):
        data = artificial_records()
        design = Design(data)
        weights, scales, _, df = design.replicates(outer=0)
        rows = omnibus(design, weights, scales, df, detail=False)
        result = next(row for row in rows if row['test_id'] == 'A|photography_weekly|age|0')
        valid = data.photography.between(1, 6).to_numpy()
        y = data.photography.between(1, 3).to_numpy()
        matrix = np.column_stack([valid & data.age_group.eq(level).to_numpy() & (y == category)
                                  for level in range(1, 7) for category in [0, 1]])
        p = weights[0] @ matrix / weights[0, valid].sum()
        table = p.reshape(6, 2)
        expected = np.outer(table.sum(1), table.sum(0))
        n = int((valid & (weights[0] > 0)).sum())
        pearson = float(n * np.sum((table - expected) ** 2 / expected))
        self.assertAlmostEqual(result['pearson_statistic'], pearson)
        self.assertLess(n, len(data))

    def test_calibration_changes_group_weights_not_records(self):
        data = artificial_records()
        original = data.copy(deep=True)
        targets = {factor: data[field].astype(str).value_counts(normalize=True).to_dict()
                   for factor, field in [('age','age_group'),('education','education_group'),
                                        ('sex','sex_group'),('stratum','stratum')]}
        result = calibrate(data.primary_weight, data, targets)
        for factor, field in [('age','age_group'),('education','education_group'),('sex','sex_group'),('stratum','stratum')]:
            for level, expected in targets[factor].items():
                self.assertAlmostEqual(result[data[field].astype(str).eq(level)].sum()/len(data), expected, places=9)
        pd.testing.assert_frame_equal(data, original)
        targets['sex'] = {'1': 1}
        with self.assertRaises(ValueError):
            calibrate(data.primary_weight, data, targets)

    def test_proportions_use_the_item_denominator(self):
        data = artificial_records()
        data.loc[:9, 'photography'] = 8
        data.loc[10:19, 'personal_files'] = 7
        design = Design(data)
        weights, scales, _, df = design.replicates()
        table = descriptives(design, weights, scales, df).set_index('estimate_id')
        row = table.loc['D|photography_weekly|0|all|0|1']
        valid = data.photography.between(1, 6)
        event = data.photography.between(1, 3)
        expected = data.primary_weight[valid & event].sum()/data.primary_weight[valid].sum()
        self.assertEqual(row.n, int(valid.sum()))
        self.assertAlmostEqual(row.estimate, expected)
        location = table.loc['D|personal_files_locations|0|all|0|1']
        self.assertEqual(location.n, int(data.personal_files.between(1, 4).sum()))

    def test_fixed_contrasts_reestimated_from_supplied_values(self):
        data = artificial_records()
        specs = pd.DataFrame(json.loads((Path(__file__).parents[1]/'helpers/survey_comparisons.json').read_text()))
        first = contrast_results(Design(data), specs)
        changed = data.copy()
        changed.loc[changed.age_group.eq(6), 'photography'] = 6
        second = contrast_results(Design(changed), specs)
        cid = 'C|photography_weekly|age|6_minus_1'
        a = first.set_index('contrast_id').loc[cid]
        b = second.set_index('contrast_id').loc[cid]
        self.assertNotEqual(a.estimate, b.estimate)
        self.assertEqual(len(first), 266)
        self.assertEqual(len(second), 266)
        self.assertTrue(first.contrast_id.is_unique)


if __name__ == '__main__':
    unittest.main()
