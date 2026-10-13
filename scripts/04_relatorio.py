from pathlib import Path
import hashlib, html, json, re, zipfile
import importlib, sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
sys.path.insert(0,str(ROOT/'scripts'))
IND_BAIRRO=['renda_media_responsavel_com_renda_2022','pct_analfabetismo_15mais','pct_60mais','pct_15a29','densidade_hab_km2','pct_domicilios_rede_agua','pct_domicilios_rede_esgoto_pluvial']

def num(v):
    return None if v is None or (isinstance(v,float) and not np.isfinite(v)) else float(v)

def bairros_ibge(cands):
    """Bairros IBGE com votos por join espacial (06_bairros_espacial) e correlações (07), uma entrada por cidade gerada."""
    esp=importlib.import_module('06_bairros_espacial')
    ib=pd.read_parquet(OUT/'ibge_bairros.parquet').set_index('CD_BAIRRO')
    res={}
    for f in sorted(OUT.glob('votos_bairros_ibge_*.parquet')):
        m=f.stem.rsplit('_',1)[1]
        v=pd.read_parquet(f)
        w=v[v.NR_VOTAVEL.isin(cands)].pivot_table(index='CD_BAIRRO',columns='NR_VOTAVEL',values='QT_VOTOS',aggfunc='sum',fill_value=0).reindex(columns=cands,fill_value=0)
        excl=pd.read_csv(OUT/f'exclusoes_bairros_{m}.csv',sep=';')
        cob=100*v.QT_VOTOS.sum()/(v.QT_VOTOS.sum()+excl.QT_VOTOS.sum())
        polys,rows={},{}
        for cd,rings in esp.ler_malha(ROOT/'data/raw/PR_bairros_CD2022.gpkg',m):
            polys.setdefault(cd,[]).append([[round(la,5),round(lo,5)] for lo,la in rings[0]])
        for cd in polys:
            r=w.loc[cd] if cd in w.index else None
            rows[cd]={'nome':ib.NM_BAIRRO.get(cd,cd),'total':None if r is None else int(r.sum()),'v':None if r is None else [int(x) for x in r],'ind':{k:num(ib[k].get(cd)) for k in IND_BAIRRO}}
        cor=pd.read_csv(OUT/f'correlacoes_bairros_{m}.csv',sep=';')
        res[m]={'nome':str(ib.loc[ib.CD_MUN==m,'NM_MUN'].iloc[0]),'cobertura_votos_pct':round(cob,2),'bairros':rows,'poligonos':polys,
                'correlacoes':[{k:(num(x) if isinstance(x,float) else x) for k,x in r.items()} for r in cor.drop(columns=['candidato']).to_dict('records')]}
    return res

