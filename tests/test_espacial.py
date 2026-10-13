import importlib, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'pipeline'))
esp = importlib.import_module('espacial')

def quad(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], float)

# A = [0,1]x[0,1], B = [1,2]x[0,1] (share the edge x=1); coordinates are (lon, lat)
BAIRROS = [('A', [quad(0, 0, 1, 1)]), ('B', [quad(1, 0, 2, 1)])]

def locais(*pts):
    return pd.DataFrame({'NR_LONGITUDE': [p[0] for p in pts], 'NR_LATITUDE': [p[1] for p in pts]})

def test_parse_coord_comma_and_invalid():
    out = esp.parse_coord(pd.Series(['-23,5', '', '-1', 'x', '-23.5']))
    assert out.iloc[0] == -23.5 and out.iloc[4] == -23.5
    assert out.iloc[1:4].isna().all()

def test_point_inside_gets_its_bairro():
    r = esp.atribuir_bairros(locais(('0,5', '0,5'), ('1,5', '0,5')), BAIRROS)
    assert r.CD_BAIRRO.tolist() == ['A', 'B'] and (r.motivo_exclusao == '').all()

def test_missing_coordinate_is_excluded():
    r = esp.atribuir_bairros(locais(('', '0,5')), BAIRROS)
    assert r.motivo_exclusao.iloc[0] == 'SEM_COORDENADA' and pd.isna(r.CD_BAIRRO.iloc[0])

def test_point_outside_is_excluded():
    r = esp.atribuir_bairros(locais(('5', '5')), BAIRROS)
    assert r.motivo_exclusao.iloc[0] == 'FORA_DE_BAIRRO'

def test_point_on_shared_edge_gets_exactly_one_bairro():
    e = locais(('1', '0,5'), ('0,5', '0,5'))
    r = esp.atribuir_bairros(e, BAIRROS)
    assert len(r) == len(e) and r.CD_BAIRRO.iloc[0] in ('A', 'B')

def test_hole_is_not_inside():
    hole = quad(0.4, 0.4, 0.6, 0.6)
    r = esp.atribuir_bairros(locais(('0,5', '0,5')), [('A', [quad(0, 0, 1, 1), hole])])
    assert r.motivo_exclusao.iloc[0] == 'FORA_DE_BAIRRO'

GPKG = Path(__file__).resolve().parents[1] / 'data/raw/PR_bairros_CD2022.gpkg'

@pytest.mark.skipif(not GPKG.exists(), reason='malha IBGE não baixada')
def test_ler_malha_maringa_returns_closed_rings():
    m = esp.ler_malha(GPKG, '4115200')
    assert 100 <= len(m) <= 120 and len({c for c, _ in m}) == 113
    assert all(np.array_equal(r[0], r[-1]) for _, rings in m for r in rings)

def test_ler_malha_unknown_municipio_names_it():
    if not GPKG.exists():
        pytest.skip('malha IBGE não baixada')
    with pytest.raises(ValueError, match='9999999'):
        esp.ler_malha(GPKG, '9999999')
