# Dados

Os arquivos brutos (cerca de 1,8 GB) **não ficam no repositório**. Baixe-os para `data/raw/` com estes nomes; os scripts de `src/pipeline/` procuram exatamente esses arquivos. Os resultados intermediários vão para `outputs/`, também fora do repositório.

`manifesto_fontes.csv` registra a URL, a data de download e o SHA-256 dos arquivos baixados do IBGE, para conferir a versão usada.

## Para gerar a página por bairro

**TSE** (portal de dados abertos)

| Arquivo em `data/raw/` | Conteúdo |
|---|---|
| `votacao_secao_2026_BR.zip` | Votação por seção, 2026 |
| `eleitorado_local_votacao_2026.zip` | Locais de votação, com latitude e longitude |
| `municipio_tse_ibge.zip` | Correspondência de códigos TSE e IBGE |

**IBGE · Censo 2022, agregados por bairro**

`ibge_bairros_basico_BR_20260520.zip`, `ibge_bairros_demografia_BR.zip`, `ibge_bairros_caracteristicas_domicilio1_BR.zip`, `ibge_bairros_caracteristicas_domicilio2_BR_20250417.zip`, `ibge_bairros_parentesco_BR.zip`, `ibge_bairros_cor_ou_raca_BR.zip` e `ibge_bairros_renda.zip`.

**IBGE · Censo 2022, agregados por setor censitário** (usados nos bairros do TSE, que são estimados)

`ibge_setores_basico_BR_20260520.zip`, `ibge_setores_demografia_BR.zip`, `ibge_setores_caracteristicas_domicilio1_BR.zip`, `ibge_setores_caracteristicas_domicilio2_BR_20250417.zip`, `ibge_setores_parentesco_BR.zip`, `ibge_setores_cor_ou_raca_BR.zip` e `ibge_setores_renda.zip`.

**IBGE · malhas (GeoPackage)**

`PR_bairros_CD2022.gpkg` e `PR_setores_CD2022.gpkg`.

Os agregados do Censo ficam em `ftp.ibge.gov.br/Censos/Censo_Demografico_2022/` (pastas `Agregados_por_Setores_Censitarios` e `Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel`) e as malhas em `geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/`. As URLs exatas estão no manifesto.
