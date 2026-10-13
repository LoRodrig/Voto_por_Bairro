"""Relatório centrado em cidade e bairro (Paraná): só características do Censo que existem por bairro."""
import base64
import importlib
import json
import sys
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
sys.path.insert(0, str(ROOT / 'scripts'))
INDICADORES = importlib.import_module('09_setores').INDICADORES

IND = list(INDICADORES)

BRANCO, NULO = 95, 96  # códigos do TSE
NOME_PROJETO = 'Voto por Bairro'  # troque aqui para renomear a página
SUBTITULO = 'Paraná · presidente 2026 · por bairro'
DUELO = [13, 22]  # Lula e Flávio Bolsonaro; percentuais são sobre os votos válidos de todos os candidatos
NOMES = {'13': 'Lula', '22': 'Flávio Bolsonaro'}

def num(v):
    return None if v is None or pd.isna(v) else float(v)

def cidades(cands):
    """Uma entrada por cidade: bairros IBGE e bairros TSE (contorno aproximado por setores), votos, nulos e correlações."""
    esp = importlib.import_module('06_bairros_espacial')
    ib = pd.read_parquet(OUT / 'ibge_bairros.parquet')
    rd = lambda loop: [[round(la, 5), round(lo, 5)] for lo, la in loop]
    res = {}
    for f in sorted(OUT.glob('votos_unidades_*.parquet')):
        m = f.stem.rsplit('_', 1)[1]
        v = pd.read_parquet(f)
        w = v.pivot_table(index='UNIDADE', columns='NR_VOTAVEL', values='QT_VOTOS', aggfunc='sum', fill_value=0)
        for c in (BRANCO, NULO):
            if c not in w:
                w[c] = 0
        tipo = v.groupby('TIPO').QT_VOTOS.sum()
        tot = tipo.sum()
        polys = {}
        for cd, rings in esp.ler_malha(ROOT / 'data/raw/PR_bairros_CD2022.gpkg', m):
            polys.setdefault(cd, []).append(rd(rings[0]))
        un = pd.read_parquet(OUT / f'unidades_{m}.parquet').set_index('UNIDADE')
        ibn = ib[ib.CD_MUN == m].set_index('CD_BAIRRO')
        setores = dict(esp.ler_malha(ROOT / 'data/raw/PR_setores_CD2022.gpkg', m, tabela='PR_setores_CD2022', col='CD_SETOR'))
        su = pd.read_parquet(OUT / f'setores_unidade_{m}.parquet')

        def votos(u):
            if u not in w.index:
                return {'total': None, 'v': None, 'nulos': None, 'brancos': None}
            r = w.loc[u]
            return {'total': int(r[cands].sum()), 'v': [int(r[c]) for c in DUELO], 'nulos': int(r[NULO]), 'brancos': int(r[BRANCO])}

        bairros = {}
        for cd in polys:  # todo polígono IBGE aparece, mesmo sem votos
            bairros[cd] = {'nome': ibn.NM_BAIRRO.get(cd, cd), 'tipo': 'ibge', 'n_setores': None, 'pop': num(ibn.populacao_2022.get(cd)), **votos(cd), 'ind': {k: num(ibn[k].get(cd)) for k in IND}}
        for u, row in un[un.TIPO == 'TSE'].iterrows():
            bairros[u] = {'nome': row.NOME, 'tipo': 'tse', 'n_setores': int(row.n_setores), 'pop': num(row.populacao_2022), **votos(u), 'ind': {k: num(row[k]) for k in IND}}
            rings = [r for cd in su.CD_SETOR[su.UNIDADE == u] for r in setores[cd]]
            polys[u] = [rd(loop) for loop in esp.dissolver(rings)]
        cor = pd.read_csv(OUT / f'correlacoes_bairros_{m}.csv', sep=';')
        res[m] = {'nome': str(ibn.NM_MUN.iloc[0]), 'pct_ibge': round(100 * tipo.get('IBGE', 0) / tot, 2), 'pct_tse': round(100 * tipo.get('TSE', 0) / tot, 2),
                  'bairros': bairros, 'poligonos': polys,
                  'correlacoes': [{k: (num(x) if isinstance(x, float) else x) for k, x in r.items()} for r in cor[cor.candidato_numero.isin(DUELO)].drop(columns=['candidato']).to_dict('records')]}
    return res

def main():
    tse = json.loads((OUT / 'auditoria_tse.json').read_text(encoding='utf-8'))
    cand = {v['NR_VOTAVEL']: v['NM_VOTAVEL'] for v in tse['votaveis'] if v['NR_VOTAVEL'] not in (95, 96)}
    cands = list(cand)
    cidades_ = cidades(cands)
    if not cidades_:
        raise SystemExit('Nenhuma cidade gerada: rode scripts/06_bairros_espacial.py --uf PR --municipio <código IBGE>.')
    data = {'nomes': NOMES, 'cands': DUELO, 'ind_ordem': IND,
            'indicadores': dict(INDICADORES), 'cidades': cidades_}
    tpl = (ROOT / 'scripts/relatorio_bairros_template.html').read_text(encoding='utf-8')
    lf = ROOT / 'scripts/vendor/leaflet'
    html = tpl.replace('__LEAFLET_CSS__', (lf / 'leaflet.css').read_text(encoding='utf-8')).replace('__LEAFLET_JS__', (lf / 'leaflet.js').read_text(encoding='utf-8'))
    font = base64.b64encode((ROOT / 'scripts/vendor/fonts/manrope-latin-wght.woff2').read_bytes()).decode()
    ic = ROOT / 'scripts/vendor/icons'
    html = html.replace('__NOME__', NOME_PROJETO).replace('__SUB__', SUBTITULO)
    html = html.replace('__FAVICON__', base64.b64encode((ic / 'favicon.svg').read_bytes()).decode()).replace('__APPLE__', base64.b64encode((ic / 'apple-touch-icon.png').read_bytes()).decode())
    html = html.replace('__FONT__', font).replace('__DATA__', json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('</', '<\\/'))
    (OUT / 'relatorio_bairros_parana.html').write_text(html, encoding='utf-8')
    site = ROOT / 'docs'  # fonte do GitHub Pages
    site.mkdir(exist_ok=True)
    (site / 'index.html').write_text(html, encoding='utf-8')
    (site / '.nojekyll').write_text('', encoding='utf-8')
    print('Relatório criado:', OUT / 'relatorio_bairros_parana.html', f'{len(html) / 1e6:.1f} MB', '| cidades:', ', '.join(v['nome'] for v in cidades_.values()))

if __name__ == '__main__':
    main()
