# SEA Tramping Voyage Simulation

## Monte Carlo Optimisation Engine for South East Asian Bulk Cargo Tramping

### Overview
This application uses Monte Carlo simulation to discover optimal annual voyage programmes
for a bulk carrier operating in the South East Asian tramping market. It evaluates
70 ports × 70 ports × 21 commodity types (102,900 theoretical combinations) and
identifies the most profitable route networks, commodity strategies, and seasonal patterns.

### Architecture
- **70 Ports**: Top ports by cargo volume from Intra-SEA trade data (2020-2024)
- **21 Commodity Types**: Coal, Dry Bulk, Agri-Bulk, Break-Bulk, Steel, Fertilizers
- **3-Phase Simulation**: Exploration → Informed Search → Exploitation
- **Stochastic Variables**: Freight rates, bunker prices, port congestion

### Installation

```bash
pip install streamlit plotly pandas numpy openpyxl
```

### Running the Application

```bash
cd sea_tramping_sim
streamlit run app.py
```

The dashboard will open in your browser at http://localhost:8501

### How to Use

1. **Vessel Configuration** (sidebar): Set your vessel specs - DWT, speed, fuel consumption
2. **Cost Parameters** (sidebar): Set charter hire rate, bunker price
3. **Data Overview** tab: Review the 70-port network and 4,000+ feasible voyage legs
4. **Port Network** tab: Interactive map of all ports with distance matrix
5. **Run Simulation** tab: Configure iterations and run Monte Carlo simulation
6. **Results** tab: View profit distributions, port rankings, commodity analysis
7. **Top Programmes** tab: Detailed voyage schedules for the best annual plans

### Default Vessel Configuration
- DWT: 20,000 MT (Handy-size bulk carrier)
- Speed: 12.0 knots laden / 12.5 knots ballast
- Fuel: 25.0 MT/day laden / 20.0 MT/day ballast
- Charter Hire: $7,000/day
- Bunker Price: $600/MT VLSFO
- Operating Days: 350/year

### Simulation Parameters
- **Iterations**: 10,000 (default) - increase for more robust results
- **Freight Volatility**: ±15% stochastic variation on base rates
- **Bunker Volatility**: ±10% stochastic variation on fuel price
- **3-Phase Convergence**: 20% exploration, 50% informed, 30% exploitation

### Data Source
Port pair volume data from D1_Port_Pair_Matrix_Advantis.xlsx (2020-2024)
Freight rates: Market benchmark estimates for handy-size SEA trades
Port charges: Regional averages by country

### Project Structure
```
sea_tramping_sim/
├── app.py                          # Streamlit dashboard
├── modules/
│   ├── data_processor.py           # Data loading, port database, leg library
│   └── simulation_engine.py        # Monte Carlo engine, analysis
├── data/
│   ├── port_coordinates.py         # Port lat/lon database
│   └── D1_Port_Pair_Matrix_Advantis.xlsx  # Source data
└── README.md
```
