"""Reestimate fixed survey analyses from semantic inputs supplied by a local adapter.

Only aggregate tables are written. The 141-test and 266-contrast families stay
fixed, including failed estimates, which use p=1 inside BY adjustment only.
"""
from __future__ import annotations
from pathlib import Path
import json
from collections.abc import Callable
import numpy as np
import pandas as pd
from scipy.stats import f, t, false_discovery_control
from helpers import survey_statistics as stats

ITEMS, KEYS, FIELDS = stats.ITEMS, stats.KEYS, stats.FIELDS
META = ['contrast_id', 'area', 'area_label', 'outcome', 'factor', 'left', 'right', 'left_label', 'right_label']
NUMERIC = ['estimate', 'std_error', 'conf_low', 'conf_high', 'statistic', 'df', 'p_value']


def correction(values, family_size):
    values = np.asarray(values, float)
    if len(values) != family_size:
        raise ValueError('Incomplete multiple-testing family')
    return false_discovery_control(np.nan_to_num(values, nan=1.0), method='by')


def domains(data):
    for area in range(3):
        geographic = np.ones(len(data), bool) if area == 0 else data.area.eq(area).to_numpy()
        for factor, levels in [('all', [0]), ('age', range(1, 7)), ('education', range(1, 5))]:
            for level in levels:
                mask = geographic if factor == 'all' else geographic & data[FIELDS[factor]].eq(level).to_numpy()
                yield area, factor, level, mask


def calibrate(base, data, targets):
    """Iterative proportional fitting to user-supplied population margins."""
    groups = []
    for factor, field in [('sex', 'sex_group'), ('age', 'age_group'),
                          ('education', 'education_group'), ('stratum', 'stratum')]:
        mapping = targets.get(factor)
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError('Calibration requires four complete population margins')
        levels = set(data[field].astype(str))
        if set(map(str, mapping)) != levels:
            raise ValueError('Calibration categories do not cover the analysis population')
        weights = np.asarray(list(mapping.values()), float)
        if not np.isfinite(weights).all() or np.any(weights <= 0):
            raise ValueError('Calibration targets must be finite and positive')
        weights = weights / weights.sum()
        groups.append([(data[field].astype(str).eq(str(level)).to_numpy(), float(target))
                       for level, target in zip(mapping, weights)])
    result = np.asarray(base, float).copy()
    result *= len(result) / result.sum()
    for _ in range(10000):
        for group in groups:
            for mask, target in group:
                total = result[mask].sum()
                if total <= 0:
                    raise ValueError('Empty calibration category')
                result[mask] *= len(result) * target / total
        error = max(abs(result[mask].sum() / len(result) - target)
                    for group in groups for mask, target in group)
        if error < 1e-10:
            return result
    raise ValueError('Calibration did not converge')


def _category_order(value):
    """Normalize numeric codes while retaining lexical order of composite labels."""
    text = str(value)
    try:
        return ((0, float(text)),)
    except ValueError:
        return ((1, text),)


