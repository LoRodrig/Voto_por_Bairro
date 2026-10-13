"""Atribui votos a bairros IBGE por ponto-em-polígono (sem geopandas: shapely é bloqueado nesta máquina)."""
import argparse
import sqlite3
import struct
from pathlib import Path
import importlib
import re
import unicodedata
import numpy as np
import pandas as pd

KEY = ['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO']
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'

def _norm(v):
    return re.sub('[^A-Z0-9]', '', unicodedata.normalize('NFKD', str(v)).encode('ascii', 'ignore').decode().upper())

def agregar_setores(df):
    return importlib.import_module('09_setores').agregar(df)

def parse_coord(s):
    """Texto com vírgula decimal -> float; vazio, -1 ou inválido -> NaN."""
    v = pd.to_numeric(s.astype(str).str.replace(',', '.', regex=False), errors='coerce')
    return v.mask(v == -1)

def _ring_edges(rings):
    return [(r[:-1], r[1:]) for r in rings]

def _inside(px, py, rings):
    """Even-odd: anéis de furo contam como cruzamentos extras, então excluem o ponto."""
    n = np.zeros(len(px), int)
    for a, b in _ring_edges(rings):
        x1, y1, x2, y2 = a[:, 0], a[:, 1], b[:, 0], b[:, 1]
        cross = (y1 > py[:, None]) != (y2 > py[:, None])
        with np.errstate(divide='ignore', invalid='ignore'):
            xi = x1 + (py[:, None] - y1) * (x2 - x1) / (y2 - y1)
        n += (cross & (px[:, None] < xi)).sum(axis=1)
    return n % 2 == 1

def atribuir_bairros(locais, bairros):
    """bairros: [(CD_BAIRRO, [anel_externo, *furos])]; anel = array Nx2 (lon, lat). Uma linha de saída por entrada."""
    out = locais.copy()
    lon, lat = parse_coord(out.NR_LONGITUDE).to_numpy(), parse_coord(out.NR_LATITUDE).to_numpy()
    ok = ~(np.isnan(lon) | np.isnan(lat))
    cd = np.full(len(out), None, object)
    for code, rings in sorted(bairros, key=lambda b: b[0]):  # ordem fixa: ponto na divisa fica com o menor código
        livre = ok & np.array([c is None for c in cd])
        if not livre.any():
            break
        x0, y0 = rings[0].min(axis=0)
        x1, y1 = rings[0].max(axis=0)
        cand = livre & (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1)
        if cand.any():
            hit = _inside(lon[cand], lat[cand], rings)
            cd[np.flatnonzero(cand)[hit]] = code
    out['CD_BAIRRO'] = cd
    out['motivo_exclusao'] = np.where(~ok, 'SEM_COORDENADA', np.where(out.CD_BAIRRO.isna(), 'FORA_DE_BAIRRO', ''))
    return out

def ler_malha(gpkg, cd_mun, tabela='PR_bairros_CD2022', col='CD_BAIRRO'):
    """Lê polígonos (WKB tipo 3) do GeoPackage IBGE para um município. Mesmo código pode ter várias partes."""
    rows = sqlite3.connect(gpkg).execute(f'select {col}, geom from {tabela} where CD_MUN=?', (cd_mun,)).fetchall()
    if not rows:
        raise ValueError(f'Município {cd_mun} sem bairros na malha {gpkg}')
    out = []
    for cd, g in rows:
        off = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[g[3] >> 1 & 7]  # cabeçalho GeoPackage + envelope
        end = '<' if g[off] == 1 else '>'
        tipo, nrings = struct.unpack(end + 'II', g[off + 1:off + 9])
        assert tipo == 3, f'geometria {tipo} não suportada'
        p, rings = off + 9, []
        for _ in range(nrings):
            n = struct.unpack(end + 'I', g[p:p + 4])[0]
            rings.append(np.frombuffer(g, dtype=end + 'f8', count=2 * n, offset=p + 4).reshape(n, 2))
            p += 4 + 16 * n
        out.append((cd, rings))
    return out

