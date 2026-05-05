"""
Data Processing Module
Reads the port pair matrix, builds port database, creates the 70x70x21 leg library.
"""
import pandas as pd
import numpy as np
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.port_coordinates import PORT_COORDS
from data.port_charges import get_port_charges, STEVEDORING_RATES
from data.sea_distances_loader import (
    load_distance_matrix, get_sea_distance_nm, is_loaded,
    load_route_waypoints,
)

# Load pre-built sea distance matrix and route waypoints once at module import
_sea_matrix_loaded    = load_distance_matrix()
_sea_waypoints_loaded = load_route_waypoints()

# Filter stats written by build_leg_library() — read by sim_logger
_FILTER_STATS: dict = {}

COMMODITY_GROUPS = {
    'Steam Coal': 'Steam Coal', 'Coking Coal': 'Coking Coal', 'Anthracite': 'Anthracite',
    'Petroleum Coke': 'Petroleum Coke', 'Clinker': 'Clinker', 'Clinker/Gypsum': 'Clinker',
    'Limestone': 'Limestone', 'Gypsum': 'Gypsum', 'Nickel Ore': 'Nickel Ore', 'Slag': 'Slag',
    'Aggregates': 'Aggregates', 'Salt': 'Salt', 'Stones': 'Aggregates', 'Bauxite': 'Nickel Ore',
    'Soda Ash': 'Aggregates', 'Sulphur': 'Aggregates',
    'Rice': 'Rice', 'Rice/Tapioca': 'Rice', 'Sugar': 'Sugar',
    'Palm Kernel Expeller': 'Palm Kernel Expeller', 'Copra': 'Copra', 'Tapioca': 'Rice',
    'Cement': 'Cement', 'Cement Bagged': 'Cement Bagged', 'Cement/Clinker': 'Cement',
    'Cement Bagged/Rice': 'Cement Bagged', 'Project Cargo': 'Project Cargo',
    'General Cargo': 'Project Cargo', 'Building Materials': 'Project Cargo',
    'Logs': 'Timber', 'Logs/Timber': 'Timber', 'Timber': 'Timber', 'Wood Chips': 'Wood Chips',
    'Steels': 'Steels', 'Steel Billets': 'Steels', 'Steel Coils': 'Steels',
    'Steel Plates': 'Steels', 'Steel Pipes': 'Steels', 'Steel Slabs': 'Steels',
    'Wire Rod': 'Steels', 'Rebars': 'Steels', 'HRC': 'Steels',
    'Scrap': 'Scrap', 'Scrap/Steels': 'Scrap',
    'Urea': 'Fertilizers', 'Bulk Fertilizers': 'Fertilizers', 'Fertilizers': 'Fertilizers',
    'Fertilizers Bagged': 'Fertilizers', 'Di-Amonium Phosphate': 'Fertilizers',
    'Phosphate Rock': 'Fertilizers', 'Muriate Of Potash': 'Fertilizers', 'Potash': 'Fertilizers',
    'Triple Superphosphate': 'Fertilizers', 'NPK': 'Fertilizers',
    'Nitrates Bagged': 'Fertilizers', 'Ammonium Nitrate': 'Fertilizers',
    'Ammonium Sulphate': 'Fertilizers',
}

COMMODITY_23 = [
    'Steam Coal', 'Coking Coal', 'Anthracite', 'Petroleum Coke',
    'Clinker', 'Limestone', 'Gypsum', 'Nickel Ore', 'Slag', 'Aggregates', 'Salt',
    'Rice', 'Sugar', 'Palm Kernel Expeller', 'Copra',
    'Cement', 'Cement Bagged', 'Project Cargo', 'Timber', 'Wood Chips',
    'Steels', 'Scrap', 'Fertilizers'
]