class Design:
    def __init__(self, data, calibration_targets=None):
        self.data = data.reset_index(drop=True)
        units = self.data[KEYS].drop_duplicates()
        order = sorted(range(len(units)), key=lambda i: tuple(_category_order(units.iloc[i][field]) for field in KEYS))
        self.units = units.iloc[order].reset_index(drop=True)
        self.strata = self.units.stratum.to_numpy()
        self.counts = {s: int(sum(self.strata == s)) for s in set(self.strata)}
        if min(self.counts.values()) < 2:
            raise ValueError('At least two sampled clusters per stratum are required')
        self.df = len(self.units) - len(self.counts)
        if self.df <= 10:
            raise ValueError('The fixed adjusted models require more than ten design degrees of freedom')
        self.masks = [((self.data.stratum == r.stratum) & (self.data.cluster == r.cluster)).to_numpy()
                      for r in self.units.itertuples()]
        self.targets = calibration_targets
        self._weights = {}
        self._fits = {}
        self.X, self.ages = stats.matrix(self.data)
        self.prediction_targets = [(factor, level, *stats.matrix(self.data, **{factor: level}))
                                   for factor, levels in [('age', range(1, 7)), ('education', range(1, 5))]
                                   for level in levels]
        self.model_meta = pd.DataFrame([dict(item=item, factor=factor, level=level)
                                       for item in ITEMS for factor, level, *_ in self.prediction_targets])

    def weights(self, weight='primary', removed=(), calibrated=False):
        removed = tuple(sorted(removed))
        key = weight, removed, calibrated
        if key in self._weights:
            return self._weights[key]
        factors = np.ones(len(self.data))
        for stratum, count in self.counts.items():
            deleted = [j for j in removed if self.strata[j] == stratum]
            if deleted:
                if len(deleted) >= count:
                    raise ValueError('Empty sampling stratum')
                factors[self.data.stratum.to_numpy() == stratum] = count / (count - len(deleted))
                for j in deleted:
                    factors[self.masks[j]] = 0
        result = self.data[weight + '_weight'].to_numpy(float) * factors
        if calibrated:
            if self.targets is None:
                raise ValueError('calibration_targets_unavailable')
            result = calibrate(result, self.data, self.targets)
        self._weights[key] = result
        return result

    def replicates(self, weight='primary', outer=None, calibrated=False):
        removed = () if outer is None else (outer,)
        weights = [self.weights(weight, removed, calibrated)]
        if outer is not None and self.counts[self.strata[outer]] == 2:
            return np.array(weights), np.array([]), [], self.df - 1
        scales, deleted = [], [removed]
        for j in range(len(self.units)):
            if j == outer:
                continue
            count = self.counts[self.strata[j]] - int(outer is not None and self.strata[j] == self.strata[outer])
            scales.append((count - 1) / count)
            pair = tuple(sorted(removed + (j,)))
            weights.append(self.weights(weight, pair, calibrated))
            deleted.append(pair)
        return np.array(weights), np.array(scales), deleted, self.df - int(outer is not None)

    def model_fit(self, weight='primary', removed=(), calibrated=False):
        key = weight, tuple(sorted(removed)), calibrated
        if key in self._fits:
            return self._fits[key]
        weights = self.weights(*key)
        values = []
        for item in ITEMS:
            valid = self.data[item].between(1, 7 if item == 'personal_files' else 6).to_numpy()
            y = (self.data[item].eq(6) if item == 'personal_files' else self.data[item].between(1, 3)).to_numpy(float)
            try:
                beta, boundary, _ = stats.fit_boundary(self.X, self.ages, y, weights, valid)
                values.extend(float(np.average(stats.predict(P, ages, beta, boundary), weights=weights))
                              for _, _, P, ages in self.prediction_targets)
            except (ValueError, np.linalg.LinAlgError):
                values.extend([np.nan] * 10)
        result = np.array(values)
        self._fits[key] = result
        return result


def descriptives(design, weights, scales, df):
    data = design.data
    rows = []
    for outcome, item, categories, y, valid, _ in stats.outcomes(data):
        for area, factor, level, group in domains(data):
            mask = group & valid
            denominators = weights[:, mask].sum(1)
            w = weights[0, mask]
            for category in categories:
                event = mask & (y == category)
                numerators = weights[:, event].sum(1)
                p = np.divide(numerators, denominators, out=np.full(len(weights), np.nan), where=denominators > 0)
                variance = float(np.sum(scales * (p[1:] - p[0]) ** 2))
                interval = stats.intervals(np.array([p[0]]), np.array([variance]), df, True)
                rows.append(dict(estimate_id=f'D|{outcome}|{area}|{factor}|{level}|{category}',
                    outcome=outcome, item=item, area=area, factor=factor, level=level, category=category,
                    n=int(mask.sum()), event_n=int(event.sum()), weighted_denominator=float(w.sum()),
                    effective_n=float(w.sum() ** 2 / (w @ w)) if len(w) else np.nan,
                    psus=len(data.loc[mask, KEYS].drop_duplicates()),
                    event_psus=len(data.loc[event, KEYS].drop_duplicates()),
                    interval_status=('boundary_point_no_interval' if p[0] in [0, 1]
                                     else 'estimated' if np.isfinite(p).all() else 'empty_domain'),
                    **{k: float(v[0]) if isinstance(v, np.ndarray) else v for k, v in interval.items()}))
    return pd.DataFrame(rows)


