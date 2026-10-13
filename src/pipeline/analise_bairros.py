"""Correlações do voto com indicadores do Censo: bairros de uma cidade (com IC bootstrap) e municípios do PR."""
import importlib
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'atlas_nacional'))
IND_BAIRRO = importlib.import_module('setores').INDICADORES
MIN_BAIRROS = 20

def _spearman(x, y):
    if np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(pd.Series(x).rank(), pd.Series(y).rank())[0, 1])

def analisar_bairros(votos_bairro, ibge_bairros, candidatos, rng_seed=20261012, n_boot=2000):
    """Spearman voto% x indicador por candidato, IC95% por bootstrap de bairros.
    Colunas: candidato_numero, indicador, n_bairros, spearman, ic95_inf, ic95_sup."""
    v = votos_bairro[votos_bairro.NR_VOTAVEL.isin(candidatos)]
    w = v.pivot_table(index='CD_BAIRRO', columns='NR_VOTAVEL', values='QT_VOTOS', aggfunc='sum', fill_value=0)
    tot = w.sum(axis=1)
    pct = w.div(tot.replace(0, np.nan), axis=0) * 100
    d = pct.join(ibge_bairros.set_index('CD_BAIRRO'), how='inner')
    d = d[d.populacao_2022.fillna(0) > 0]
    rng, rows = np.random.default_rng(rng_seed), []
    for c in candidatos:
        for ind in (i for i in IND_BAIRRO if i in d):
            z = d[[ind, c]].dropna()
            row = dict(candidato_numero=c, indicador=ind, n_bairros=len(z), spearman=np.nan, ic95_inf=np.nan, ic95_sup=np.nan)
            if len(z) >= MIN_BAIRROS:
                x, y = z[ind].to_numpy(), z[c].to_numpy()
                row['spearman'] = _spearman(x, y)
                idx = rng.integers(0, len(z), (n_boot, len(z)))
                boot = [_spearman(x[i], y[i]) for i in idx]
                row['ic95_inf'], row['ic95_sup'] = np.nanquantile(boot, [.025, .975])
            rows.append(row)
    return pd.DataFrame(rows)

NOVOS = {'taxa_desocupacao_2022': 'Taxa de desocupação, 14+ (%, Censo 2022; não comparável à PNAD)',
         'pct_25mais_superior_completo_2022': 'Superior completo, 25+ (%, 2022)',
         'pct_25mais_sem_instrucao_ou_fund_incompleto_2022': 'Sem instrução ou fundamental incompleto, 25+ (%, 2022)'}

def main(municipios=('4115200',)):
    import json
    OUT = Path(__file__).resolve().parents[2] / 'outputs'
    cand = {v['NR_VOTAVEL']: v['NM_VOTAVEL'] for v in json.loads((OUT / 'auditoria_tse.json').read_text(encoding='utf-8'))['votaveis'] if v['NR_VOTAVEL'] not in (95, 96)}
    a03 = importlib.import_module('analise_municipal')
    a03.INDICATORS.update(NOVOS)
    mun = pd.read_parquet(OUT / 'analise_municipal_ampla.parquet').merge(pd.read_parquet(OUT / 'sidra_pr_municipios.parquet'), on='CD_MUN', how='left', validate='one_to_one')
    pr = mun[(mun.SG_UF == 'PR') & (mun.alerta_limite_territorial == '')]
    c = pd.DataFrame(a03.associations(pr, cand, 'PR — municípios'))
    c['candidato'] = c.candidato_numero.map(cand)
    c.to_csv(OUT / 'correlacoes_pr_municipios.csv', sep=';', index=False, encoding='utf-8-sig')
    ib = pd.read_parquet(OUT / 'ibge_bairros.parquet')
    for m in municipios:
        vu, un = OUT / f'votos_unidades_{m}.parquet', OUT / f'unidades_{m}.parquet'
        if vu.exists() and un.exists():  # bairro IBGE + bairro TSE (fora dos polígonos)
            r = analisar_bairros(pd.read_parquet(vu).rename(columns={'UNIDADE': 'CD_BAIRRO'}), pd.read_parquet(un).rename(columns={'UNIDADE': 'CD_BAIRRO'}), cand)
        else:
            r = analisar_bairros(pd.read_parquet(OUT / f'votos_bairros_ibge_{m}.parquet'), ib, cand)
        r['candidato'] = r.candidato_numero.map(cand)
        r.to_csv(OUT / f'correlacoes_bairros_{m}.csv', sep=';', index=False, encoding='utf-8-sig')
    return c, r

if __name__ == '__main__':
    c, r = main(sys.argv[1:] or ('4115200',))
    top = c[c.n_territorios >= 300].assign(a=lambda d: d.spearman.abs()).sort_values('a', ascending=False)
    print(top[['candidato', 'indicador', 'n_territorios', 'spearman']].head(8).to_string(index=False))
    print(r.dropna(subset=['spearman']).assign(a=lambda d: d.spearman.abs()).sort_values('a', ascending=False)[['candidato', 'indicador', 'n_bairros', 'spearman', 'ic95_inf', 'ic95_sup']].head(8).to_string(index=False))
