"""Associações territoriais descritivas, sensibilidade e relatório local."""
from pathlib import Path
import json, html, math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs'
INDICATORS={
 'renda_media_responsavel_com_renda_2022':'Renda média do responsável com renda (R$, 2022)',
 'pct_analfabetismo_15mais':'Analfabetismo, 15+ (%, 2022)',
 'pct_60mais':'População 60+ (%, 2022)',
 'pct_15a29':'População 15–29 (%, 2022)',
 'densidade_hab_km2':'Densidade demográfica (hab/km², 2022)',
 'pct_domicilios_rede_agua':'Domicílios com rede de água (%, 2022)',
 'pct_domicilios_rede_esgoto_pluvial':'Domicílios com esgoto em rede geral/pluvial (%, 2022)',
 'pct_matriculas_privadas':'Matrículas básicas em escolas privadas (%, 2025)',
 'pct_matriculas_escolas_rurais':'Matrículas básicas em escolas rurais (%, 2025)',
 'superior_presencial_por_mil_hab_2022':'Matrículas superiores presenciais 2024 / mil hab. 2022',
 'basica_por_mil_hab_2022':'Matrículas básicas 2025 / mil hab. 2022',
 'saldo_caged_por_mil_hab_2022':'Saldo Caged agosto/2026 / mil hab. 2022',
}

def correlation(x,y,w=None):
    x,y=np.asarray(x,float),np.asarray(y,float)
    if len(x)<3 or np.std(x)==0 or np.std(y)==0:return np.nan
    if w is None:return float(np.corrcoef(x,y)[0,1])
    w=np.asarray(w,float); w=w/w.sum()
    x=x-np.sum(w*x); y=y-np.sum(w*y)
    den=np.sqrt(np.sum(w*x*x)*np.sum(w*y*y))
    return float(np.sum(w*x*y)/den) if den>0 else np.nan

def associations(d,candidates,scope):
    rows=[]
    for cand in candidates:
        for indicator in INDICATORS:
            if indicator not in d:continue
            z=d[[indicator,str(cand),'votos_validos','SG_UF']].dropna()
            if len(z)<20:continue
            x,y=z[indicator],z[str(cand)]
            rankx,ranky=x.rank(),y.rank()
            withinx=rankx-rankx.groupby(z.SG_UF).transform('mean')
            withiny=ranky-ranky.groupby(z.SG_UF).transform('mean')
            rows.append({'recorte':scope,'candidato_numero':cand,'indicador':indicator,'n_territorios':len(z),'pearson':correlation(x,y),'spearman':correlation(rankx,ranky),'pearson_ponderado_votos_validos':correlation(x,y,z.votos_validos),'correlacao_ranks_ajustada_uf':correlation(withinx,withiny)})
    return rows