def omnibus(design, weights, scales, df, detail=True):
    data = design.data
    rows = []
    dimensions = [(factor, area) for area in range(3) for factor in ['age', 'education']] + [('region', 0)]
    for outcome, item, categories, y, valid, role in stats.outcomes(data):
        for factor, area in dimensions:
            field, levels = dict(age=('age_group', range(1, 7)), education=('education_group', range(1, 5)),
                                 region=('area', [1, 2]))[factor]
            group = data[field].to_numpy()
            mask = valid & (np.ones(len(data), bool) if area == 0 else data.area.eq(area).to_numpy())
            matrix = np.column_stack([mask & (group == level) & (y == category)
                                      for level in levels for category in categories]).astype(float)
            denominator = weights[:, mask].sum(1)
            probabilities = np.divide(weights @ matrix, denominator[:, None],
                                      out=np.full((len(weights), matrix.shape[1]), np.nan), where=denominator[:, None] > 0)
            row = dict(test_id=f'A|{outcome}|{factor}|{area}', layer='eda', outcome=outcome,
                       item=item, factor=factor, area=area)
            if detail:
                n = matrix.sum(0).astype(int)
                tab = n.reshape(len(levels), len(categories))
                expected = np.outer(tab.sum(1), tab.sum(0)) / max(mask.sum(), 1)
                row.update(outcome_role=role, n=int(mask.sum()), psus=len(data.loc[mask, KEYS].drop_duplicates()),
                           zero_cells=int((n == 0).sum()), cells_under_5=int((n < 5).sum()),
                           expected_cells_under_5=int((expected < 5).sum()),
                           nominal_df=(len(levels) - 1) * (len(categories) - 1))
            try:
                if not np.all(denominator > 0):
                    raise ValueError('empty_replicate_domain')
                covariance = stats.cov(probabilities[0], probabilities[1:], scales)
                result = stats.rao_scott(probabilities[0], covariance, len(levels), len(categories), int((mask & (weights[0] > 0)).sum()), design_df=df)
                row.update(status='estimated', **result)
            except (ValueError, np.linalg.LinAlgError) as error:
                row.update(status=str(error), p_value=np.nan, statistic=np.nan)
            rows.append(row)
    if len(rows) != 91:
        raise RuntimeError('The omnibus specification must contain 91 tests')
    return rows


def model_inference(design, values, scales, df, detailed=False, weight='primary'):
    meta = design.model_meta
    covariance = stats.cov(values[0], values[1:], scales)
    model_df = df - 10
    profiles = meta.copy()
    if detailed:
        n, empty_mass = {}, {}
        for item in ITEMS:
            valid = design.data[item].between(1, 7 if item == 'personal_files' else 6).to_numpy()
            _, mass = stats.support(design.data, valid, item, design.weights(weight))
            empty_mass[item] = mass
            n[item] = int(valid.sum())
        profiles['n'] = [n[r.item] for r in meta.itertuples()]
        profiles['empty_cell_target_weight'] = [empty_mass[r.item][(r.factor, r.level)] for r in meta.itertuples()]
        for key, val in stats.intervals(values[0], covariance.diagonal(), model_df, True).items():
            profiles[key] = val
    tests = []
    for item in ITEMS:
        for factor, levels, reference in [('age', range(2, 7), 1), ('education', range(1, 4), 4)]:
            selections = meta.item.eq(item) & meta.factor.eq(factor)
            matrix = []
            for level in levels:
                matrix.append((selections & meta.level.eq(level)).to_numpy(float)
                              - (selections & meta.level.eq(reference)).to_numpy(float))
            for level, contrast in list(zip(levels, matrix)) + [('omnibus', np.array(matrix))]:
                individual = level != 'omnibus'
                name = f'{level}_minus_{reference}' if individual else 'omnibus'
                row = dict(test_id=f'P|{item}|{factor}|{name}',
                           layer='probability_contrast' if individual else 'probability_omnibus',
                           item=item, factor=factor)
                indexes = np.flatnonzero(contrast != 0) if individual else np.flatnonzero(np.any(contrast != 0, axis=0))
                local = contrast[indexes] if individual else contrast[:, indexes]
                z = local @ values[0, indexes]
                V = local @ covariance[np.ix_(indexes, indexes)] @ local.T
                if detailed and individual:
                    row.update(level=level, reference=reference,
                               **stats.intervals(float(z), float(V), model_df))
                elif not detailed or not individual:
                    row['denominator_df'] = model_df
                try:
                    if not np.isfinite(values[:, indexes]).all():
                        raise ValueError('model_fit_failed_in_full_or_nested_replicate')
                    if individual:
                        if V <= 0 or not np.isfinite(V):
                            raise ValueError('singular_covariance')
                        statistic = float(z / np.sqrt(V))
                        p = float(2 * t.sf(abs(statistic), model_df))
                    else:
                        if not np.isfinite(V).all() or np.linalg.matrix_rank(V) != len(z):
                            raise ValueError('singular_covariance')
                        statistic = float(z @ np.linalg.solve(V, z) / len(z))
                        p = float(f.sf(statistic, len(z), model_df))
                        if detailed:
                            row['numerator_df'] = len(z)
                    row.update(status='estimated', statistic=statistic, p_value=p)
                except (ValueError, np.linalg.LinAlgError) as error:
                    row.update(status=str(error), p_value=np.nan, statistic=np.nan)
                tests.append(row)
    return profiles, tests


