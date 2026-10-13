import importlib, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'pipeline'))
esp = importlib.import_module('espacial')
setores = importlib.import_module('setores')

ROOT = Path(__file__).resolve().parents[1]
KEY = ['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO']

# ---------- 09_setores.agregar ----------
def _setor(**kw):
    base = dict(V00001=0, V00049=0, V01042=0, V01063=0, V01317=0, V01318=0, V01319=0, V01320=0, V01321=0, V01006=0, V01034=0, V01035=0, V01036=0, V01040=0, V01041=0,
                V00111=0, V00309=0, V06001=0, V06004=np.nan, V0001=0, AREA_KM2=1.0)
    base.update(kw)
    return base

def test_agregar_sums_counts_and_weights_income_by_responsaveis():
    df = pd.DataFrame([
        _setor(V01317=60, V01318=10, V01320=30, V01006=100, V01040=10, V01041=5, V01034=5, V01035=10, V01036=5, V00111=40, V00309=20, V06001=50, V06004=1000.0, V0001=100, AREA_KM2=2.0, V00001=50, V00049=10, V01042=50, V01063=20),
        _setor(V01317=150, V01318=10, V01320=40, V01006=300, V01040=30, V01041=15, V06001=150, V06004=3000.0, V00111=100, V00309=50, V0001=300, AREA_KM2=2.0, V00001=150, V00049=50, V01042=150, V01063=70)])
    r = setores.agregar(df)
    assert r['pct_pretos_pardos'] == pytest.approx(100 * 90 / 300)
    assert r['pct_apartamento'] == pytest.approx(100 * 60 / 200)
    assert r['pct_mulheres_responsaveis'] == pytest.approx(100 * 90 / 200)
    assert r['pct_60mais'] == pytest.approx(100 * 60 / 400)
    assert r['pct_15a29'] == pytest.approx(100 * 20 / 400)
    assert r['pct_domicilios_rede_agua'] == pytest.approx(100 * 140 / 200)
    assert r['pct_domicilios_rede_esgoto_pluvial'] == pytest.approx(100 * 70 / 200)
    assert r['renda_media_responsavel_com_renda_2022'] == pytest.approx((50 * 1000 + 150 * 3000) / 200)
    assert r['populacao_2022'] == 400 and r['densidade_hab_km2'] == pytest.approx(100)

def test_agregar_ignores_setor_without_income_in_income_average():
    df = pd.DataFrame([_setor(V06001=10, V06004=2000.0), _setor(V06001=90, V06004=np.nan)])
    assert setores.agregar(df)['renda_media_responsavel_com_renda_2022'] == pytest.approx(2000.0)

def test_agregar_empty_returns_nan_not_error():
    assert np.isnan(setores.agregar(pd.DataFrame([_setor()]))['pct_60mais'])

# ---------- 06.ler_malha generalizado ----------
GPKG_SET = ROOT / 'data/raw/PR_setores_CD2022.gpkg'

@pytest.mark.skipif(not GPKG_SET.exists(), reason='malha de setores não baixada')
def test_ler_malha_setores_maringa():
    m = esp.ler_malha(GPKG_SET, '4115200', tabela='PR_setores_CD2022', col='CD_SETOR')
    assert len(m) == 793 and len({c for c, _ in m}) == 793

# ---------- 06.construir_unidades ----------
def quad(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], float)

BAIRROS = [('A', [quad(0, 0, 1, 1)])]
SETORES = [('S1', [quad(0, 0, 1, 1)]), ('S2', [quad(1, 0, 2, 1)]), ('S3', [quad(2, 0, 3, 1)])]

def _cad():
    return pd.DataFrame({'SG_UF': 'PR', 'CD_MUNICIPIO': 1, 'NR_ZONA': 1, 'NR_SECAO': [1, 2, 3, 4],
        'NR_LATITUDE': ['0,5', '0,5', '0,5', ''], 'NR_LONGITUDE': ['0,5', '1,5', '2,5', ''],
        'NM_BAIRRO': ['CENTRO', 'ZONA 07', 'ZONA 07', 'ZONA 09']})

def _votos():
    v = _cad()[KEY].copy()
    v['NR_VOTAVEL'] = 13
    v['QT_VOTOS'] = [10, 20, 30, 40]
    extra = v.iloc[:1].copy(); extra['NR_SECAO'] = 99; extra['QT_VOTOS'] = 5  # seção sem cadastro
    return pd.concat([v, extra], ignore_index=True)

IND_SETOR = pd.DataFrame([_setor(V01317=90, V01318=5, V01320=5, V0001=100, V06001=10, V06004=1000.0, V01006=100),
                          _setor(V01317=80, V01318=5, V01320=15, V0001=200, V06001=20, V06004=2000.0, V01006=200),
                          _setor(V01317=70, V01318=10, V01320=20, V0001=300, V06001=30, V06004=3000.0, V01006=300)], index=['S1', 'S2', 'S3'])