COMMODITY_CATEGORIES = {
    'Steam Coal': 'Coal', 'Coking Coal': 'Coal', 'Anthracite': 'Coal', 'Petroleum Coke': 'Coal',
    'Clinker': 'Dry Bulk', 'Limestone': 'Dry Bulk', 'Gypsum': 'Dry Bulk',
    'Nickel Ore': 'Dry Bulk', 'Slag': 'Dry Bulk', 'Aggregates': 'Dry Bulk', 'Salt': 'Dry Bulk',
    'Rice': 'Agri-Bulk', 'Sugar': 'Agri-Bulk', 'Palm Kernel Expeller': 'Agri-Bulk', 'Copra': 'Agri-Bulk',
    'Cement': 'Break-Bulk', 'Cement Bagged': 'Break-Bulk', 'Project Cargo': 'Break-Bulk',
    'Timber': 'Break-Bulk', 'Wood Chips': 'Dry Bulk',
    'Steels': 'Steel/Metal', 'Scrap': 'Steel/Metal', 'Fertilizers': 'Fertilizers',
}

FREIGHT_RATE_PARAMS = {
    'Steam Coal':           {'base': 5.0, 'per_nm': 0.0050, 'min_rate': 7.0, 'max_rate': 18.0},
    'Coking Coal':          {'base': 6.0, 'per_nm': 0.0055, 'min_rate': 8.0, 'max_rate': 20.0},
    'Anthracite':           {'base': 6.0, 'per_nm': 0.0052, 'min_rate': 8.0, 'max_rate': 19.0},
    'Petroleum Coke':       {'base': 6.5, 'per_nm': 0.0055, 'min_rate': 8.5, 'max_rate': 20.0},
    'Clinker':              {'base': 6.0, 'per_nm': 0.0055, 'min_rate': 8.0, 'max_rate': 20.0},
    'Limestone':            {'base': 5.0, 'per_nm': 0.0045, 'min_rate': 6.5, 'max_rate': 16.0},
    'Gypsum':               {'base': 5.5, 'per_nm': 0.0048, 'min_rate': 7.0, 'max_rate': 17.0},
    'Nickel Ore':           {'base': 6.5, 'per_nm': 0.0058, 'min_rate': 8.5, 'max_rate': 21.0},
    'Slag':                 {'base': 5.0, 'per_nm': 0.0045, 'min_rate': 6.5, 'max_rate': 16.0},
    'Aggregates':           {'base': 5.0, 'per_nm': 0.0042, 'min_rate': 6.0, 'max_rate': 15.0},
    'Salt':                 {'base': 5.5, 'per_nm': 0.0048, 'min_rate': 7.0, 'max_rate': 16.0},
    'Rice':                 {'base': 7.5, 'per_nm': 0.0060, 'min_rate': 9.5, 'max_rate': 24.0},
    'Sugar':                {'base': 7.5, 'per_nm': 0.0060, 'min_rate': 9.5, 'max_rate': 24.0},
    'Palm Kernel Expeller': {'base': 8.0, 'per_nm': 0.0065, 'min_rate': 10.0, 'max_rate': 26.0},
    'Copra':                {'base': 8.0, 'per_nm': 0.0068, 'min_rate': 10.0, 'max_rate': 27.0},
    'Cement':               {'base': 6.5, 'per_nm': 0.0058, 'min_rate': 8.5, 'max_rate': 22.0},
    'Cement Bagged':        {'base': 7.5, 'per_nm': 0.0065, 'min_rate': 10.0, 'max_rate': 25.0},
    'Project Cargo':        {'base': 12.0, 'per_nm': 0.0085, 'min_rate': 15.0, 'max_rate': 40.0},
    'Timber':               {'base': 7.5, 'per_nm': 0.0060, 'min_rate': 9.5, 'max_rate': 24.0},
    'Wood Chips':           {'base': 6.0, 'per_nm': 0.0052, 'min_rate': 7.5, 'max_rate': 19.0},
    'Steels':               {'base': 9.0, 'per_nm': 0.0075, 'min_rate': 12.0, 'max_rate': 30.0},
    'Scrap':                {'base': 7.5, 'per_nm': 0.0060, 'min_rate': 9.5, 'max_rate': 24.0},
    'Fertilizers':          {'base': 7.5, 'per_nm': 0.0060, 'min_rate': 9.5, 'max_rate': 24.0},
}