def family(design, weight='primary', outer=None, calibrated=False, detailed=False):
    weights, scales, deleted, df = design.replicates(weight, outer, calibrated)
    if len(scales) == 0:
        # Fixed metadata are generated independently of the observed results.
        rows = [dict(test_id=f'A|{outcome}|{factor}|{area}', layer='eda', item=item, outcome=outcome,
                     factor=factor, area=area) for outcome, item, *_ in stats.outcomes(design.data)
                for factor, area in [(fac, area) for area in range(3) for fac in ['age', 'education']] + [('region', 0)]]
        for item in ITEMS:
            for factor, levels, ref in [('age', range(2, 7), 1), ('education', range(1, 4), 4)]:
                rows.extend(dict(test_id=f'P|{item}|{factor}|{level}_minus_{ref}', layer='probability_contrast',
                                 item=item, factor=factor) for level in levels)
                rows.append(dict(test_id=f'P|{item}|{factor}|omnibus', layer='probability_omnibus', item=item, factor=factor))
        result = pd.DataFrame(rows)[['test_id', 'layer', 'item', 'factor']]
        result['status'] = 'singleton_stratum_after_outer_deletion'
        for col in ['p_value', 'q_by_141', 'statistic']:
            result[col] = np.nan
        return result, None, None
    values = np.array([design.model_fit(weight, rem, calibrated) for rem in deleted])
    profiles, model_tests = model_inference(design, values, scales, df, detailed, weight)
    result = pd.DataFrame(omnibus(design, weights, scales, df, detailed) + model_tests)
    if len(result) != 141 or not result.test_id.is_unique:
        raise RuntimeError('The complete family must contain 141 unique tests')
    result['q_by_141'] = correction(result.p_value, 141)
    result.loc[result.status.ne('estimated'), 'q_by_141'] = np.nan
    if detailed:
        result['method'] = result.layer.map({'eda': 'Rao–Scott F', 'probability_contrast': f'JKn t({df - 10})',
                                           'probability_omnibus': 'Probability Wald F'})
        description = descriptives(design, weights, scales, df)
    else:
        description = None
    return result, profiles, description


