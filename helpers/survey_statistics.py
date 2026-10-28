"""Survey estimators with explicit semantic inputs and no source-file schema.

Second-order Rao–Scott F tests use the replicate covariance. Adjusted profiles
use weighted logistic regression and population marginal standardization.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.linalg import eigvalsh, helmert
from scipy.optimize import linprog, minimize
from scipy.special import expit, logit
from scipy.stats import f, t, false_discovery_control

ITEMS = ['photography', 'video_recording', 'sharing_with_contacts',
         'sharing_with_unspecified_audiences', 'personal_files']
KEYS = ['stratum', 'cluster']
FIELDS = {'age': 'age_group', 'education': 'education_group', 'sex': 'sex_group'}


def ratio(y, mask, w):
    den = w[mask].sum()
    return float(w[mask] @ y[mask] / den) if den > 0 else np.nan

def fit(X, y, w, linear=False, verify=False):
    if np.linalg.matrix_rank(X[w > 0]) != X.shape[1]:
        raise ValueError('Rank deficient')
    if linear:
        b = np.linalg.lstsq(X * np.sqrt(w)[:, None], y * np.sqrt(w), rcond=None)[0]
        return (b, {'out_of_bounds': int(((X @ b < 0) | (X @ b > 1)).sum())})
    b = np.zeros(X.shape[1])
    b[0] = logit(np.clip(np.average(y, weights=w), 1e-06, 1 - 1e-06))

    def objective(z):
        return float(np.sum(w * (np.logaddexp(0, X @ z) - y * (X @ z))))
    for iteration in range(100):
        p = expit(X @ b)
        score = X.T @ (w * (y - p))
        h = X.T @ ((w * p * (1 - p))[:, None] * X)
        step = np.linalg.solve(h, score)
        rate = 1.0
        prev = objective(b)
        while objective(b + rate * step) > prev + 1e-10 and rate > 1e-08:
            rate *= 0.5
        b += rate * step
        if np.max(abs(score)) / max(w.sum(), 1) < 1e-10:
            break
    else:
        raise ValueError('Logistic convergence failure')
    score = X.T @ (w * (y - expit(X @ b)))
    cond = np.linalg.cond(h)
    if np.max(abs(b)) > 25 or cond > 1000000000000.0 or np.max(abs(score)) / w.sum() > 1e-08:
        raise ValueError('Unstable logistic fit')
    check = 0.0
    if verify:
        z = minimize(objective, b + 0.02 * np.sin(np.arange(len(b))), jac=lambda z: X.T @ (w * (expit(X @ z) - y)), hess=lambda z: X.T @ ((w * expit(X @ z) * (1 - expit(X @ z)))[:, None] * X), method='trust-exact', options={'gtol': 1e-08})
        check = float(np.max(abs(expit(X @ z.x) - expit(X @ b))))
        assert check < 1e-06, check
    return (b, dict(iterations=iteration + 1, condition=cond, max_score=float(np.max(abs(score))), independent_prediction_error=check))

def intervals(value, var, df, probability=False):
    se = np.sqrt(np.maximum(var, 0))
    half = t.ppf(0.975, df) * se
    low = value - half
    high = value + half
    if probability:
        good = (value > 0) & (value < 1) & (se > 0)
        low = np.full(len(value), np.nan)
        high = low.copy()
        lh = t.ppf(0.975, df) * se[good] / (value[good] * (1 - value[good]))
        low[good] = expit(logit(value[good]) - lh)
        high[good] = expit(logit(value[good]) + lh)
    return dict(estimate=value, std_error=se, conf_low=low, conf_high=high, denominator_df=df)

def cov(full, reps, scales):
    delta = reps - full
    return delta.T @ (scales[:, None] * delta)

def separation_margin(X, y, w):
    """LP checks existence of a complete/quasi separator, not an arbitrary beta cap."""
    signed = X[w > 0] * (2 * y[w > 0] - 1)[:, None]
    fit = linprog(-signed.mean(0), A_ub=-signed, b_ub=np.zeros(len(signed)), bounds=[(-1.0, 1.0)] * X.shape[1], method='highs')
    if not fit.success:
        raise ValueError('separation_diagnostic_failed: ' + fit.message)
    return float(-fit.fun)

def contrast_basis(nr, nc, method):
    if method == 'helmert':
        return np.kron(helmert(nr).T, helmert(nc).T)
    rows = np.repeat(np.arange(nr), nc)
    cols = np.tile(np.arange(nc), nr)
    main = np.column_stack([np.ones(nr * nc)] + [rows == j for j in range(1, nr)] + [cols == j for j in range(1, nc)])
    interaction = np.column_stack([(rows == j) & (cols == k) for j in range(1, nr) for k in range(1, nc)])
    q, _ = np.linalg.qr(main)
    return interaction - q @ (q.T @ interaction)

def rao_scott(p, V, nr, nc, N, basis='dummy', *, design_df):
    """Second-order Rao–Scott F following survey's replicate-design formula.

    All cells retained. Rank-deficient covariance is declared non-estimable,
    rather than silently changing the full-category hypothesis.
    """
    tab = p.reshape(nr, nc)
    if np.any(tab.sum(0) <= 0) or np.any(tab.sum(1) <= 0):
        raise ValueError('empty_category_margin')
    C = contrast_basis(nr, nc, basis)
    inv = np.divide(1.0, p, out=np.zeros_like(p), where=p > 0)
    denom = C.T @ ((inv / N)[:, None] * C)
    numerator = (C * inv[:, None]).T @ V @ (C * inv[:, None])
    if np.linalg.matrix_rank(denom) != C.shape[1]:
        raise ValueError('singular_reference_covariance')
    eigen = eigvalsh((numerator + numerator.T) / 2, (denom + denom.T) / 2)
    if eigen.min() <= 1e-10 * eigen.max():
        raise ValueError('singular_design_covariance')
    expected = np.outer(tab.sum(1), tab.sum(0))
    pearson = float(N * np.sum((tab - expected) ** 2 / expected))
    ndf = float(eigen.sum() ** 2 / (eigen @ eigen))
    statistic = float(pearson / eigen.sum())
    return dict(statistic=statistic, numerator_df=ndf, denominator_df=ndf * design_df, p_value=float(f.sf(statistic, ndf, ndf * design_df)), pearson_statistic=pearson, nominal_df=C.shape[1], design_effect_min=float(eigen.min()), design_effect_max=float(eigen.max()))

def outcomes(d):
    result = []
    for item in ITEMS:
        valid = d[item].between(1, 7 if item == 'personal_files' else 6).to_numpy()
        y = (d[item].eq(6) if item == 'personal_files' else d[item].between(1, 3)).to_numpy(int)
        result.append((item + ('_nonproduction' if item == 'personal_files' else '_weekly'), item, [0, 1], y, valid, 'primary_graph'))
    result.append(('phone', 'phone', [0, 1], d.phone_holder.to_numpy(), d.phone_holder.isin([0, 1]).to_numpy(), 'primary_graph'))
    p, q = (d.sharing_with_contacts.between(1, 5).to_numpy(), d.sharing_with_unspecified_audiences.between(1, 5).to_numpy())
    joint = np.select([p & q, p & ~q, ~p & ~q, ~p & q], [1, 2, 3, 4])
    result.append(('joint_sharing', 'sharing_experience', [1, 2, 3, 4], joint, (d.sharing_with_contacts.between(1, 6) & d.sharing_with_unspecified_audiences.between(1, 6)).to_numpy(), 'primary_graph'))
    for name, cats in [('personal_files_answers', list(range(1, 8))), ('personal_files_locations', list(range(1, 5)))]:
        result.append((name, 'personal_files', cats, d.personal_files.to_numpy(), d.personal_files.isin(cats).to_numpy(), 'primary_graph'))
    for item in ITEMS[:4]:
        result.append((item + '_six_levels', item, list(range(1, 7)), d[item].to_numpy(), d[item].between(1, 6).to_numpy(), 'full_frequency'))
    return result

def matrix(d, mode='main', age=None, education=None, area=None):
    ages = d.age_group.to_numpy() if age is None else np.full(len(d), age)
    areas = d.area.to_numpy() if area is None else np.full(len(d), area)
    age_part = [ages == k for k in range(1, 7)]
    if mode == 'main':
        edu = d.education_group.to_numpy() if education is None else np.full(len(d), education)
        rest = [edu == k for k in range(2, 5)] + [d.sex_group.eq(2), areas == 2]
    else:
        edu = d.education_group.eq(4).to_numpy() if education is None else np.full(len(d), education)
        rest = [d.sex_group.eq(2), edu, areas == 2, edu * (areas == 2)]
    return (np.column_stack(age_part + rest).astype(float), ages)

def fit_boundary(X, ages, y, weights, mask):
    """The same model in age-cell-intercept coordinates, not a penalized model.

    Homogeneous age cells have boundary p=0/1. Their likelihood contribution
    tends to zero; finite terms are estimated from the other age cells.
    """
    training = mask & (weights > 0)
    boundary = {}
    for age in range(1, 7):
        a = training & (ages == age)
        if not a.any():
            raise ValueError(f'empty_age_level_{age}')
        values = np.unique(y[a])
        if len(values) == 1:
            boundary[age] = float(values[0])
    finite = training & ~np.isin(ages, list(boundary))
    cols = [k for k in range(6) if k + 1 not in boundary] + list(range(6, X.shape[1]))
    design = X[finite][:, cols]
    if np.linalg.matrix_rank(design) != len(cols):
        raise ValueError('finite_part_rank_deficient')
    if separation_margin(design, y[finite], weights[finite]) > 1e-07:
        raise ValueError('additional_separation_direction')
    b, info = fit(design, y[finite], weights[finite], verify=True)
    beta = np.zeros(X.shape[1])
    beta[cols] = b
    info.update(boundary_ages=';'.join(map(str, boundary)), boundary_values=';'.join((str(boundary[k]) for k in boundary)), finite_n=int(finite.sum()), finite_parameters=len(cols), likelihood=float(np.sum(weights[finite] * (y[finite] * (design @ b) - np.logaddexp(0, design @ b)))))
    return (beta, boundary, info)

def predict(X, ages, beta, boundary):
    prob = expit(X @ beta)
    for age, value in boundary.items():
        prob[ages == age] = value
    assert np.isfinite(prob).all() and np.all((prob >= 0) & (prob <= 1))
    return prob

def support(d, valid, item, weights):
    counts = []
    for age in range(1, 7):
        for edu in range(1, 5):
            for sex in [1, 2]:
                for area in [1, 2]:
                    mask = valid & d.age_group.eq(age).to_numpy() & d.education_group.eq(edu).to_numpy() & d.sex_group.eq(sex).to_numpy() & d.area.eq(area).to_numpy()
                    y = (d[item].eq(6) if item == 'personal_files' else d[item].between(1, 3)).to_numpy()
                    counts.append(dict(item=item, age=age, education=edu, sex=sex, area=area, n=int(mask.sum()), events=int((mask & y).sum()), event_psus=len(d.loc[mask & y, KEYS].drop_duplicates())))
    lookup = {(r['age'], r['education'], r['sex'], r['area']): r['n'] for r in counts}
    mass = {}
    for fac, levels in [('age', range(1, 7)), ('education', range(1, 5))]:
        for level in levels:
            cells = zip(np.full(len(d), level) if fac == 'age' else d.age_group, np.full(len(d), level) if fac == 'education' else d.education_group, d.sex_group, d.area)
            empty = np.array([lookup[c] == 0 for c in cells])
            mass[fac, level] = float(np.average(empty, weights=weights))
    return (counts, mass)
