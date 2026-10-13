"""Indicadores do Censo 2022 por setor censitário e agregação (mesmas fórmulas de 02_integrar.py)."""
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd

RAW = Path(__file__).resolve().parents[1] / 'data/raw'
# Características do Censo 2022 usadas por bairro (ordem e rótulos); fonte única para 07 e 08
INDICADORES = {
    'renda_media_responsavel_com_renda_2022': 'Renda média do responsável (R$)',
    'pct_pretos_pardos': 'Pretos e pardos (%)',
    'pct_60mais': 'Pessoas com 60 anos ou mais (%)',
    'pct_15a29': 'Jovens de 15 a 29 anos (%)',
    'pct_apartamento': 'Domicílios em apartamento (%)',
    'pct_mulheres_responsaveis': 'Mulheres responsáveis pelo domicílio (%)',
    'densidade_hab_km2': 'Densidade (hab/km²)',
    'pct_domicilios_rede_agua': 'Domicílios com rede de água (%)',
    'pct_domicilios_rede_esgoto_pluvial': 'Domicílios com esgoto em rede (%)',
}
FONTES = {  # zip -> variáveis usadas
    'ibge_setores_cor_ou_raca_BR.zip': ['V01317', 'V01318', 'V01319', 'V01320', 'V01321'],
    'ibge_setores_caracteristicas_domicilio1_BR.zip': ['V00001', 'V00049'],
    'ibge_setores_parentesco_BR.zip': ['V01042', 'V01063'],
    'ibge_setores_demografia_BR.zip': ['V01006', 'V01034', 'V01035', 'V01036', 'V01040', 'V01041'],
    'ibge_setores_caracteristicas_domicilio2_BR_20250417.zip': ['V00111', 'V00309'],
    'ibge_setores_renda.zip': ['V06001', 'V06004'],
    'ibge_setores_basico_BR_20260520.zip': ['V0001', 'AREA_KM2'],
}

def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(',', '.', regex=False), errors='coerce')

def _ler(zip_path, cd_mun, cols):
    with zipfile.ZipFile(zip_path) as z:
        nome = z.namelist()[0]
        head = pd.read_csv(z.open(nome), sep=';', encoding='latin1', nrows=0).columns
        real = {c.upper(): c for c in head}  # a caixa das colunas varia entre arquivos
        idc = real['CD_SETOR'] if 'CD_SETOR' in real else real['SETOR']
        out = []
        for ch in pd.read_csv(z.open(nome), sep=';', encoding='latin1', usecols=[idc] + [real[c] for c in cols], dtype=str, chunksize=200000):
            out.append(ch[ch[idc].str.startswith(cd_mun)])
    d = pd.concat(out).rename(columns={**{real[c]: c for c in cols}, idc: 'CD_SETOR'}).set_index('CD_SETOR')
    return d.apply(_num)

def ler_setores_ind(cd_mun):
    """Contagens do Censo 2022 por CD_SETOR do município (string de 7 dígitos IBGE). Falha se faltar algum setor."""
    partes = [_ler(RAW / z, cd_mun, c) for z, c in FONTES.items()]
    d = partes[0].join(partes[1:], how='outer')
    if d.empty:
        raise ValueError(f'Município {cd_mun} sem setores nos agregados')
    return d

def agregar(df):
    """Soma contagens de setores e calcula os indicadores. df precisa de V01317…V06004, V0001 e AREA_KM2."""
    s = df.sum()
    r = lambda a, b: 100 * a / b if b else np.nan
    pesos = df.V06001.where(df.V06004.notna() & (df.V06001 > 0), 0)
    pop = s.V0001
    return {'pct_apartamento': r(s.V00049, s.V00001), 'pct_mulheres_responsaveis': r(s.V01063, s.V01042),
            'pct_pretos_pardos': r(s.V01318 + s.V01320, s.V01317 + s.V01318 + s.V01319 + s.V01320 + s.V01321),
            'pct_60mais': r(s.V01040 + s.V01041, s.V01006),
            'pct_15a29': r(s.V01034 + s.V01035 + s.V01036, s.V01006),
            'pct_domicilios_rede_agua': r(s.V00111, s.V06001),
            'pct_domicilios_rede_esgoto_pluvial': r(s.V00309, s.V06001),
            'renda_media_responsavel_com_renda_2022': (df.V06004.fillna(0) * pesos).sum() / pesos.sum() if pesos.sum() else np.nan,
            'populacao_2022': pop,
            'densidade_hab_km2': pop / s.AREA_KM2 if s.AREA_KM2 else np.nan}