def contrast_results(design, specs, weight='primary', outer=None):
    data = design.data
    common = (data.sharing_with_contacts.between(1, 6) & data.sharing_with_unspecified_audiences.between(1, 6)).to_numpy()
    outcomes = {item + '_weekly': (data[item].between(1, 6).to_numpy(), data[item].between(1, 3).to_numpy()) for item in ITEMS[:4]}
    outcomes.update(personal_files_nonproduction=(data.personal_files.between(1, 7).to_numpy(), data.personal_files.eq(6).to_numpy()),
                    personal_files_original=(data.personal_files.between(1, 4).to_numpy(), data.personal_files.eq(1).to_numpy()),
                    kin_only=(common, (data.sharing_with_contacts.between(1, 5) & data.sharing_with_unspecified_audiences.eq(6)).to_numpy()),
                    neither=(common, (data.sharing_with_contacts.eq(6) & data.sharing_with_unspecified_audiences.eq(6)).to_numpy()))
    keys, numerators, denominators = [], [], []
    for row in specs.itertuples():
        for level in [row.left, row.right]:
            key = row.area, row.outcome, row.factor, level
            if key in keys:
                continue
            valid, event = outcomes[row.outcome]
            mask = valid & data[FIELDS[row.factor]].eq(level).to_numpy()
            if row.area:
                mask &= data.area.eq(row.area).to_numpy()
            keys.append(key)
            denominators.append(mask)
            numerators.append(mask & event)
    num, den = np.array(numerators, float).T, np.array(denominators, float).T
    left = np.array([keys.index((r.area, r.outcome, r.factor, r.left)) for r in specs.itertuples()])
    right = np.array([keys.index((r.area, r.outcome, r.factor, r.right)) for r in specs.itertuples()])
    weights, scales, _, df = design.replicates(weight, outer)
    denominator = weights @ den
    means = np.divide(weights @ num, denominator, out=np.full_like(denominator, np.nan), where=denominator > 0)
    delta = means[:, left] - means[:, right]
    result = specs.copy()
    result['estimate'] = delta[0]
    if len(scales) == 0:
        for column in NUMERIC[1:] + ['q_by_266']:
            result[column] = np.nan
        result['status'] = 'singleton_stratum_after_outer_deletion'
    else:
        se = np.sqrt(np.sum(scales[:, None] * (delta[1:] - delta[0]) ** 2, axis=0))
        ok = np.isfinite(delta).all(0) & np.isfinite(se) & (se > 0)
        statistic = np.divide(delta[0], se, out=np.full(266, np.nan), where=ok)
        result['std_error'] = np.where(ok, se, np.nan)
        result['df'] = df
        result['statistic'] = statistic
        result['p_value'] = 2 * t.sf(abs(statistic), df)
        result['conf_low'] = delta[0] - t.ppf(.975, df) * result.std_error
        result['conf_high'] = delta[0] + t.ppf(.975, df) * result.std_error
        result['q_by_266'] = np.where(ok, correction(result.p_value, 266), np.nan)
        result['status'] = np.where(ok, 'estimated', 'undefined_variance_or_replicate')
    return result


def summarize_contrasts(results, expected_deletions):
    rows = []
    for _, group in results.groupby('contrast_id', sort=False):
        main = group[group.scenario.eq('primary')].iloc[0]
        alternative = group[group.scenario.eq('alternative')].iloc[0]
        deleted = group[group.scenario.str.startswith('delete_')]
        valid = deleted[deleted.status.eq('estimated')]
        row = {key: main[key] for key in META}
        for prefix, source in [('primary', main), ('alternative', alternative)]:
            for col in NUMERIC + ['q_by_266']:
                row[prefix + '_' + col] = source[col]
        row.update(weight_change_pp=100 * (alternative.estimate - main.estimate),
                   weight_direction_reversed=bool(alternative.estimate * main.estimate < 0),
                   deletion_estimable=len(valid), deletion_significant=int(valid.q_by_266.lt(.05).sum()),
                   deletion_estimate_min=deleted.estimate.min(), deletion_estimate_max=deleted.estimate.max(),
                   deletion_max_change_pp=100 * abs(deleted.estimate - main.estimate).max(),
                   deletion_direction_reversals=int((deleted.estimate * main.estimate < 0).sum()),
                   deletion_q_min=valid.q_by_266.min(), deletion_q_max=valid.q_by_266.max())
        row['supported_all_checks'] = bool(main.q_by_266 < .05 and alternative.q_by_266 < .05
            and alternative.estimate * main.estimate > 0 and len(valid) == expected_deletions
            and row['deletion_significant'] == expected_deletions and row['deletion_direction_reversals'] == 0
            and expected_deletions > 0)
        rows.append(row)
    return pd.DataFrame(rows)


def location_profiles(descriptions):
    rows = []
    ages = {1:'18–29歲',2:'30–39歲',3:'40–49歲',4:'50–59歲',5:'60–69歲',6:'70歲以上'}
    areas = {0:'全體',1:'數位成熟區',2:'非數位成熟區'}
    for scenario, table in descriptions.items():
        table = table[table.outcome.eq('personal_files_locations') & table.factor.eq('age')]
        for r in table.itertuples():
            rows.append(dict(scenario=scenario, area=r.area, area_label=areas[r.area], level=r.level,
                label=ages[r.level], category=r.category, n=r.n, event_n=r.event_n, psu_n=r.psus,
                event_psu_n=r.event_psus, kish_n=r.effective_n, estimate=r.estimate, std_error=r.std_error,
                boundary=bool(r.estimate in [0, 1])))
    return pd.DataFrame(rows)