IND_BAIRRO = pd.DataFrame({'pct_pretos_pardos': [10.0], 'populacao_2022': [100.0]}, index=pd.Index(['A'], name='CD_BAIRRO'))

def test_unidades_reconcile_to_100_percent_of_votes():
    r = esp.construir_unidades(_cad(), _votos(), BAIRROS, SETORES, IND_SETOR, IND_BAIRRO)
    assert r['votos'].QT_VOTOS.sum() + r['sem_cadastro'] == _votos().QT_VOTOS.sum()
    assert r['sem_cadastro'] == 5

def test_section_inside_bairro_is_ibge_unit_others_are_tse_by_name():
    r = esp.construir_unidades(_cad(), _votos(), BAIRROS, SETORES, IND_SETOR, IND_BAIRRO)
    v = r['votos'].set_index('UNIDADE').QT_VOTOS
    assert v['A'] == 10 and v['TSE|ZONA07'] == 50 and v['TSE|ZONA09'] == 40
    assert set(r['unidades'].set_index('UNIDADE').TIPO) == {'IBGE', 'TSE'}

def test_tse_unit_indicators_come_from_distinct_setores_of_its_polling_places():
    u = esp.construir_unidades(_cad(), _votos(), BAIRROS, SETORES, IND_SETOR, IND_BAIRRO)['unidades'].set_index('UNIDADE')
    z7 = u.loc['TSE|ZONA07']
    assert z7.n_setores == 2 and z7.populacao_2022 == 500
    assert z7.pct_pretos_pardos == pytest.approx(100 * 50 / 200)  # S2+S3 somados: (5+15+10+20) / 200
    assert pd.isna(u.loc['TSE|ZONA09'].pct_pretos_pardos) and u.loc['TSE|ZONA09'].n_setores == 0
    assert u.loc['A'].pct_pretos_pardos == 10.0

# ---------- setores atribuídos a bairros do TSE (contorno aproximado) ----------
SETORES5 = SETORES + [('S4', [quad(3, 0, 4, 1)]), ('S5', [quad(4, 0, 5, 1)])]
IND5 = pd.concat([IND_SETOR, pd.DataFrame([_setor(V01317=60, V01318=15, V01320=25, V0001=400, V06001=40, V06004=4000.0, V01006=400),
                                              _setor(V01317=50, V01318=25, V01320=25, V0001=500, V06001=50, V06004=5000.0, V01006=500)], index=['S4', 'S5'])])
META = pd.DataFrame({'SITUACAO': ['Urbana'] * 4 + ['Rural'], 'CD_BAIRRO': ['A', None, None, None, None]}, index=['S1', 'S2', 'S3', 'S4', 'S5'])

def _cad2():
    c = _cad().copy()
    c['NM_BAIRRO'] = ['CENTRO', 'ZONA 07', 'ZONA 08', 'ZONA 09']
    return c

def test_free_urban_setor_goes_to_nearest_tse_unit_and_rural_is_left_out():
    r = esp.construir_unidades(_cad2(), _votos(), BAIRROS, SETORES5, IND5, IND_BAIRRO, setor_meta=META)
    su = r['setor_unidade'].set_index('CD_SETOR').UNIDADE
    assert su['S2'] == 'TSE|ZONA07' and su['S3'] == 'TSE|ZONA08' and su['S4'] == 'TSE|ZONA08'
    assert 'S5' not in su.index and 'S1' not in su.index

def test_tse_unit_indicators_use_all_its_assigned_setores():
    u = esp.construir_unidades(_cad2(), _votos(), BAIRROS, SETORES5, IND5, IND_BAIRRO, setor_meta=META)['unidades'].set_index('UNIDADE')
    z8 = u.loc['TSE|ZONA08']
    assert z8.n_setores == 2 and z8.populacao_2022 == 700                       # S3 + S4
    assert z8.pct_pretos_pardos == pytest.approx(100 * 70 / 200)  # S3+S4: (10+20+15+25) / (100+100)

# ---------- dissolver: contorno externo da união de setores ----------
def _area(ring):
    x, y = ring[:, 0], ring[:, 1]
    return abs((x[:-1] * y[1:] - x[1:] * y[:-1]).sum()) / 2

def test_dissolver_two_adjacent_squares_gives_one_loop_with_total_area():
    loops = esp.dissolver([quad(0, 0, 1, 1), quad(1, 0, 2, 1)])
    assert len(loops) == 1 and _area(loops[0]) == pytest.approx(2.0)
    assert np.array_equal(loops[0][0], loops[0][-1])

def test_dissolver_keeps_the_hole_as_second_loop():
    ring = [quad(i, j, i + 1, j + 1) for i in range(3) for j in range(3) if (i, j) != (1, 1)]
    loops = sorted(esp.dissolver(ring), key=_area)
    assert len(loops) == 2 and _area(loops[0]) == pytest.approx(1.0) and _area(loops[1]) == pytest.approx(9.0)

def test_dissolver_separate_parts_stay_separate():
    assert len(esp.dissolver([quad(0, 0, 1, 1), quad(5, 5, 6, 6)])) == 2