PORT_CHARGES_BY_COUNTRY = {
    'Indonesia': {'mean': 15000, 'std': 4000},
    'Philippines': {'mean': 20000, 'std': 5000},
    'Malaysia': {'mean': 22000, 'std': 5000},
    'Thailand': {'mean': 18000, 'std': 4000},
    'Vietnam': {'mean': 18000, 'std': 4000},
    'Bangladesh': {'mean': 25000, 'std': 7000},
    'Cambodia': {'mean': 14000, 'std': 3000},
    'Myanmar': {'mean': 15000, 'std': 4000},
    'Sri Lanka': {'mean': 22000, 'std': 5000},
    'Singapore': {'mean': 25000, 'std': 6000},
}

# V2: Split port costs into navigation + stevedoring (FIO cargo = zero stevedoring)
# Load port navigation based on real voyage data ($7,530 Tanjung Tapa → $14,971 other)
# Discharge port navigation from real data ($28,765 – $30,496)
PORT_COSTS_V2 = {
    # country: (load_nav, load_steve, disch_nav, disch_steve)
    'Indonesia':   {'load_nav': 7530,  'load_steve': 0, 'disch_nav': 14000, 'disch_steve': 0},
    'Philippines': {'load_nav': 10000, 'load_steve': 0, 'disch_nav': 22000, 'disch_steve': 0},
    'Malaysia':    {'load_nav': 9500,  'load_steve': 0, 'disch_nav': 20000, 'disch_steve': 0},
    'Thailand':    {'load_nav': 9500,  'load_steve': 0, 'disch_nav': 19000, 'disch_steve': 0},
    'Vietnam':     {'load_nav': 9000,  'load_steve': 0, 'disch_nav': 18500, 'disch_steve': 0},
    'Bangladesh':  {'load_nav': 12000, 'load_steve': 0, 'disch_nav': 28765, 'disch_steve': 0},
    'Cambodia':    {'load_nav': 8000,  'load_steve': 0, 'disch_nav': 16000, 'disch_steve': 0},
    'Myanmar':     {'load_nav': 8500,  'load_steve': 0, 'disch_nav': 17000, 'disch_steve': 0},
    'Sri Lanka':   {'load_nav': 10000, 'load_steve': 0, 'disch_nav': 22000, 'disch_steve': 0},
    'Singapore':   {'load_nav': 14971, 'load_steve': 0, 'disch_nav': 30496, 'disch_steve': 0},
    'default':     {'load_nav': 10000, 'load_steve': 0, 'disch_nav': 20000, 'disch_steve': 0},
}

HANDLING_COST = {
    'Coal': {'load': 1.0, 'disch': 1.5},
    'Dry Bulk': {'load': 1.5, 'disch': 2.0},
    'Agri-Bulk': {'load': 2.0, 'disch': 2.5},
    'Break-Bulk': {'load': 3.0, 'disch': 3.5},
    'Steel/Metal': {'load': 3.5, 'disch': 4.0},
    'Fertilizers': {'load': 2.0, 'disch': 2.5},
}

PORT_CONGESTION = {
    'Chittagong': {'mean': 5.0, 'std': 2.5},
    'Payra': {'mean': 3.0, 'std': 1.5},
    'Mongla': {'mean': 4.0, 'std': 2.0},
    'Manila': {'mean': 2.0, 'std': 1.0},
    'Surabaya': {'mean': 1.5, 'std': 0.8},
}
DEFAULT_CONGESTION = {'mean': 1.0, 'std': 0.5}

CARGO_RATE = {
    'Coal': {'load': 8000, 'disch': 6000},
    'Dry Bulk': {'load': 5000, 'disch': 4000},
    'Agri-Bulk': {'load': 4000, 'disch': 3500},
    'Break-Bulk': {'load': 5000, 'disch': 4000},  # same as Dry Bulk — 20K DWT tramping
    'Steel/Metal': {'load': 2500, 'disch': 2000},
    'Fertilizers': {'load': 4000, 'disch': 3500},
}

