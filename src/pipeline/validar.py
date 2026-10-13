"""Validações finais: reconciliação de votos por unidade de bairro e integridade da página. Sai com código 1 se algo falhar."""
import json
import re
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs'

def main():
    erros = []
    mun = pd.read_csv(OUT / 'votos_municipios_2026_t1.csv', sep=';')
    uf = pd.read_csv(OUT / 'votos_estados_2026_t1.csv', sep=';')
    if mun.QT_VOTOS.sum() != uf.QT_VOTOS.sum():
        erros.append('votos municipais != votos estaduais')
    sec = pd.read_parquet(OUT / 'votos_secoes_2026_t1.parquet', columns=['SG_UF', 'CD_MUNICIPIO', 'QT_VOTOS'])
    if sec.QT_VOTOS.sum() != mun.QT_VOTOS.sum():
        erros.append('votos por seção != votos municipais')
    cross = pd.read_parquet(OUT / 'correspondencia_tse_ibge.parquet')
    arquivos = sorted(OUT.glob('votos_unidades_*.parquet'))
    for f in arquivos:
        m = f.stem.rsplit('_', 1)[1]
        v = pd.read_parquet(f)
        cd = int(cross.loc[cross.CD_MUN == m, 'CD_MUNICIPIO'].iloc[0])
        total = sec[(sec.SG_UF == 'PR') & (sec.CD_MUNICIPIO == cd)].QT_VOTOS.sum()
        t = v.groupby('TIPO').QT_VOTOS.sum()
        print(f"{m}: {100 * v.QT_VOTOS.sum() / total:.2f}% dos votos em unidades (bairro IBGE {100 * t.get('IBGE', 0) / total:.1f}% · bairro TSE {100 * t.get('TSE', 0) / total:.1f}%)")
        if v.QT_VOTOS.sum() != total:  # todo voto de seção cadastrada deve estar em alguma unidade
            erros.append(f'{m}: votos em unidades ({v.QT_VOTOS.sum()}) != votos do município ({total})')
    pagina = ROOT / 'index.html'
    if not pagina.exists():
        erros.append('index.html ausente')
    else:
        dados = re.search(r'<script id="dados" type="application/json">(.*?)</script>', pagina.read_text(encoding='utf-8'), re.S)
        if not dados:
            erros.append('index.html sem bloco de dados')
        elif len(json.loads(dados.group(1).replace('<\\/', '</')).get('cidades', {})) != len(arquivos):
            erros.append('index.html não tem todas as cidades processadas')
    for e in erros:
        print('FALHA:', e)
    print('OK' if not erros else f'{len(erros)} falha(s)')
    sys.exit(1 if erros else 0)

if __name__ == '__main__':
    main()