def main():
    data=json.loads((OUT/'dados_relatorio.json').read_text(encoding='utf-8'))
    votes=pd.read_csv(OUT/'votos_bairros_local_votacao_2026_t1.csv',sep=';',dtype={'CD_MUNICIPIO':str})
    candidates=list(map(int,data['candidatos']))
    votes=votes[(votes.SG_UF!='ZZ')&votes.NR_VOTAVEL.isin(candidates)]
    b=votes.pivot_table(index=['SG_UF','CD_MUNICIPIO','NM_BAIRRO'],columns='NR_VOTAVEL',values='QT_VOTOS',aggfunc='sum',fill_value=0).reindex(columns=candidates,fill_value=0)
    data['bairro_candidatos']=candidates
    data['bairros_ibge']=bairros_ibge(candidates)
    data['bairros']={}
    for key,values in b.iterrows():
        code=key[0]+'|'+key[1]
        data['bairros'].setdefault(code,[]).append([key[2],int(values.sum())]+[int(values[c]) for c in candidates])
    cor=pd.read_csv(OUT/'correlacoes_municipais.csv',sep=';')
    cor=cor[cor.recorte.str.startswith('Brasil')]
    national=pd.read_csv(OUT/'votos_estados_2026_t1.csv',sep=';')
    leaders=national[(national.SG_UF!='ZZ')&national.NR_VOTAVEL.isin(candidates)].groupby('NR_VOTAVEL').QT_VOTOS.sum().nlargest(2).index
    rows=[]
    for c in leaders:
        for indicator in ['renda_media_responsavel_com_renda_2022','pct_analfabetismo_15mais','superior_presencial_por_mil_hab_2022','saldo_caged_por_mil_hab_2022']:
            s=cor[(cor.candidato_numero==c)&(cor.indicador==indicator)].iloc[0]
            rows.append([data['candidatos'][str(c)],data['indicadores'][indicator],int(s.n_territorios),round(s.spearman,3),round(s.correlacao_ranks_ajustada_uf,3)])
    findings='<p>Para os dois candidatos com maior votação nacional, nesta extração:</p><div class="scroll"><table><thead><tr><th>Candidato</th><th>Indicador</th><th>Municípios</th><th>Spearman</th><th>Ranks ajustados por UF</th></tr></thead><tbody>'
    findings+=''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in r)+'</tr>' for r in rows)
    findings+='</tbody></table></div><p>A relação com renda e analfabetismo é mais acentuada no conjunto nacional do que após retirar as diferenças médias entre estados. A associação com o saldo mensal de emprego é próxima de zero para ambos. Esses resultados descrevem territórios; não caracterizam o voto de indivíduos.</p>'
    template=(ROOT/'scripts/relatorio_template.html').read_text(encoding='utf-8')
    leaflet=ROOT/'scripts/vendor/leaflet'
    template=template.replace('__LEAFLET_CSS__',(leaflet/'leaflet.css').read_text(encoding='utf-8')).replace('__LEAFLET_JS__',(leaflet/'leaflet.js').read_text(encoding='utf-8'))
    result=template.replace('__DATA__',json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('</','<\\/')).replace('__FINDINGS__',json.dumps(findings,ensure_ascii=False))
    (OUT/'relatorio_eleicoes_2026.html').write_text(result,encoding='utf-8')
    # Guarda JavaScript isolado para validação sintática; não é necessário abrir este arquivo.
    (OUT/'verificacao_relatorio.js').write_text(result.split('<script>')[-1].split('</script>')[0],encoding='utf-8')
    a=data['auditoria']; t=data['auditoria_tse']
    md=f'''# Análise territorial — presidente, primeiro turno de 2026

Extração em 12/10/2026. Votos: geração do TSE em 06/10/2026. Não substitui a consulta de atualizações posteriores do TSE.

## Entrega

- [Abrir relatório interativo local](relatorio_eleicoes_2026.html)
- {a['municipios_tse']:,} unidades municipais brasileiras na base eleitoral; correspondência oficial TSE–IBGE para todas.
- {a['municipios_com_censo']:,} municípios com dados do Censo 2022; Boa Esperança do Norte sem Censo municipal próprio em 2022.
- {t['secoes']:,} seções eleitorais incluindo exterior; {a['bairros_tse']:,} nomes de bairros cadastrais brasileiros.
- {a['bairros_correspondencia_nominal']:,} nomes de bairro associados nominalmente ao IBGE, sujeitos à validação cartográfica.
- 13 candidatos e 12 indicadores; Pearson, Spearman, análise ponderada, recortes por UF, estabilidade por blocos de UF e modelo ajustado descritivo.

## Achados descritivos

| Candidato | Indicador | Municípios | Spearman | Ranks ajustados por UF |
|---|---|---:|---:|---:|
'''
    md+='\n'.join('| '+' | '.join(map(str,r))+' |' for r in rows)
    md+='''

A associação com renda e analfabetismo perde intensidade após retirar diferenças entre estados, embora persista. A associação com o saldo Caged de agosto é próxima de zero para os dois candidatos de maior votação. Não se pode concluir causalidade, nem inferir o voto de indivíduos com base em renda ou educação.

## Limites que afetam o uso

1. Censo 2022, educação básica 2025, superior 2024 e Caged agosto/2026 têm referências distintas. As variáveis descrevem contexto histórico, não todas as condições em outubro/2026.
2. As correlações principais excluem Boa Esperança do Norte, Sorriso e Nova Ubiratã por alteração territorial. A base preserva os votos desses municípios e os sinaliza. Outras mudanças de limites não foram auditadas nacionalmente.
3. Bairros são nomes dos locais de votação; correspondência nominal não valida os limites nem a residência de eleitores. Não atribuir resultados de uma seção aos moradores do setor censitário em que a urna está instalada.
4. Renda é do responsável com renda, não renda per capita. Escolas e cursos medem oferta local, não escolaridade dos eleitores. EAD foi excluído da medida municipal de educação superior por não ter localização municipal comparável.
5. Caged usa somente MOV de agosto/2026. Não incorpora FOR/EXC, revisões posteriores, acumulado do ano, desemprego ou estoque. Porte do estabelecimento não foi utilizado devido ao aviso do MTE.
6. Não foram realizados testes de significância, FDR ou alegações de descoberta causal. As 300 reamostragens por UF são diagnóstico de estabilidade dos ranks globais fixos; não resolvem toda a dependência espacial local. Intervalos não são simultâneos.
7. Os coeficientes de regressão são descritivos, com efeitos fixos de UF e controles especificados no relatório. Não equivalem a efeitos causais; frações de votos são composicionais.
8. Sem geocodificação cartográfica validada de todos os bairros, as correlações de bairros permanecem um produto exploratório, separado do resultado municipal principal.

## Paraná por bairro IBGE

O relatório tem um mapa por bairro para as cidades do Paraná geradas (join espacial: local de votação dentro do polígono do bairro). O fundo do mapa usa tiles da internet (CARTO/OpenStreetMap). Cobertura de votos atribuídos: ver o aviso no relatório; Maringá cobre só cerca de 40%. Escolaridade e desocupação do Censo 2022 existem somente por município (`sidra_pr_municipios.parquet`).

## Arquivos

- `analise_municipal_ampla.csv` / `.parquet`: uma linha por unidade municipal, indicadores e percentual por candidato; zeros de candidatos sem votos preservados.
- `base_municipal_integrada.csv`: formato longo das linhas de votação presentes na fonte; candidatos com zero votos podem não gerar linha.
- `votos_secoes_2026_t1.parquet`: votos no maior detalhe original.
- `votos_locais_2026_t1.parquet`: votos por local de votação.
- `votos_bairros_local_votacao_2026_t1.csv`: bairros cadastrais do TSE.
- `base_bairros_cruzamento_exploratorio.csv`: integração nominal com indicadores censitários.
- `correlacoes_municipais.csv`, `correlacoes_bairros_exploratorias.csv`: resultados estatísticos, com tamanho da base em cada cálculo.
- `modelo_ajustado_descritivo.csv`: coeficientes em pontos percentuais por desvio-padrão.
- `estabilidade_correlacoes_blocos_uf.csv`: quantis da reamostragem por blocos.
- `auditoria_tse.json`, `auditoria_integracao.json`, `validacao_final.json`: controles e cobertura.
- `../data/manifesto_fontes.json`: caminhos, tamanhos e SHA-256 dos arquivos originais.

Os arquivos CSV usam ponto e vírgula, UTF-8 com BOM e ponto como separador decimal. No Excel/Power BI, selecione esses parâmetros de importação. Preserve códigos geográficos como texto.
'''
    (OUT/'LEIA_PRIMEIRO.md').write_text(md,encoding='utf-8')
    print('Relatório criado:',OUT/'relatorio_eleicoes_2026.html', 'bytes=',len(result.encode()),flush=True)

if __name__=='__main__':main()