# Flat port stay days per commodity (load port + discharge port combined)
# Based on real operator experience — used instead of cargo-rate calculation
DEFAULT_PORT_STAY_DAYS = {
    'Steam Coal':           3.0,
    'Coking Coal':          3.0,
    'Anthracite':           3.0,
    'Petroleum Coke':       3.0,
    'Nickel Ore':           3.5,
    'Iron Ore':             3.0,
    'Bauxite':              3.0,
    'Clinker':              3.5,
    'Limestone':            3.5,
    'Gypsum':               3.5,
    'Slag':                 3.5,
    'Aggregates':           3.5,
    'Salt':                 3.5,
    'Palm Kernel Expeller': 4.0,
    'Sugar':                4.0,
    'Rice':                 4.0,
    'Copra':                4.0,
    'Grain':                3.5,
    'Wood Chips':           3.5,
    'Timber':               4.0,
    'Steels':               5.0,
    'Scrap':                4.5,
    'Fertilizers':          4.0,
    'Cement':               3.5,
    'Cement Bagged':        4.0,
    'Project Cargo':        5.0,
    'Dry Bulk':             3.5,
}
_PORT_STAY_FALLBACK = 3.5


def haversine_nm(lat1, lon1, lat2, lon2):
    R = 3440.065
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def sea_distance(port1_coords, port2_coords, port1_country, port2_country,
                 port1_name="", port2_name=""):
    """
    Return sea distance in NM between two ports.
    Uses pre-built searoute matrix when available; falls back to Haversine × factor.
    """
    # Try real sea distance matrix first
    if is_loaded() and port1_name and port2_name:
        nm = get_sea_distance_nm(
            port1_name, port2_name,
            port_coords=PORT_COORDS,
            country_a=port1_country,
            country_b=port2_country,
        )
        if nm > 0:
            return nm

    # Haversine × correction factor fallback
    straight_nm = haversine_nm(*port1_coords, *port2_coords)
    lat1, lon1 = port1_coords
    lat2, lon2 = port2_coords
    if port1_country == 'Indonesia' and port2_country == 'Indonesia':
        factor = 1.45
    elif ('Indonesia' in [port1_country, port2_country] and
          'Philippines' in [port1_country, port2_country]):
        factor = 1.35
    elif ((lon1 < 105 or lon2 < 105) and (lon1 > 115 or lon2 > 115)):
        factor = 1.50
    elif 'Bangladesh' in [port1_country, port2_country]:
        factor = 1.40
    elif 'Sri Lanka' in [port1_country, port2_country]:
        factor = 1.35
    elif port1_country == 'Philippines' and port2_country == 'Philippines':
        factor = 1.30
    else:
        factor = 1.25
    return straight_nm * factor


def load_and_process_data(excel_path):
    df = pd.read_excel(excel_path, sheet_name='Summary – All Years', header=None)
    data = df.iloc[3:].copy()
    data.columns = ['#', 'Load Country', 'Load Port', 'Disch Country', 'Disch Port',
                     'Commodity', 'Category', '2020', '2021', '2022', '2023', '2024',
                     'Total', 'Voyages', 'Corridor']
    data = data[pd.to_numeric(data['#'], errors='coerce').notna()].copy()
    for col in ['2020', '2021', '2022', '2023', '2024', 'Total']:
        data[col] = pd.to_numeric(data[col], errors='coerce').fillna(0)
    data['Voyages'] = pd.to_numeric(data['Voyages'], errors='coerce').fillna(0)
    intra = data[data['Corridor'] == 'Intra-SEA'].copy()
    intra['Commodity_Group'] = intra['Commodity'].map(COMMODITY_GROUPS).fillna('Other')
    intra = intra[intra['Commodity_Group'] != 'Other']
    return intra


