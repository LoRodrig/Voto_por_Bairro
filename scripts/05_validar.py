"""Validações finais: reconciliação de votos, cobertura de bairros e integridade do relatório. Sai com código 1 se algo falhar."""
import json
import re
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
MIN_COBERTURA = 90.0
# Cobertura abaixo do mínimo só é aceita com explicação registrada aqui.
EXPLICADAS = {'4115200': 'A malha de bairros do IBGE (Censo 2022) não cobre toda a área urbana de Maringá: locais de votação de Zona 02/07 e Vila Morangueira ficam a ~0,6 km (mediana) do polígono mais próximo.'}

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
    for f in sorted(OUT.glob('votos_bairros_ibge_*.parquet')):
        m = f.stem.rsplit('_', 1)[1]
        por = pd.read_parquet(f).QT_VOTOS.sum()
        excl = pd.read_csv(OUT / f'exclusoes_bairros_{m}.csv', sep=';').QT_VOTOS.sum()
        cd = int(cross.loc[cross.CD_MUN == m, 'CD_MUNICIPIO'].iloc[0])
        total = sec[(sec.SG_UF == 'PR') & (sec.CD_MUNICIPIO == cd)].QT_VOTOS.sum()
        cob = 100 * por / total
        print(f'{m}: cobertura {cob:.2f}%')
        if por + excl != total:
            erros.append(f'{m}: bairros + exclusões ({por + excl}) != votos do município ({total})')
        vu = OUT / f'votos_unidades_{m}.parquet'
        if vu.exists():  # bairro IBGE ou bairro TSE: todos os votos de seções cadastradas devem estar em alguma unidade
            unid = pd.read_parquet(vu).QT_VOTOS.sum()
            print(f'{m}: {100 * unid / total:.2f}% dos votos em unidades (bairro IBGE ou TSE)')
            if unid != total:
                erros.append(f'{m}: votos em unidades ({unid}) != votos do município ({total})')
        if cob < MIN_COBERTURA and m not in EXPLICADAS:
            erros.append(f'{m}: cobertura {cob:.1f}% < {MIN_COBERTURA}% sem explicação registrada')
    html = (OUT / 'relatorio_eleicoes_2026.html').read_text(encoding='utf-8')
    dados = re.search(r'<script id="dados" type="application/json">(.*?)</script>', html, re.S)
    if not dados:
        erros.append('relatório sem bloco de dados')
    elif not json.loads(dados.group(1).replace('<\\/', '</')).get('bairros_ibge'):
        erros.append('relatório sem bairros_ibge')
    novo = OUT / 'relatorio_bairros_parana.html'
    if not novo.exists() or 'bairros' not in novo.read_text(encoding='utf-8'):
        erros.append('relatorio_bairros_parana.html ausente ou vazio')
    for e in erros:
        print('FALHA:', e)
    print('OK' if not erros else f'{len(erros)} falha(s)')
    sys.exit(1 if erros else 0)

if __name__ == '__main__':
    main()