def votos_por_bairro(votos, secoes_bairro):
    """votos: seção x votável; secoes_bairro: chave da seção + CD_BAIRRO + motivo_exclusao.
    Retorna (votos por CD_BAIRRO x votável, votos excluídos por motivo). Falha se não reconciliar."""
    j = votos.merge(secoes_bairro[KEY + ['CD_BAIRRO', 'motivo_exclusao']], on=KEY, how='left')
    j['motivo_exclusao'] = j.motivo_exclusao.fillna('SEM_CADASTRO')
    por = j[j.motivo_exclusao == ''].groupby(['CD_BAIRRO', 'NR_VOTAVEL'], as_index=False).QT_VOTOS.sum()
    excl = j[j.motivo_exclusao != ''].groupby('motivo_exclusao', as_index=False).QT_VOTOS.sum()
    assert por.QT_VOTOS.sum() + excl.QT_VOTOS.sum() == votos.QT_VOTOS.sum(), 'votos não reconciliam'
    return por, excl

def dissolver(rings, casas=6):
    """Contorno da união de polígonos adjacentes: arestas compartilhadas (a->b e b->a) se cancelam e o resto é encadeado em laços fechados."""
    arestas = set()
    for r in rings:
        pts = [(round(float(x), casas), round(float(y), casas)) for x, y in r]
        arestas.update((a, b) for a, b in zip(pts[:-1], pts[1:]) if a != b)
    resto = {}
    for a, b in arestas:
        if (b, a) not in arestas:
            resto.setdefault(a, []).append(b)
    laços = []
    while resto:
        ini = next(iter(resto))
        atual, laço = ini, [ini]
        while True:
            prox = resto[atual].pop()
            if not resto[atual]:
                del resto[atual]
            laço.append(prox)
            atual = prox
            if atual == ini or atual not in resto:
                break
        if atual == ini:
            laços.append(np.array(laço))
    return laços

def ler_setores_meta(gpkg, cd_mun):
    """SITUACAO (Urbana/Rural) e CD_BAIRRO do IBGE (nulo quando o setor não pertence a nenhum bairro) por setor."""
    rows = sqlite3.connect(gpkg).execute('select CD_SETOR, SITUACAO, CD_BAIRRO from PR_setores_CD2022 where CD_MUN=?', (cd_mun,)).fetchall()
    return pd.DataFrame(rows, columns=['CD_SETOR', 'SITUACAO', 'CD_BAIRRO']).set_index('CD_SETOR')

def _centroide(ring):
    x, y = ring[:, 0], ring[:, 1]
    a = x[:-1] * y[1:] - x[1:] * y[:-1]
    area = a.sum() / 2
    if abs(area) < 1e-18:
        return ring[:-1].mean(axis=0)
    return np.array([((x[:-1] + x[1:]) * a).sum(), ((y[:-1] + y[1:]) * a).sum()]) / (6 * area)

def _setores_por_unidade(c, votos_sec, setores, setor_meta):
    """Setor que contém locais de votação -> unidade TSE de maior votação ali; setor urbano livre (sem bairro IBGE)
    -> unidade TSE do local de votação mais próximo do seu centróide. Setor rural livre fica sem unidade."""
    t = c[(c.TIPO == 'TSE') & c.setor.notna()].copy()
    t['v'] = t.set_index(KEY).index.map(votos_sec).fillna(0).to_numpy()
    direto = t.groupby(['setor', 'UNIDADE']).v.sum().reset_index().sort_values('v', ascending=False).drop_duplicates('setor')
    out = dict(zip(direto.setor, direto.UNIDADE))
    pts = t[['NR_LATITUDE', 'NR_LONGITUDE', 'UNIDADE']].copy()
    pts['lat'], pts['lon'] = parse_coord(pts.NR_LATITUDE), parse_coord(pts.NR_LONGITUDE)
    pts = pts.dropna(subset=['lat', 'lon']).drop_duplicates(['lat', 'lon'])
    if setor_meta is None or pts.empty:
        return out
    cent = {cd: _centroide(rings[0]) for cd, rings in setores}
    livres = setor_meta[setor_meta.CD_BAIRRO.isna() & (setor_meta.SITUACAO == 'Urbana')].index
    k = np.cos(np.radians(pts.lat.mean()))
    for cd in livres:
        if cd in out or cd not in cent:
            continue
        lon, lat = cent[cd]
        d = np.hypot((pts.lon.to_numpy() - lon) * k, pts.lat.to_numpy() - lat)
        out[cd] = pts.UNIDADE.to_numpy()[d.argmin()]
    return out

