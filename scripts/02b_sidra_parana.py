"""Escolaridade (25+) e desocupação por município do Paraná, Censo 2022 (SIDRA/IBGE, tabelas 10141 e 6580)."""
import gzip
import json
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / 'outputs'
API = 'https://servicodados.ibge.gov.br/api/v3/agregados/{t}/periodos/2022/variaveis/{v}?localidades=N6[N3[41]]&classificacao={c}'
# 6580: variável 1641, força de trabalho (32386) e desocupada (32446); sexo e idade = total
TRABALHO = dict(t=6580, v=1641, c='629[32386,32446]|2[6794]|58[95253]', cls='629')
# 10141: variável 1643, total (120704), superior completo (99713), sem instrução/fund. incompleto (9493); sexo e deficiência = total
INSTRUCAO = dict(t=10141, v=1643, c='1568[120704,99713,9493]|2[6794]|839[46583]', cls='1568')

def buscar(q):
    with urllib.request.urlopen(API.format(**q), timeout=60) as r:
        raw = r.read()
    if raw[:2] == bytes([0x1f, 0x8b]):  # a API às vezes responde comprimida sem pedir
        raw = gzip.decompress(raw)
    res = json.loads(raw)[0]['resultados']
    rows = []
    for x in res:
        cat = next(iter(next(c for c in x['classificacoes'] if c['id'] == q['cls'])['categoria']))
        for s in x['series']:
            rows.append((s['localidade']['id'], cat, pd.to_numeric(s['serie']['2022'], errors='coerce')))
    return pd.DataFrame(rows, columns=['CD_MUN', 'cat', 'valor'])

def calcular(trab, inst):
    # min_count=1 mantém NaN (valor suprimido) em vez de virar 0; pivot_table descartaria a coluna toda
    t = trab.groupby(['CD_MUN', 'cat']).valor.sum(min_count=1).unstack().reindex(columns=['32386', '32446'])
    i = inst.groupby(['CD_MUN', 'cat']).valor.sum(min_count=1).unstack().reindex(columns=['120704', '99713', '9493'])
    out = pd.DataFrame(index=t.index.union(i.index))
    out['taxa_desocupacao_2022'] = 100 * t['32446'] / t['32386'].replace(0, np.nan)
    out['pct_25mais_superior_completo_2022'] = 100 * i['99713'] / i['120704'].replace(0, np.nan)
    out['pct_25mais_sem_instrucao_ou_fund_incompleto_2022'] = 100 * i['9493'] / i['120704'].replace(0, np.nan)
    return out.rename_axis('CD_MUN').reset_index()

if __name__ == '__main__':
    r = calcular(buscar(TRABALHO), buscar(INSTRUCAO))
    assert len(r) == 399, f'esperados 399 municípios do PR, vieram {len(r)}'
    r.to_parquet(OUT / 'sidra_pr_municipios.parquet', index=False)
    print(r.describe().round(2).to_string())