def main():
    audit=json.loads((OUT/'auditoria_integracao.json').read_text(encoding='utf-8'))
    tseaudit=json.loads((OUT/'auditoria_tse.json').read_text(encoding='utf-8'))
    cand={v['NR_VOTAVEL']:v['NM_VOTAVEL'] for v in tseaudit['votaveis'] if v['NR_VOTAVEL'] not in [95,96]}
    votes=pd.read_csv(OUT/'votos_municipios_2026_t1.csv',sep=';',dtype={'CD_MUNICIPIO':str})
    votes=votes[(votes.SG_UF!='ZZ')&votes.NR_VOTAVEL.isin(cand)].copy()
    wide=votes.pivot_table(index=['SG_UF','CD_MUNICIPIO','NM_MUNICIPIO'],columns='NR_VOTAVEL',values='QT_VOTOS',aggfunc='sum',fill_value=0).reindex(columns=list(cand),fill_value=0)
    wide['votos_validos']=wide.sum(axis=1)
    for c in cand:wide[c]=100*wide[c]/wide.votos_validos.replace(0,np.nan)
    wide=wide.reset_index();wide.columns=wide.columns.map(str)
    cross=pd.read_parquet(OUT/'correspondencia_tse_ibge.parquet')
    wide=wide.merge(cross[['SG_UF','CD_MUNICIPIO','CD_MUN']],on=['SG_UF','CD_MUNICIPIO'],validate='one_to_one')
    ind=pd.read_parquet(OUT/'indicadores_municipais.parquet')
    assert not wide.loc[wide.CD_MUN.notna(),'CD_MUN'].duplicated().any()
    d=wide.merge(ind.drop(columns=['SG_UF']),on='CD_MUN',how='left',validate='many_to_one')
    d['alerta_limite_territorial']=np.where((d.SG_UF=='MT')&d.NM_MUNICIPIO.isin(['SORRISO','NOVA UBIRATÃ','BOA ESPERANÇA DO NORTE']),'ALTERACAO_TERRITORIAL_2025','')
    d.to_parquet(OUT/'analise_municipal_ampla.parquet',index=False)
    d.to_csv(OUT/'analise_municipal_ampla.csv',sep=';',index=False,encoding='utf-8-sig')
    eligible=d[d.alerta_limite_territorial==''].copy()
    rows=associations(eligible,cand,'Brasil — municípios')
    for uf,g in eligible.groupby('SG_UF'):rows+=associations(g,cand,'UF '+uf+' — municípios')
    corr=pd.DataFrame(rows)
    corr['candidato']=corr.candidato_numero.map(cand)
    corr.to_csv(OUT/'correlacoes_municipais.csv',sep=';',index=False,encoding='utf-8-sig')
    # Intervalos de estabilidade por reamostragem de UFs: exploratórios; não testes causais.
    rng=np.random.default_rng(20261012)
    bs=[]
    for c in cand:
        for indicator in INDICATORS:
            z=eligible[[indicator,str(c),'SG_UF']].dropna()
            ranked=z[[indicator,str(c)]].rank().to_numpy(float)
            blocks=[ranked[z.SG_UF.eq(uf).to_numpy()] for uf in sorted(z.SG_UF.unique())]
            if len(blocks)<10:continue
            stats=[]
            for _ in range(300):
                arr=np.concatenate([blocks[i] for i in rng.integers(0,len(blocks),len(blocks))])
                stats.append(correlation(arr[:,0],arr[:,1]))
            bs.append({'candidato_numero':c,'indicador':indicator,'q025_estabilidade_blocos_uf':float(np.nanquantile(stats,.025)),'q975_estabilidade_blocos_uf':float(np.nanquantile(stats,.975)),'replicacoes':300})
    pd.DataFrame(bs).to_csv(OUT/'estabilidade_correlacoes_blocos_uf.csv',sep=';',index=False,encoding='utf-8-sig')
    # Modelo ajustado: associação em pontos percentuais por um desvio-padrão, com efeitos fixos de UF.
    predictors=['renda_media_responsavel_com_renda_2022','pct_analfabetismo_15mais','pct_60mais','densidade_hab_km2','pct_matriculas_escolas_rurais','superior_presencial_por_mil_hab_2022','saldo_caged_por_mil_hab_2022','populacao_2022']
    z=eligible.dropna(subset=predictors).copy()
    X=z[predictors].copy()
    for col in ['renda_media_responsavel_com_renda_2022','densidade_hab_km2','superior_presencial_por_mil_hab_2022','populacao_2022']:X[col]=np.log1p(X[col])
    X=(X-X.mean())/X.std(ddof=0)
    X=pd.concat([X,pd.get_dummies(z.SG_UF,prefix='UF',drop_first=True,dtype=float)],axis=1)
    arr=np.column_stack([np.ones(len(X)),X.to_numpy(float)])
    models=[]
    for c in cand:
        y=z[str(c)].to_numpy(float)
        coef=np.linalg.lstsq(arr,y,rcond=None)[0]
        pred=arr@coef
        r2=1-np.sum((y-pred)**2)/np.sum((y-y.mean())**2)
        for i,p in enumerate(predictors):models.append({'candidato_numero':c,'candidato':cand[c],'indicador':p,'coeficiente_pp_por_desvio_padrao':coef[i+1],'transformacao':'log1p' if p in [predictors[0],predictors[3],predictors[5],predictors[7]] else 'original','n_municipios':len(z),'r2_descritivo':r2,'condicao_matriz':float(np.linalg.cond(arr))})
    pd.DataFrame(models).to_csv(OUT/'modelo_ajustado_descritivo.csv',sep=';',index=False,encoding='utf-8-sig')
    # Agrega votos associados ao MESMO código de bairro antes de calcular relações exploratórias.
    bj=pd.read_parquet(OUT/'base_bairros_cruzamento_exploratorio.parquet')
    good=bj[bj.CD_BAIRRO.notna() & bj.NR_VOTAVEL.isin(cand)].copy()
    good=good[~((good.SG_UF=='MT')&good.NM_MUNICIPIO.isin(['SORRISO','NOVA UBIRATÃ','BOA ESPERANÇA DO NORTE']))]
    bwide=good.pivot_table(index=['SG_UF','CD_MUN','CD_BAIRRO'],columns='NR_VOTAVEL',values='QT_VOTOS',aggfunc='sum',fill_value=0).reindex(columns=list(cand),fill_value=0)
    bwide['votos_validos']=bwide.sum(axis=1)
    for c in cand:bwide[c]=100*bwide[c]/bwide.votos_validos.replace(0,np.nan)
    bwide=bwide.reset_index();bwide.columns=bwide.columns.map(str)
    bind=good[['CD_BAIRRO']+[c for c in INDICATORS if c in good]].drop_duplicates()
    bwide=bwide.merge(bind,on='CD_BAIRRO',validate='many_to_one')
    bc=pd.DataFrame(associations(bwide,cand,'Bairros — correspondência nominal exploratória'))
    bc['candidato']=bc.candidato_numero.map(cand)
    bc.to_csv(OUT/'correlacoes_bairros_exploratorias.csv',sep=';',index=False,encoding='utf-8-sig')
    summary=[]
    for uf,g in d.groupby('SG_UF'):
        for c in cand:summary.append({'uf':uf,'candidato':cand[c],'numero':c,'pct_votos_validos':float(np.average(g[str(c)],weights=g.votos_validos)),'municipios':len(g),'municipios_com_ibge':int(g.populacao_2022.notna().sum())})
    pd.DataFrame(summary).to_csv(OUT/'resumo_estados.csv',sep=';',index=False,encoding='utf-8-sig')
    # Dados compactos para relatório offline. Nenhuma dependência externa ou telemetria.
    payload={'candidatos':cand,'indicadores':INDICATORS,'auditoria':audit,'auditoria_tse':tseaudit,'municipios':d[['SG_UF','NM_MUNICIPIO','CD_MUNICIPIO','CD_MUN','votos_validos','alerta_limite_territorial']+list(map(str,cand))+list(INDICATORS)].round(5).replace({np.nan:None}).to_dict('records'),'correlacoes':corr.round(6).replace({np.nan:None}).to_dict('records'),'estados':summary}
    def clean(v):
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
        if isinstance(v,list):return [clean(x) for x in v]
        if isinstance(v,float) and not math.isfinite(v):return None
        return v
    (OUT/'dados_relatorio.json').write_text(json.dumps(clean(payload),ensure_ascii=False,allow_nan=False),encoding='utf-8')
    national=corr[corr.recorte.str.startswith('Brasil')].copy()
    national['abs_spearman']=national.spearman.abs()
    print(national.sort_values('abs_spearman',ascending=False)[['candidato','indicador','n_territorios','spearman','correlacao_ranks_ajustada_uf']].head(12).to_string(index=False),flush=True)
    print('Análises concluídas; nenhum p-valor ou alegação de causalidade.',flush=True)

if __name__=='__main__':main()
