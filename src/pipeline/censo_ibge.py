"""Integra fontes por chaves auditáveis. Não aproxima nomes por similaridade."""
from pathlib import Path
import json, re, unicodedata, zipfile
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

def ibge(level):
    idcol='CD_MUN' if level=='municipios' else 'CD_BAIRRO'
    base=readzip(next(RAW.glob(f'ibge_{level}_basico*.zip')),dtype=str)
    base.columns=base.columns.str.upper()
    keep=[c for c in [idcol,'CD_MUN','NM_MUN','NM_BAIRRO','CD_UF','AREA_KM2','V0001'] if c in base]
    base=base[list(dict.fromkeys(keep))].copy()
    base['populacao_2022']=num(base.pop('V0001'))
    base['area_km2']=num(base.pop('AREA_KM2'))
    variables={'alfabetizacao':['V00900','V00901'],'demografia':['V01006','V01034','V01035','V01036','V01040','V01041'],'caracteristicas_domicilio2':['V00111','V00309'],'renda':['V06001','V06004','V06006']}
    for tema,cols in variables.items():
        d=readzip(next(RAW.glob(f'ibge_{level}_{tema}*.zip')),dtype=str)
        d.columns=d.columns.str.upper()
        joincols=[idcol] if level=='municipios' else [idcol,'NM_BAIRRO']
        d=d[joincols+cols]
        for c in cols:d[c]=num(d[c])
        base=base.merge(d,on=joincols,validate='one_to_one',how='left')
    base['pct_analfabetismo_15mais']=100*base.V00901/(base.V00900+base.V00901).replace(0,np.nan)
    base['pct_60mais']=100*(base.V01040+base.V01041)/base.V01006.replace(0,np.nan)
    base['pct_15a29']=100*(base.V01034+base.V01035+base.V01036)/base.V01006.replace(0,np.nan)
    base['pct_domicilios_rede_agua']=100*base.V00111/base.V06001.replace(0,np.nan)
    base['pct_domicilios_rede_esgoto_pluvial']=100*base.V00309/base.V06001.replace(0,np.nan)
    base['densidade_hab_km2']=base.populacao_2022/base.area_km2.replace(0,np.nan)
    if level=='bairros':  # só nível bairro; o atlas nacional segue como estava
        extras={'cor_ou_raca':['V01317','V01318','V01319','V01320','V01321'],'caracteristicas_domicilio1':['V00001','V00049'],'parentesco':['V01042','V01063']}
        for tema,cols in extras.items():
            d=readzip(next(RAW.glob(f'ibge_bairros_{tema}*.zip')),dtype=str);d.columns=d.columns.str.upper()
            d=d[[idcol,'NM_BAIRRO']+cols].copy()
            for c in cols:d[c]=num(d[c])
            base=base.merge(d,on=[idcol,'NM_BAIRRO'],validate='one_to_one',how='left')
        base['pct_pretos_pardos']=100*(base.V01318+base.V01320)/base[extras['cor_ou_raca']].sum(axis=1).replace(0,np.nan)  # pretos + pardos sobre as cinco categorias
        base['pct_apartamento']=100*base.V00049/base.V00001.replace(0,np.nan)  # domicílios particulares permanentes ocupados
        base['pct_mulheres_responsaveis']=100*base.V01063/base.V01042.replace(0,np.nan)
    base=base.rename(columns={'V06004':'renda_media_responsavel_com_renda_2022','V06006':'renda_mediana_responsavel_com_renda_2022'})
    save(base,'ibge_'+level)
    return base