def run_analysis(data: pd.DataFrame, output_dir: Path, *, calibration_targets=None,
                 sensitivity=True, progress: Callable[[str], None] | None=None):
    """Compute fresh tables. The optional extra calibration is never substituted.

    ``output_dir`` must not exist. Every input variable is a semantic field
    produced by the local SAV adapter. No survey records or source identifiers
    are written to disk by this estimator.
    """
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError('Choose a new output directory')
    if not sensitivity:
        raise ValueError('The public workflow retains every prespecified sensitivity scenario')
    design = Design(data, calibration_targets)
    specs = pd.DataFrame(json.loads(Path(__file__).with_name('survey_comparisons.json').read_text()))
    if len(specs) != 266 or not specs.contrast_id.is_unique:
        raise ValueError('The fixed contrast specification must contain 266 unique comparisons')
    aggregate_root = output / 'aggregates'
    for kind in ['primary', 'alternative', 'contrasts']:
        (aggregate_root / kind).mkdir(parents=True)
    def write(relative, frame):
        frame.to_csv(aggregate_root / relative, index=False, float_format='%.15g')
    def notify(message):
        if progress is not None:
            progress(message)
    tables, scenario_frames, contrasts, descriptions = {}, [], [], {}
    for name in ['primary', 'alternative']:
        notify('Estimating ' + name + ' weights')
        formal, profiles, description = family(design, weight=name, detailed=True)
        tables[name] = formal
        descriptions[name] = description
        write(f'{name}/formal_tests.csv', formal)
        write(f'{name}/adjusted_profiles.csv', profiles)
        write(f'{name}/descriptive_profiles.csv', description)
        contrasts.append(contrast_results(design, specs, name).assign(scenario=name))
    # The archived omnibus sensitivity table retains an additional calibration
    # diagnostic; the official alternative-weight analysis is a separate table.
    primary_scenario, _, _ = family(design)
    scenario_frames.append(primary_scenario.assign(scenario='primary'))
    if calibration_targets is not None:
        notify('Estimating supplied population calibration')
        calibrated, _, _ = family(design, calibrated=True)
    else:
        calibrated = primary_scenario.copy()
        for column in calibrated.select_dtypes(include='number').columns:
            if column != 'area':
                calibrated[column] = np.nan
        calibrated['status'] = 'calibration_targets_unavailable'
    scenario_frames.append(calibrated.assign(scenario='alternative'))
    for outer in range(len(design.units)):
        notify(f'Checking deletion {outer + 1} of {len(design.units)}')
        label = f'delete_{outer + 1:02d}'
        result, _, _ = family(design, outer=outer)
        scenario_frames.append(result.assign(scenario=label))
        contrasts.append(contrast_results(design, specs, outer=outer).assign(scenario=label))
    all_contrasts = pd.concat(contrasts, ignore_index=True)
    expected_deletions = sum(design.counts[stratum] > 2 for stratum in design.strata)
    summary = summarize_contrasts(all_contrasts, expected_deletions)
    write('primary/scenario_tests.csv', pd.concat(scenario_frames, ignore_index=True))
    write('contrasts/all_scenarios.csv', all_contrasts)
    write('contrasts/contrast_summary.csv', summary)
    write('contrasts/location_profiles.csv', location_profiles(descriptions))
    report = dict(status='pass', statistical_reestimation=True, input_estimates='user_supplied_survey',
                  observations=len(data), strata=len(design.counts), sampled_clusters=len(design.units),
                  design_df=design.df, omnibus_family=141, contrast_family=266,
                  scenarios=2 + len(design.units), estimable_deletion_designs=expected_deletions,
                  calibration_available=calibration_targets is not None,
                  aggregate_root=str(aggregate_root),
                  scenario_definitions={
                      'primary/scenario_tests.csv:alternative': 'Additional calibration to supplied population margins',
                      'alternative/* and contrasts/*:alternative': 'Supplied alternative survey weights'},
                  respondent_data_exported=False)
    (output / 'analysis_report.json').write_text(json.dumps(report, indent=2) + '\n')
    notify('Fresh aggregate estimates completed')
    return report