def build_port_database(intra_data, n_ports=70):
    load_vol = intra_data.groupby(['Load Country', 'Load Port'])['Total'].sum().reset_index()
    load_vol.columns = ['Country', 'Port', 'Load_Vol']
    disch_vol = intra_data.groupby(['Disch Country', 'Disch Port'])['Total'].sum().reset_index()
    disch_vol.columns = ['Country', 'Port', 'Disch_Vol']
    ports = load_vol.merge(disch_vol, on=['Country', 'Port'], how='outer').fillna(0)
    ports['Total_Vol'] = ports['Load_Vol'] + ports['Disch_Vol']
    ports = ports.sort_values('Total_Vol', ascending=False).head(n_ports).reset_index(drop=True)
    ports['Port_ID'] = range(n_ports)

    coords_lat, coords_lon = [], []
    for _, row in ports.iterrows():
        port_name = row['Port']
        if port_name in PORT_COORDS:
            lat, lon = PORT_COORDS[port_name]
        else:
            found = False
            for key in PORT_COORDS:
                if key.lower() in port_name.lower() or port_name.lower() in key.lower():
                    lat, lon = PORT_COORDS[key]
                    found = True
                    break
            if not found:
                centroids = {
                    'Indonesia': (-2.5, 118.0), 'Philippines': (12.0, 122.0),
                    'Vietnam': (16.0, 108.0), 'Thailand': (13.0, 101.0),
                    'Malaysia': (4.0, 109.0), 'Bangladesh': (23.0, 90.0),
                    'Cambodia': (11.5, 105.0), 'Myanmar': (19.0, 96.0),
                    'Sri Lanka': (7.5, 80.5), 'Singapore': (1.3, 103.8),
                }
                lat, lon = centroids.get(row['Country'], (5.0, 115.0))
        coords_lat.append(lat)
        coords_lon.append(lon)

    ports['Lat'] = coords_lat
    ports['Lon'] = coords_lon

    port_exports, port_imports = {}, {}
    for _, row in ports.iterrows():
        pname = row['Port']
        exp = intra_data[intra_data['Load Port'] == pname].groupby('Commodity_Group')['Total'].sum()
        port_exports[pname] = exp.to_dict()
        imp = intra_data[intra_data['Disch Port'] == pname].groupby('Commodity_Group')['Total'].sum()
        port_imports[pname] = imp.to_dict()

    ports['Exports'] = ports['Port'].map(port_exports)
    ports['Imports'] = ports['Port'].map(port_imports)
    return ports


def build_distance_matrix(ports_df):
    n = len(ports_df)
    dist_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(i+1, n):
            d = sea_distance(
                (ports_df.iloc[i]['Lat'], ports_df.iloc[i]['Lon']),
                (ports_df.iloc[j]['Lat'], ports_df.iloc[j]['Lon']),
                ports_df.iloc[i]['Country'], ports_df.iloc[j]['Country'],
                port1_name=ports_df.iloc[i]['Port'],
                port2_name=ports_df.iloc[j]['Port'],
            )
            dist_matrix[i][j] = d
            dist_matrix[j][i] = d
    return dist_matrix


def compute_freight_rate(commodity, distance_nm, rng=None, volatility=0.15):
    params = FREIGHT_RATE_PARAMS.get(commodity, FREIGHT_RATE_PARAMS['Steam Coal'])
    base_rate = params['base'] + params['per_nm'] * distance_nm
    base_rate = np.clip(base_rate, params['min_rate'], params['max_rate'])
    if rng is not None:
        base_rate *= (1 + rng.normal(0, volatility))
        base_rate = max(base_rate, params['min_rate'] * 0.7)
    return base_rate


