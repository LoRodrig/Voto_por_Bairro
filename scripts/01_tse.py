"""Consolida votos presidenciais de 2026, primeiro turno, com validações."""
from pathlib import Path
import json
import zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT/'data/raw', ROOT/'outputs'
OUT.mkdir(exist_ok=True)
KEY = ['SG_UF','CD_MUNICIPIO','NR_ZONA','NR_SECAO']

def main():
    locais = []
    with zipfile.ZipFile(RAW/'eleitorado_local_votacao_2026.zip') as z:
        for name in z.namelist():
            if not name.lower().endswith('.csv'): continue
            d = pd.read_csv(z.open(name),sep=';',encoding='latin1',dtype=str)
            d = d[(d.NR_TURNO=='1') & (d.AA_ELEICAO=='2026')].copy()
            locais.append(d)
    loc = pd.concat(locais,ignore_index=True)
    for k in KEY[1:]: loc[k] = pd.to_numeric(loc[k],errors='raise').astype('int64')
    keep = KEY+['NM_BAIRRO','NR_LATITUDE','NR_LONGITUDE','QT_ELEITOR_ELEICAO_FEDERAL','NR_LOCAL_VOTACAO','NM_LOCAL_VOTACAO','DS_ENDERECO']
    loc = loc[keep].drop_duplicates()
    if loc.duplicated(KEY).any():
        loc[loc.duplicated(KEY,False)].to_csv(OUT/'conflitos_locais.csv',index=False)
        raise ValueError('Cadastro possui chaves ambíguas; conferir conflitos_locais.csv')
    loc.to_parquet(OUT/'cadastro_secoes.parquet',index=False)
    parts, section_parts = [], []
    total_rows = 0
    generations = set()
    with zipfile.ZipFile(RAW/'votacao_secao_2026_BR.zip') as z:
        name = next(n for n in z.namelist() if n.endswith('.csv'))
        for i,d in enumerate(pd.read_csv(z.open(name),sep=';',encoding='latin1',chunksize=250000)):
            generations.update(d.DT_GERACAO.unique())
            d=d[(d.ANO_ELEICAO==2026)&(d.NR_TURNO==1)&(d.CD_CARGO==1)].copy()
            total_rows += len(d)
            if (d.QT_VOTOS<0).any(): raise ValueError('Votos negativos')
            cols=KEY+['NM_MUNICIPIO','NR_LOCAL_VOTACAO','NR_VOTAVEL','NM_VOTAVEL','QT_VOTOS']
            d=d[cols]
            section_parts.append(d)
            parts.append(d.groupby(['SG_UF','CD_MUNICIPIO','NM_MUNICIPIO','NR_VOTAVEL','NM_VOTAVEL'],dropna=False).QT_VOTOS.sum())
            print(f'Lote {i+1}: {total_rows:,} registros',flush=True)
    sec=pd.concat(section_parts,ignore_index=True)
    if sec.duplicated(KEY+['NR_VOTAVEL']).any(): raise ValueError('Duplicação seção/votável')
    sec.to_parquet(OUT/'votos_secoes_2026_t1.parquet',index=False)
    mun=pd.concat(parts).groupby(level=list(range(5))).sum().reset_index()
    mun.to_csv(OUT/'votos_municipios_2026_t1.csv',sep=';',index=False,encoding='utf-8-sig')
    uf=mun.groupby(['SG_UF','NR_VOTAVEL','NM_VOTAVEL'],as_index=False).QT_VOTOS.sum()
    uf.to_csv(OUT/'votos_estados_2026_t1.csv',sep=';',index=False,encoding='utf-8-sig')
    joined=sec.merge(loc[KEY+['NM_BAIRRO']],on=KEY,how='left',validate='many_to_one',indicator=True)
    joined.NM_BAIRRO=joined.NM_BAIRRO.fillna('SEM CORRESPONDENCIA')
    bairros=joined.groupby(['SG_UF','CD_MUNICIPIO','NM_MUNICIPIO','NM_BAIRRO','NR_VOTAVEL','NM_VOTAVEL'],dropna=False,as_index=False).QT_VOTOS.sum()
    bairros.to_csv(OUT/'votos_bairros_local_votacao_2026_t1.csv',sep=';',index=False,encoding='utf-8-sig')
    local=sec.groupby(['SG_UF','CD_MUNICIPIO','NM_MUNICIPIO','NR_ZONA','NR_LOCAL_VOTACAO','NR_VOTAVEL','NM_VOTAVEL'],as_index=False).QT_VOTOS.sum()
    local.to_parquet(OUT/'votos_locais_2026_t1.parquet',index=False)
    assert sec.QT_VOTOS.sum()==mun.QT_VOTOS.sum()==uf.QT_VOTOS.sum()==bairros.QT_VOTOS.sum()
    audit={'linhas_votos':total_rows,'datas_geracao_votos':sorted(generations),'votos_totais':int(sec.QT_VOTOS.sum()),'municipios_brasil':len(mun[mun.SG_UF!='ZZ'][['SG_UF','CD_MUNICIPIO']].drop_duplicates()),'secoes':len(sec[KEY].drop_duplicates()),'bairros_cadastrais':len(bairros[['SG_UF','CD_MUNICIPIO','NM_BAIRRO']].drop_duplicates()),'votos_sem_correspondencia_cadastro':int(joined.loc[joined._merge!='both','QT_VOTOS'].sum()),'reconciliacao_agregacoes':'OK','votaveis':mun.groupby(['NR_VOTAVEL','NM_VOTAVEL']).QT_VOTOS.sum().reset_index().to_dict('records')}
    (OUT/'auditoria_tse.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=True),flush=True)

if __name__=='__main__': main()
