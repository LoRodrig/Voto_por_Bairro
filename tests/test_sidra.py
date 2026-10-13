import importlib, sys
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'pipeline'))
sidra = importlib.import_module('escolaridade_sidra')

def test_calcular_rates_from_counts():
    trab = pd.DataFrame({'CD_MUN': ['1', '1', '2', '2'], 'cat': ['32386', '32446', '32386', '32446'], 'valor': [200, 10, 100, 0]})
    inst = pd.DataFrame({'CD_MUN': ['1'] * 3 + ['2'] * 3, 'cat': ['120704', '99713', '9493'] * 2, 'valor': [100, 25, 40, 50, 5, 30]})
    r = sidra.calcular(trab, inst).set_index('CD_MUN')
    assert r.loc['1', 'taxa_desocupacao_2022'] == pytest.approx(5.0)
    assert r.loc['2', 'taxa_desocupacao_2022'] == 0
    assert r.loc['1', 'pct_25mais_superior_completo_2022'] == pytest.approx(25.0)
    assert r.loc['2', 'pct_25mais_sem_instrucao_ou_fund_incompleto_2022'] == pytest.approx(60.0)

def test_calcular_missing_value_gives_nan_not_zero():
    trab = pd.DataFrame({'CD_MUN': ['1', '1'], 'cat': ['32386', '32446'], 'valor': [None, 10]})
    inst = pd.DataFrame({'CD_MUN': ['1'], 'cat': ['120704'], 'valor': [100]})
    r = sidra.calcular(trab, inst)
    assert r.taxa_desocupacao_2022.isna().all()