def build_leg_library(ports_df, dist_matrix, intra_data):
    n_ports = len(ports_df)
    port_names = ports_df['Port'].tolist()
    port_countries = ports_df['Country'].tolist()

    observed = set()
    observed_volumes = {}
    for _, row in intra_data.iterrows():
        if row['Load Port'] in port_names and row['Disch Port'] in port_names:
            key = (row['Load Port'], row['Disch Port'], row['Commodity_Group'])
            observed.add(key)
            observed_volumes[key] = observed_volumes.get(key, 0) + row['Total']

    legs = []
    for i in range(n_ports):
        for j in range(n_ports):
            if i == j:
                continue
            origin = port_names[i]
            dest = port_names[j]
            dist = dist_matrix[i][j]
            if dist < 50:
                continue

            for commodity in COMMODITY_23:
                if commodity not in COMMODITY_CATEGORIES:
                    continue
                key = (origin, dest, commodity)
                cat = COMMODITY_CATEGORIES[commodity]

                exports = ports_df.iloc[i].get('Exports', {})
                imports = ports_df.iloc[j].get('Imports', {})
                if not isinstance(exports, dict): exports = {}
                if not isinstance(imports, dict): imports = {}

                origin_exports = exports.get(commodity, 0) > 0
                dest_imports = imports.get(commodity, 0) > 0

                if key in observed:
                    status = 'observed'
                    annual_vol = observed_volumes[key] / 5.0
                elif origin_exports and dest_imports:
                    status = 'plausible'
                    exp_vol = exports.get(commodity, 0) / 5.0
                    imp_vol = imports.get(commodity, 0) / 5.0
                    annual_vol = min(exp_vol, imp_vol) * 0.1
                else:
                    continue

                freight_rate = compute_freight_rate(commodity, dist)
                handling = HANDLING_COST.get(cat, HANDLING_COST['Dry Bulk'])
                cargo_rate = CARGO_RATE.get(cat, CARGO_RATE['Dry Bulk'])

                # Per-port charges and congestion from port_charges.py (per-port granularity)
                load_charges  = get_port_charges(origin, port_countries[i])
                disch_charges = get_port_charges(dest,   port_countries[j])
                load_pc  = load_charges['nav']
                disch_pc = disch_charges['nav']
                load_cong  = load_charges['cong_mean']
                disch_cong = disch_charges['cong_mean']
                load_cong_std  = load_charges['cong_std']
                disch_cong_std = disch_charges['cong_std']

                # Stevedoring (FIO default = 0)
                steve_load = STEVEDORING_RATES.get(cat, (0.0, 0.0))[0]
                steve_disch = STEVEDORING_RATES.get(cat, (0.0, 0.0))[1]

                # Keep legacy split columns
                load_costs_v2 = {'load_nav': load_pc, 'load_steve': 0}
                disch_costs_v2 = {'disch_nav': disch_pc, 'disch_steve': 0}

                _port_stay = DEFAULT_PORT_STAY_DAYS.get(
                    commodity,
                    DEFAULT_PORT_STAY_DAYS.get(cat, _PORT_STAY_FALLBACK),
                )
                legs.append({
                    'origin_id': i, 'dest_id': j,
                    'origin_port': origin, 'dest_port': dest,
                    'origin_country': port_countries[i], 'dest_country': port_countries[j],
                    'commodity': commodity, 'category': cat,
                    'direction': 'Intra-SEA',  # overwritten after filter below
                    'distance_nm': dist, 'status': status,
                    'annual_volume_mt': annual_vol,
                    'freight_rate_usd_mt': freight_rate,
                    'load_handling_usd_mt': handling['load'],
                    'disch_handling_usd_mt': handling['disch'],
                    'load_port_charges': load_pc, 'disch_port_charges': disch_pc,
                    # V2 split columns
                    'load_port_nav':   load_costs_v2['load_nav'],
                    'load_port_steve': load_costs_v2['load_steve'],
                    'disch_port_nav':  disch_costs_v2['disch_nav'],
                    'disch_port_steve': disch_costs_v2['disch_steve'],
                    'load_congestion_days': load_cong,  'disch_congestion_days': disch_cong,
                    'load_congestion_std':  load_cong_std, 'disch_congestion_std': disch_cong_std,
                    'load_steve_per_mt':   steve_load,  'disch_steve_per_mt':  steve_disch,
                    'load_rate_mt_day': cargo_rate['load'], 'disch_rate_mt_day': cargo_rate['disch'],
                    'port_stay_days': _port_stay,
                })

    legs_df = pd.DataFrame(legs)
    if legs_df.empty:
        return legs_df

    _n_raw = len(legs_df)

    # Fix 1a — SEA load ports + Far East discharge ports.
    # LOAD ports: SEA only (vessel loads cargo in SEA region).
    # DISCHARGE ports: SEA + Far East (China, Japan, Korea, Taiwan, HK).
    # This reflects real Handysize tramping: load coal/nickel/ore in SEA,
    # discharge in Far East, ballast back for next cargo.
    _SEA_LOAD_COUNTRIES = {
        'Indonesia', 'Philippines', 'Vietnam', 'Malaysia', 'Thailand',
        'Singapore', 'Bangladesh', 'Myanmar', 'Cambodia', 'Timor-Leste',
        'Brunei', 'Sri Lanka',
    }
    _FAR_EAST_COUNTRIES = {
        'China', 'Japan', 'Korea South', 'Hong Kong',
        'Taiwan, Province of China',
    }
    _ALL_DISCHARGE_COUNTRIES = _SEA_LOAD_COUNTRIES | _FAR_EAST_COUNTRIES
    legs_df = legs_df[
        legs_df['origin_country'].isin(_SEA_LOAD_COUNTRIES) &
        legs_df['dest_country'].isin(_ALL_DISCHARGE_COUNTRIES)
    ]
    _n_intra = len(legs_df)

    # Tag direction: Export from SEA if discharging in Far East, else Intra-SEA
    legs_df['direction'] = legs_df['dest_country'].apply(
        lambda c: 'Export from SEA' if c in _FAR_EAST_COUNTRIES else 'Intra-SEA'
    )

    # Fix 1b — remove Break-Bulk and Project Cargo (slow cargo, distorts port stay)
    legs_df = legs_df[~legs_df['category'].isin(['Break-Bulk'])]
    _n_no_bb = len(legs_df)

    # Fix 1c — remove legs involving NOT_SUITABLE ports
    try:
        from data.port_restrictions import NOT_SUITABLE_PORTS
        legs_df = legs_df[
            ~legs_df['origin_port'].isin(NOT_SUITABLE_PORTS) &
            ~legs_df['dest_port'].isin(NOT_SUITABLE_PORTS)
        ]
    except ImportError:
        pass
    _n_no_blocked = len(legs_df)

    # Fix 1d — Cambodia excluded as LOAD port only (shallow river ports, no 20K DWT access)
    legs_df = legs_df[~legs_df['origin_country'].isin({'Cambodia'})]

    # Fix 2 — commodity restrictions for restricted ports.
    # Only certain commodities make operational sense at each port.
    _PORT_COMMODITY_ALLOW = {
        'Samarinda':             {'Steam Coal', 'Coking Coal', 'Petroleum Coke'},
        'Bangkok (Khlong Toei)': {'Steam Coal', 'Clinker', 'Cement'},
        'Mongla':                {'Steam Coal', 'Clinker'},
        'Yangon':                {'Steam Coal', 'Rice', 'Fertilizers'},
    }
    for _port, _allowed in _PORT_COMMODITY_ALLOW.items():
        # Restrict legs where this port appears as origin (loading)
        _origin_mask = legs_df['origin_port'] == _port
        if _origin_mask.any():
            legs_df = legs_df[
                ~_origin_mask | legs_df['commodity'].isin(_allowed)
            ]
        # Restrict legs where this port appears as destination (discharge)
        _dest_mask = legs_df['dest_port'] == _port
        if _dest_mask.any():
            legs_df = legs_df[
                ~_dest_mask | legs_df['commodity'].isin(_allowed)
            ]

    _n_final = len(legs_df)

    # Record filter stats for sim_logger (mutate in place so imported references stay valid)
    _cat_counts = legs_df['category'].value_counts().to_dict() if _n_final > 0 else {}
    _FILTER_STATS.update({
        'n_raw':        _n_raw,
        'n_intra_sea':  _n_intra,
        'n_no_bb':      _n_no_bb,
        'n_no_blocked': _n_no_blocked,
        'n_final':      _n_final,
        'categories':   _cat_counts,
        'n_ports':      len(port_names),
        'active_ports': sorted(set(legs_df['origin_port'].tolist() + legs_df['dest_port'].tolist())) if _n_final > 0 else [],
    })

    return legs_df.reset_index(drop=True)
