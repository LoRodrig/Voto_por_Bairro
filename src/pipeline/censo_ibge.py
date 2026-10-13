"""Censo 2022 por bairro (IBGE) e correspondência de códigos TSE ↔ IBGE. Não aproxima nomes por similaridade."""
from pathlib import Path
import re, unicodedata, zipfile
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
RAW, OUT=ROOT/'data/raw',ROOT/'outputs'

def norm(v):
    s=unicodedata.normalize('NFKD',str(v)).encode('ascii','ignore').decode().upper()
    return re.sub('[^A-Z0-9]','',s)

def readzip(path,contains=None,**kw):
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.lower().endswith('.csv') and (contains is None or contains in n)]
        if len(names)!=1: raise ValueError((path,names))
        return pd.read_csv(z.open(names[0]),sep=';',encoding='latin1',**kw)

def num(s):
    return pd.to_numeric(s.astype(str).str.replace(',','.',regex=False),errors='coerce')

def save(d,name):
    d.to_parquet(OUT/(name+'.parquet'),index=False)
    d.to_csv(OUT/(name+'.csv'),index=False,sep=';',encoding='utf-8-sig')

def ibge_bairros():
    """Características do Censo 2022 por bairro do IBGE (uma linha por código e nome de bairro)."""
    idcol='CD_BAIRRO'
    base=readzip(next(RAW.glob('ibge_bairros_basico*.zip')),dtype=str)
    base.columns=base.columns.str.upper()
    keep=[c for c in [idcol,'CD_MUN','NM_MUN','NM_BAIRRO','CD_UF','AREA_KM2','V0001'] if c in base]
    base=base[list(dict.fromkeys(keep))].copy()
    base['populacao_2022']=num(base.pop('V0001'))
    base['area_km2']=num(base.pop('AREA_KM2'))
    temas={'demografia':['V01006','V01034','V01035','V01036','V01040','V01041'],'caracteristicas_domicilio2':['V00111','V00309'],'renda':['V06001','V06004'],
           'cor_ou_raca':['V01317','V01318','V01319','V01320','V01321'],'caracteristicas_domicilio1':['V00001','V00049'],'parentesco':['V01042','V01063']}
    for tema,cols in temas.items():
        d=readzip(next(RAW.glob(f'ibge_bairros_{tema}*.zip')),dtype=str)
        d.columns=d.columns.str.upper()
        d=d[[idcol,'NM_BAIRRO']+cols].copy()
        for c in cols:d[c]=num(d[c])
        base=base.merge(d,on=[idcol,'NM_BAIRRO'],validate='one_to_one',how='left')
    base['pct_60mais']=100*(base.V01040+base.V01041)/base.V01006.replace(0,np.nan)
    base['pct_15a29']=100*(base.V01034+base.V01035+base.V01036)/base.V01006.replace(0,np.nan)
    base['pct_domicilios_rede_agua']=100*base.V00111/base.V06001.replace(0,np.nan)
    base['pct_domicilios_rede_esgoto_pluvial']=100*base.V00309/base.V06001.replace(0,np.nan)
    base['densidade_hab_km2']=base.populacao_2022/base.area_km2.replace(0,np.nan)
    base['pct_pretos_pardos']=100*(base.V01318+base.V01320)/base[temas['cor_ou_raca']].sum(axis=1).replace(0,np.nan)  # pretos + pardos sobre as cinco categorias
    base['pct_apartamento']=100*base.V00049/base.V00001.replace(0,np.nan)  # domicílios particulares permanentes ocupados
    base['pct_mulheres_responsaveis']=100*base.V01063/base.V01042.replace(0,np.nan)
    base=base.rename(columns={'V06004':'renda_media_responsavel_com_renda_2022'})
    save(base,'ibge_bairros')
    return base

def correspondencia():
    """Código do município no TSE ↔ código IBGE, pela tabela oficial do TSE."""
    votes=pd.read_csv(OUT/'votos_municipios_2026_t1.csv',sep=';',dtype={'CD_MUNICIPIO':str})
    votes=votes[votes.SG_UF!='ZZ'].copy()
    tse=votes[['SG_UF','CD_MUNICIPIO','NM_MUNICIPIO']].drop_duplicates()
    tse['nome_normalizado']=tse.NM_MUNICIPIO.map(norm)
    official=readzip(RAW/'municipio_tse_ibge.zip',dtype=str)
    official=official.rename(columns={'CD_MUNICIPIO_TSE':'CD_MUNICIPIO','CD_MUNICIPIO_IBGE':'CD_MUN'})
    official.CD_MUNICIPIO=pd.to_numeric(official.CD_MUNICIPIO).astype('int64').astype(str)
    cross=tse.merge(official[['SG_UF','CD_MUNICIPIO','CD_MUN']],how='left',on=['SG_UF','CD_MUNICIPIO'],validate='one_to_one')
    cross['metodo_correspondencia']='TABELA_OFICIAL_TSE_IBGE'
    save(cross,'correspondencia_tse_ibge')
    return cross

def main():
    ibge_bairros()
    correspondencia()

if __name__=='__main__':main()
