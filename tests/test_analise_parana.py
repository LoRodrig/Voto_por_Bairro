import importlib, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'pipeline'))
ana = importlib.import_module('analise_bairros')
IND = 'pct_pretos_pardos'
CAND = {13: 'A', 22: 'B'}

def bairros(n, pct_a, pop=1000):
    """n bairros; candidato 13 recebe pct_a[i]% de 1000 votos válidos, 22 recebe o resto."""
    ids = [f'B{i:02d}' for i in range(n)]
    ibge = pd.DataFrame({'CD_BAIRRO': ids, IND: np.arange(n, dtype=float), 'populacao_2022': pop})
    v13 = pd.DataFrame({'CD_BAIRRO': ids, 'NR_VOTAVEL': 13, 'QT_VOTOS': np.round(np.array(pct_a) * 10).astype(int)})
    v22 = pd.DataFrame({'CD_BAIRRO': ids, 'NR_VOTAVEL': 22, 'QT_VOTOS': 1000 - v13.QT_VOTOS})
    return pd.concat([v13, v22]), ibge

def test_monotone_relation_gives_spearman_one_with_tight_interval():
    votos, ibge = bairros(30, np.linspace(10, 80, 30))
    r = ana.analisar_bairros(votos, ibge, CAND).query('candidato_numero == 13').iloc[0]
    assert r.spearman == 1 and r.ic95_inf > 0.8 and r.n_bairros == 30

def test_random_relation_interval_includes_zero():
    rng = np.random.default_rng(1)
    votos, ibge = bairros(40, rng.uniform(10, 80, 40))
    r = ana.analisar_bairros(votos, ibge, CAND).query('candidato_numero == 13').iloc[0]
    assert r.ic95_inf < 0 < r.ic95_sup

def test_fewer_than_20_bairros_gives_nan():
    votos, ibge = bairros(10, np.linspace(10, 80, 10))
    assert ana.analisar_bairros(votos, ibge, CAND).spearman.isna().all()

def test_bairros_without_population_are_dropped():
    votos, ibge = bairros(30, np.linspace(10, 80, 30))
    ibge.loc[:4, 'populacao_2022'] = 0
    r = ana.analisar_bairros(votos, ibge, CAND).query('candidato_numero == 13').iloc[0]
    assert r.n_bairros == 25
