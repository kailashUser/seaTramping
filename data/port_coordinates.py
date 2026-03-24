"""
SEA Port Coordinates Database
Coordinates sourced from maritime port databases and admiralty records.
Format: {port_name: (latitude, longitude)}
"""

PORT_COORDS = {
    # INDONESIA - Kalimantan (major coal loading)
    "Balikpapan": (-1.2675, 116.8289),
    "Taboneo - Banjarmasin": (-3.5100, 114.6500),
    "Muara Berau": (2.0833, 117.4833),
    "Samarinda": (-0.4948, 117.1531),
    "Muara Pantai": (-2.0333, 116.0500),
    "Muara Banyuasin": (-2.3500, 104.8000),
    "Tanjung Bara CT": (1.5000, 117.7000),
    "Adang Bay": (-2.3667, 116.0000),
    "Bontang": (0.1333, 117.5000),
    "Tarakan Island": (3.3000, 117.6333),
    "Senipah Terminal": (-1.1167, 116.7833),
    "Muara Satui": (-3.1500, 115.7000),
    "Bunati": (-3.4167, 115.9667),
    "Sangkulirang": (1.0833, 117.1667),
    "Asam Asam": (-3.6000, 115.4500),
    "Bunyu": (3.4500, 117.8500),
    "Laut Island": (-3.8500, 116.0500),
    "Muara Jawa": (-0.7500, 117.1167),
    "Bengalon": (0.9000, 117.5833),
    "Kotabaru": (-3.2833, 116.2167),
    
    # INDONESIA - Java
    "Pelabuhan Ratu": (-6.9833, 106.5500),
    "Surabaya": (-7.2000, 112.7333),
    "Gresik": (-7.1500, 112.6500),
    "Semarang": (-6.9500, 110.4167),
    "Cigading": (-6.0167, 106.0333),
    "Merak": (-5.9333, 105.9833),
    "Cirebon": (-6.7167, 108.5500),
    
    # INDONESIA - Sumatra
    "Tarahan": (-5.5500, 105.3167),
    "Teluk Bayur": (-1.0000, 100.3667),
    "Belawan": (3.7833, 98.6833),
    "Dumai": (1.6833, 101.4500),
    "Palembang": (-2.9833, 104.7500),
    "Kualatanjung": (3.3833, 99.4167),
    
    # INDONESIA - Sulawesi
    "Bahudopi": (-1.5667, 121.8500),
    "Makassar": (-5.1333, 119.4167),
    "Bitung": (1.4500, 125.1833),
    "Pomalaa": (-4.1833, 121.6167),
    "Kendari": (-3.9667, 122.5833),
    
    # INDONESIA - Other
    "Kupang": (-10.1500, 123.5833),
    "Sorong": (-0.8667, 131.2500),
    
    # PHILIPPINES
    "Mariveles": (14.4333, 120.4833),
    "Limay": (14.5167, 120.5833),
    "Pagbilao": (13.9667, 121.7333),
    "Quezon": (14.0333, 122.1000),
    "Masinloc": (15.5333, 119.9500),
    "Davao": (7.0667, 125.6333),
    "Sual (Lingayen bay)": (16.0833, 120.0833),
    "Toledo (Philippines)": (10.3833, 123.6333),
    "Iloilo City": (10.7000, 122.5667),
    "Manila": (14.5833, 120.9667),
    "Villanueva (Mindanao Island)": (8.5833, 124.7667),
    "Naga (Cebu)": (10.2167, 123.7667),
    "Kauswagan": (8.1833, 124.0833),
    "Malita": (6.4000, 125.6167),
    "Isabel": (10.9333, 124.4167),
    "Batangas": (13.7500, 121.0500),
    "Nasipit": (8.9833, 125.5333),
    "Cebu": (10.3000, 123.9000),
    "Iligan": (8.2333, 124.2500),
    "Cagayan de Oro": (8.4833, 124.6500),
    "General Santos": (6.1167, 125.1667),
    "Zamboanga": (6.9000, 122.0667),
    "Ozamiz": (8.1500, 123.8500),
    "Sangi": (9.7000, 125.4500),
    "Tagoloan": (8.5333, 124.7500),
    
    # MALAYSIA
    "Lumut (Malaysia)": (4.2333, 100.6167),
    "Port Dickson": (2.5167, 101.7833),
    "Tanjung Pelepas": (1.3667, 103.5500),
    "Kuantan": (3.9667, 103.4333),
    "Port Kelang": (3.0000, 101.3833),
    "Penang": (5.4167, 100.3500),
    "Labuan": (5.2833, 115.2333),
    "Sandakan": (5.8333, 118.1000),
    "Tawau": (4.2500, 117.8833),
    "Bintulu": (3.1667, 113.0333),
    "Westport (Malaysia)": (2.9667, 101.3500),
    "Pasir Gudang": (1.4667, 103.9000),
    "Lahad Datu": (5.0333, 118.3333),
    "Kemaman": (4.2333, 103.4167),
    
    # THAILAND
    "Koh Sichang": (13.1500, 100.8167),
    "Map Ta Phut": (12.7167, 101.1667),
    "Laem Chabang": (13.0833, 100.8833),
    "Ko Por Anchorage": (13.1333, 100.7833),
    "Songkhla": (7.2000, 100.5833),
    "Bangkok": (13.7000, 100.5833),
    "Sattahip": (12.6667, 100.9000),
    "Sarasin": (8.2167, 98.3167),
    "Prachuap": (11.8000, 99.8000),
    
    # VIETNAM
    "Campha": (21.0000, 107.3333),
    "Ha Long": (20.9500, 107.0833),
    "Go Gia": (20.7167, 106.8167),
    "Binh Thuan (Vinh Tan)": (11.3333, 108.5833),
    "Cai Mep": (10.5000, 107.0167),
    "Nghi Son": (19.3667, 105.8333),
    "Son Duong": (20.8500, 106.9000),
    "Phu My": (10.5833, 107.0000),
    "Hai Phong": (20.8500, 106.6833),
    "Ho Chi Minh City": (10.7667, 106.7000),
    "Dung Quat": (15.3833, 108.7833),
    "Quy Nhon": (13.7667, 109.2500),
    "Vung Ang": (18.0833, 106.4000),
    "Da Nang": (16.0667, 108.2167),
    "Hon La": (17.9500, 106.5167),
    
    # BANGLADESH
    "Chittagong": (22.3333, 91.8333),
    "Payra": (21.8000, 90.3167),
    "Mongla": (22.4667, 89.6000),
    
    # CAMBODIA
    "Sihanoukville": (10.6333, 103.5000),
    
    # MYANMAR
    "Thilawa": (16.6667, 96.2500),
    "Yangon": (16.7667, 96.1667),
    
    # SRI LANKA
    "Colombo": (6.9500, 79.8500),
    "Trincomalee": (8.5667, 81.2333),
    "Hambantota": (6.1167, 81.1167),
    
    # SINGAPORE
    "Singapore": (1.2667, 103.8000),
}