def construir_unidades(cad, votos, bairros, setores, ind_setor, ind_bairro, setor_meta=None):
    """Unidade = bairro IBGE (seção cujo local cai no polígono) ou, senão, bairro cadastrado no TSE ('TSE|<nome>').
    Indicador de unidade TSE = soma dos setores distintos onde ficam seus locais de votação (aproximação).
    cad: chave da seção + NR_LATITUDE, NR_LONGITUDE, NM_BAIRRO, NR_LOCAL_VOTACAO, NM_LOCAL_VOTACAO.
    Com setor_meta, a unidade TSE reúne também os setores urbanos sem bairro IBGE mais próximos de seus locais de votação (contorno aproximado).
    Retorna dict: votos (UNIDADE, TIPO, NR_VOTAVEL, QT_VOTOS), unidades, pontos, setor_unidade, sem_cadastro (votos). Falha se não reconciliar."""
    c = cad.reset_index(drop=True)
    coords = c[['NR_LATITUDE', 'NR_LONGITUDE']]
    c['bairro'] = atribuir_bairros(coords, bairros).CD_BAIRRO.to_numpy()
    c['setor'] = atribuir_bairros(coords, setores).CD_BAIRRO.to_numpy()
    c['TIPO'] = np.where(c.bairro.notna(), 'IBGE', 'TSE')
    c['UNIDADE'] = np.where(c.bairro.notna(), c.bairro, 'TSE|' + c.NM_BAIRRO.fillna('SEM BAIRRO').map(_norm))
    j = votos.merge(c[KEY + ['UNIDADE', 'TIPO']], on=KEY, how='left')
    falta = j.UNIDADE.isna()
    sem_cadastro = int(j.QT_VOTOS[falta].sum())
    v = j[~falta].groupby(['UNIDADE', 'TIPO', 'NR_VOTAVEL'], as_index=False).QT_VOTOS.sum()
    assert v.QT_VOTOS.sum() + sem_cadastro == votos.QT_VOTOS.sum(), 'votos não reconciliam'
    nomes = c.groupby('UNIDADE').NM_BAIRRO.agg(lambda s: s.mode().iloc[0] if s.notna().any() else 'SEM BAIRRO')
    votos_sec = votos.groupby(KEY).QT_VOTOS.sum()
    por_unidade = pd.Series(_setores_por_unidade(c, votos_sec, setores, setor_meta), dtype=object)
    setor_unidade = por_unidade.rename_axis('CD_SETOR').rename('UNIDADE').reset_index()
    linhas = []
    for u, g in c.groupby('UNIDADE'):
        if g.TIPO.iloc[0] == 'IBGE':
            ind = ind_bairro.loc[u].to_dict() if u in ind_bairro.index else {}
            n = None
        else:
            ss = por_unidade.index[por_unidade == u] if len(por_unidade) else []
            ind = agregar_setores(ind_setor.loc[ind_setor.index.intersection(ss)]) if len(ss) else {}
            n = len(ss)
        linhas.append({'UNIDADE': u, 'TIPO': g.TIPO.iloc[0], 'NOME': nomes[u], 'n_setores': n, **ind})
    pontos = votos.merge(c[KEY + ['UNIDADE', 'TIPO', 'NR_LOCAL_VOTACAO', 'NM_LOCAL_VOTACAO', 'NR_LATITUDE', 'NR_LONGITUDE']], on=KEY)
    pontos = pontos[pontos.TIPO == 'TSE'].drop(columns='TIPO')
    return {'votos': v, 'unidades': pd.DataFrame(linhas), 'pontos': pontos, 'setor_unidade': setor_unidade, 'sem_cadastro': sem_cadastro}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--uf', required=True)
    ap.add_argument('--municipio', required=True, help='código IBGE de 7 dígitos')
    a = ap.parse_args()
    if a.uf != 'PR':
        raise SystemExit('Somente PR: a malha de bairros baixada é a do Paraná.')
    cross = pd.read_parquet(OUT / 'correspondencia_tse_ibge.parquet')
    tse = cross.loc[cross.CD_MUN == a.municipio, 'CD_MUNICIPIO']
    if tse.empty:
        raise SystemExit(f'Município {a.municipio} não encontrado em correspondencia_tse_ibge')
    cd_tse = int(tse.iloc[0])
    cad = pd.read_parquet(OUT / 'cadastro_secoes.parquet')
    cad = cad[(cad.SG_UF == a.uf) & (cad.CD_MUNICIPIO == cd_tse)]
    votos = pd.read_parquet(OUT / 'votos_secoes_2026_t1.parquet', columns=KEY + ['NR_VOTAVEL', 'QT_VOTOS'])
    votos = votos[(votos.SG_UF == a.uf) & (votos.CD_MUNICIPIO == cd_tse)]
    malha = ler_malha(ROOT / 'data/raw/PR_bairros_CD2022.gpkg', a.municipio)
    secoes = atribuir_bairros(cad[KEY + ['NR_LATITUDE', 'NR_LONGITUDE']], malha)
    por, excl = votos_por_bairro(votos, secoes)
    por.to_parquet(OUT / f'votos_bairros_ibge_{a.municipio}.parquet', index=False)
    excl.to_csv(OUT / f'exclusoes_bairros_{a.municipio}.csv', index=False, sep=';')
    total = votos.QT_VOTOS.sum()
    print(f'{a.municipio}: {100 * por.QT_VOTOS.sum() / total:.2f}% dos votos atribuídos a {por.CD_BAIRRO.nunique()} bairros')
    print(excl.to_string(index=False))
    # Unidades: bairro IBGE ou, fora dos polígonos, bairro cadastrado no TSE (100% dos votos com cadastro)
    pesq = ROOT / 'data/raw/PR_setores_CD2022.gpkg'
    setores = ler_malha(pesq, a.municipio, tabela='PR_setores_CD2022', col='CD_SETOR')
    ind_setor = importlib.import_module('09_setores').ler_setores_ind(a.municipio)
    ib = pd.read_parquet(OUT / 'ibge_bairros.parquet').set_index('CD_BAIRRO')
    meta = ler_setores_meta(pesq, a.municipio)
    r = construir_unidades(cad[KEY + ['NR_LATITUDE', 'NR_LONGITUDE', 'NM_BAIRRO', 'NR_LOCAL_VOTACAO', 'NM_LOCAL_VOTACAO']], votos, malha, setores, ind_setor, ib, setor_meta=meta)
    r['setor_unidade'].to_parquet(OUT / f'setores_unidade_{a.municipio}.parquet', index=False)
    r['votos'].to_parquet(OUT / f'votos_unidades_{a.municipio}.parquet', index=False)
    r['unidades'].to_parquet(OUT / f'unidades_{a.municipio}.parquet', index=False)
    r['pontos'].to_parquet(OUT / f'pontos_{a.municipio}.parquet', index=False)
    t = r['votos'].groupby('TIPO').QT_VOTOS.sum()
    print(f'unidades: {t.get("IBGE", 0) / total * 100:.2f}% dos votos em bairros IBGE, {t.get("TSE", 0) / total * 100:.2f}% em bairros do TSE, {r["sem_cadastro"]} votos sem cadastro')

if __name__ == '__main__':
    main()