def main():
    m,b=ibge('municipios'),ibge('bairros')
    print('IBGE carregado',len(m),len(b),flush=True)
    cols=['CO_MUNICIPIO','NO_MUNICIPIO','CO_UF','SG_UF','CO_ENTIDADE','TP_DEPENDENCIA','TP_LOCALIZACAO','QT_MAT_BAS','QT_MAT_MED','QT_MAT_EJA']
    ed=readzip(RAW/'inep_basica_2025.zip','Tabela_Matricula',usecols=cols,dtype=str)
    if ed.CO_ENTIDADE.duplicated().any():raise ValueError('Escolas duplicadas na tabela de matrículas')
    geo=ed[['CO_MUNICIPIO','NO_MUNICIPIO','CO_UF','SG_UF']].drop_duplicates()
    save(geo,'municipios_inep_2025')
    for c in ['QT_MAT_BAS','QT_MAT_MED','QT_MAT_EJA']: ed[c]=num(ed[c])
    ed['matriculas_privadas_2025']=ed.QT_MAT_BAS.where(ed.TP_DEPENDENCIA=='4',0)
    ed['matriculas_escolas_rurais_2025']=ed.QT_MAT_BAS.where(ed.TP_LOCALIZACAO=='2',0)
    counts=ed.groupby('CO_MUNICIPIO')[['QT_MAT_BAS','QT_MAT_MED','QT_MAT_EJA','matriculas_privadas_2025','matriculas_escolas_rurais_2025']].sum(min_count=1)
    counts['escolas_com_matriculas_2025']=ed[ed.QT_MAT_BAS>0].groupby('CO_MUNICIPIO').CO_ENTIDADE.nunique()
    # Se algum valor original de uma soma estiver suprimido, a soma fica ausente.
    for c in ['QT_MAT_BAS','QT_MAT_MED','QT_MAT_EJA']:
        incomplete=ed[c].isna().groupby(ed.CO_MUNICIPIO).any()
        counts.loc[incomplete,c]=np.nan
    counts=counts.reset_index().rename(columns={'CO_MUNICIPIO':'CD_MUN','QT_MAT_BAS':'matriculas_basica_2025','QT_MAT_MED':'matriculas_medio_2025','QT_MAT_EJA':'matriculas_eja_2025'})
    counts['pct_matriculas_privadas']=100*counts.matriculas_privadas_2025/counts.matriculas_basica_2025.replace(0,np.nan)
    counts['pct_matriculas_escolas_rurais']=100*counts.matriculas_escolas_rurais_2025/counts.matriculas_basica_2025.replace(0,np.nan)
    save(counts,'educacao_basica_municipios')
    sup=readzip(RAW/'inep_superior_2024.zip','CADASTRO_CURSOS',usecols=['CO_MUNICIPIO','CO_IES','CO_CURSO','TP_MODALIDADE_ENSINO','QT_MAT'],dtype=str)
    sup.QT_MAT=num(sup.QT_MAT)
    presencial=sup[(sup.TP_MODALIDADE_ENSINO=='1')&sup.CO_MUNICIPIO.str.fullmatch(r'\d{7}',na=False)]
    higher=presencial.groupby('CO_MUNICIPIO').agg(matriculas_superior_presencial_2024=('QT_MAT','sum'),cursos_superior_presencial_2024=('CO_CURSO','nunique'),ies_com_oferta_presencial_2024=('CO_IES','nunique')).reset_index().rename(columns={'CO_MUNICIPIO':'CD_MUN'})
    save(higher,'educacao_superior_municipios')
    print('Educação agregada',flush=True)
    # Caged usa código municipal de seis dígitos, compatibilizado com prefixo IBGE.
    chunks=[]
    for d in pd.read_csv(RAW/'CAGEDMOV202608.txt',sep=';',encoding='utf-8',usecols=['competênciamov','município','saldomovimentação'],dtype=str,chunksize=500000):
        if not d['competênciamov'].eq('202608').all(): raise ValueError('Competência Caged divergente')
        s=pd.to_numeric(d['saldomovimentação'],errors='raise')
        if not s.isin([-1,1]).all():raise ValueError('Saldos inesperados')
        d['admissoes_caged_agosto2026']=(s==1).astype(int)
        d['desligamentos_caged_agosto2026']=(s==-1).astype(int)
        chunks.append(d.groupby('município')[['admissoes_caged_agosto2026','desligamentos_caged_agosto2026']].sum())
    cag=pd.concat(chunks).groupby(level=0).sum().reset_index().rename(columns={'município':'codigo_caged'})
    cag['saldo_caged_agosto2026']=cag.admissoes_caged_agosto2026-cag.desligamentos_caged_agosto2026
    save(cag,'caged_municipios_agosto2026')
    ufmap=geo[['CO_UF','SG_UF']].dropna().drop_duplicates().rename(columns={'CO_UF':'CD_UF'})
    m=m.merge(ufmap,on='CD_UF',validate='many_to_one',how='left')
    m=m.merge(counts,on='CD_MUN',how='left',validate='one_to_one').merge(higher,on='CD_MUN',how='left',validate='one_to_one')
    for c in higher.columns.drop('CD_MUN'):m[c]=m[c].fillna(0)
    m['codigo_caged']=m.CD_MUN.str[:6]
    assert not m.codigo_caged.duplicated().any()
    m=m.merge(cag,on='codigo_caged',how='left',validate='one_to_one')
    for c in cag.columns.drop('codigo_caged'):m[c]=m[c].fillna(0)
    m['saldo_caged_por_mil_hab_2022']=1000*m.saldo_caged_agosto2026/m.populacao_2022
    m['superior_presencial_por_mil_hab_2022']=1000*m.matriculas_superior_presencial_2024/m.populacao_2022
    m['basica_por_mil_hab_2022']=1000*m.matriculas_basica_2025/m.populacao_2022
    m['nome_normalizado']=m.NM_MUN.map(norm)
    assert not m.duplicated(['SG_UF','nome_normalizado']).any()
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
    votes=votes.merge(cross[['SG_UF','CD_MUNICIPIO','CD_MUN']],on=['SG_UF','CD_MUNICIPIO'],validate='many_to_one')
    valid=votes[~votes.NR_VOTAVEL.isin([95,96])].groupby(['SG_UF','CD_MUNICIPIO']).QT_VOTOS.sum().rename('votos_validos')
    votes=votes.merge(valid,on=['SG_UF','CD_MUNICIPIO'],validate='many_to_one')
    votes['pct_votos_validos']=100*votes.QT_VOTOS/votes.votos_validos.replace(0,np.nan)
    votes.loc[votes.NR_VOTAVEL.isin([95,96]),'pct_votos_validos']=np.nan
    joined=votes.merge(m.drop(columns=['SG_UF','nome_normalizado']),on='CD_MUN',how='left',validate='many_to_one')
    save(joined,'base_municipal_integrada')
    save(m,'indicadores_municipais')
    # Correspondência NOMINAL de bairros: candidata à validação cartográfica, não equivalência comprovada.
    bv=pd.read_csv(OUT/'votos_bairros_local_votacao_2026_t1.csv',sep=';',dtype={'CD_MUNICIPIO':str})
    bv=bv[bv.SG_UF!='ZZ'].merge(cross[['SG_UF','CD_MUNICIPIO','CD_MUN']],on=['SG_UF','CD_MUNICIPIO'],how='left',validate='many_to_one')
    bv['bairro_normalizado']=bv.NM_BAIRRO.map(norm)
    b['bairro_normalizado']=b.NM_BAIRRO.map(norm)
    amb=b.duplicated(['CD_MUN','bairro_normalizado'],False)|b.CD_BAIRRO.duplicated(False)
    save(b[amb],'bairros_ibge_nomes_ambiguos')
    b=b[~amb].drop(columns=['NM_BAIRRO','NM_MUN'])
    bj=bv.merge(b,on=['CD_MUN','bairro_normalizado'],how='left',validate='many_to_one')
    bj['status_cruzamento']=np.where(bj.CD_BAIRRO.notna(),'NOMINAL_EXATO_A_VALIDAR_LIMITES','SEM_CORRESPONDENCIA')
    save(bj,'base_bairros_cruzamento_exploratorio')
    audit={'municipios_tse':len(cross),'municipios_correspondentes':int(cross.CD_MUN.notna().sum()),'municipios_com_censo':int(cross.CD_MUN.isin(m.CD_MUN).sum()),'municipios_sem_correspondencia':cross[cross.CD_MUN.isna()].to_dict('records'),'municipios_sem_censo':cross[~cross.CD_MUN.isin(m.CD_MUN)].to_dict('records'),'censo_municipios':len(m),'bairros_tse':len(bv[['SG_UF','CD_MUNICIPIO','NM_BAIRRO']].drop_duplicates()),'bairros_correspondencia_nominal':len(bj[bj.CD_BAIRRO.notna()][['SG_UF','CD_MUNICIPIO','NM_BAIRRO']].drop_duplicates()),'caged_total_admissoes':int(cag.admissoes_caged_agosto2026.sum()),'caged_total_desligamentos':int(cag.desligamentos_caged_agosto2026.sum()),'superior_matriculas_ead_nao_territorializadas':float(sup.loc[sup.TP_MODALIDADE_ENSINO=='2','QT_MAT'].sum()),'data_referencia_censo':2022,'basica':2025,'superior':2024,'caged_competencia':'202608','caged_escopo':'MOV agosto; não inclui revisões FOR/EXC posteriores; não é estoque nem taxa de desemprego'}
    (OUT/'auditoria_integracao.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
