import requests
import pandas as pd
import os
import pulp

# 1. Hämta data från FPL API
BASE_URL = "https://fantasy.premierleague.com/api/"
bootstrap = requests.get(f"{BASE_URL}bootstrap-static/").json()
fixtures = requests.get(f"{BASE_URL}fixtures/").json()

players = bootstrap['elements']
teams = {t['id']: t['name'] for t in bootstrap['teams']}
element_types = {e['id']: e['singular_name_short'] for e in bootstrap['element_types']}

current_gw = 1
for event in bootstrap['events']:
    if event['is_current']:
        current_gw = event['id']
        break
    elif event['is_next']:
        current_gw = event['id'] - 1
        break

target_gw = 15

# 2. Beräkna FDR
team_fdr = {t_id: [] for t_id in teams.keys()}
for f in fixtures:
    gw = f.get('event')
    if gw and current_gw < gw <= target_gw:
        team_fdr[f['team_h']].append(f['team_h_difficulty'])
        team_fdr[f['team_a']].append(f['team_a_difficulty'])

# 3. Beräkna poängprognos med SÄKRARE FILTRERING
player_projections = []
for p in players:
    # FILTER 1: Måste vara helt frisk och ordinarie (inte skadad/avstängd)
    if p['status'] != 'a':
        continue
    
    # FILTER 2: Måste ha 100% chans att spela nästa omgång (om status finns)
    if p['chance_of_playing_next_round'] is not None and p['chance_of_playing_next_round'] < 100:
        continue
        
    # FILTER 3: Måste ha spelat minst 300 minuter för att säkerställa att de är rotade i laget
    if p['minutes'] < 300:
        continue

    form = float(p['form'])
    ppm = float(p['points_per_game'])
    ict = float(p['ict_index'])
    cost = p['now_cost'] / 10.0
    team_id = p['team']
    pos_type = p['element_type']

    upcoming_fdr = team_fdr.get(team_id, [3])
    avg_fdr = sum(upcoming_fdr) / len(upcoming_fdr) if upcoming_fdr else 3.0
    fdr_factor = 1 + ((3.0 - avg_fdr) * 0.1)

    base_xp_per_gw = ((form * 0.35) + (ppm * 0.45) + (ict / 20.0 * 0.20)) * fdr_factor
    num_games = len(upcoming_fdr) if upcoming_fdr else (target_gw - current_gw)
    projected_total_xp = round(base_xp_per_gw * num_games, 1)

    player_projections.append({
        'id': p['id'],
        'Spelare': p['web_name'],
        'Lag': teams[team_id],
        'team_id': team_id,
        'Pos': element_types[pos_type],
        'pos_type': pos_type,
        'Pris': cost,
        'Form': form,
        'Snitt FDR': round(avg_fdr, 2),
        'xP/Match': round(base_xp_per_gw, 2),
        'Totalt xP (GW15)': projected_total_xp
    })

df = pd.DataFrame(player_projections)

# 4. Optimera truppen (PuLP)
prob = pulp.LpProblem("FPL_Optimization", pulp.LpMaximize)

player_vars = {p['id']: pulp.LpVariable(f"p_{p['id']}", cat='Binary') for p in player_projections}

# Maximera xP
prob += pulp.lpSum([p['Totalt xP (GW15)'] * player_vars[p['id']] for p in player_projections])

# Restriktioner
prob += pulp.lpSum([player_vars[p['id']] for p in player_projections]) == 15
prob += pulp.lpSum([p['Pris'] * player_vars[p['id']] for p in player_projections]) <= 100.0

# Kvantiteter per position
prob += pulp.lpSum([player_vars[p['id']] for p in player_projections if p['pos_type'] == 1]) == 2
prob += pulp.lpSum([player_vars[p['id']] for p in player_projections if p['pos_type'] == 2]) == 5
prob += pulp.lpSum([player_vars[p['id']] for p in player_projections if p['pos_type'] == 3]) == 5
prob += pulp.lpSum([player_vars[p['id']] for p in player_projections if p['pos_type'] == 4]) == 3

# Max 3 spelare per klubb
for t_id in teams.keys():
    prob += pulp.lpSum([player_vars[p['id']] for p in player_projections if p['team_id'] == t_id]) <= 3

# Lös problemet
prob.solve(pulp.PULP_CBC_CMD(msg=False))

# Plocka ut truppen
squad_ids = [p_id for p_id, var in player_vars.items() if var.varValue == 1]
squad_df = df[df['id'].isin(squad_ids)].copy().sort_values(by='Totalt xP (GW15)', ascending=False)

# 5. Skapa giltig startelva och bänk
gks = squad_df[squad_df['pos_type'] == 1]
defs = squad_df[squad_df['pos_type'] == 2]
mids = squad_df[squad_df['pos_type'] == 3]
fwds = squad_df[squad_df['pos_type'] == 4]

# Giltig basformation (1 GK, 3 DEF, 1 FWD krävs som minst)
start_gk = gks.head(1)
start_defs = defs.head(3)
start_fwds = fwds.head(1)

# Resterande 6 bästa utespelare
remaining_outfield = pd.concat([
    defs.iloc[3:], 
    mids, 
    fwds.iloc[1:]
]).sort_values(by='Totalt xP (GW15)', ascending=False)

start_others = remaining_outfield.head(6)

# Kombinera startelva och bänk
start_xi = pd.concat([start_gk, start_defs, start_fwds, start_others]).sort_values(by='pos_type')
bench = squad_df[~squad_df['id'].isin(start_xi['id'])].sort_values(by='pos_type')

total_cost = round(squad_df['Pris'].sum(), 1)
captain = start_xi.sort_values(by='Totalt xP (GW15)', ascending=False).iloc[0]['Spelare']

# 6. Spara till README.md
top_20_md = df.sort_values(by='Totalt xP (GW15)', ascending=False).head(20)[['Spelare', 'Lag', 'Pos', 'Pris', 'Snitt FDR', 'Totalt xP (GW15)']].to_markdown(index=False)
xi_md = start_xi[['Spelare', 'Lag', 'Pos', 'Pris', 'Totalt xP (GW15)']].to_markdown(index=False)
bench_md = bench[['Spelare', 'Lag', 'Pos', 'Pris', 'Totalt xP (GW15)']].to_markdown(index=False)

readme_content = f"""# 🏆 FPL AI Assistant (Aktiv Trupp)

Automatisk poängprognos med enbart **aktiva spelare (100% spelchans, >300 min)**.

---

## ⚽ Optimal AI-Startelva
* **Totalt trupppris:** £{total_cost}m / £100.0m
* **Vald Kapten 👑:** **{captain}**

### 🏃 Startelva (11 spelare)
{xi_md}

### 🪑 Bänk (4 spelare - alla spelmässigt aktiva)
{bench_md}

---

## 📊 Top 20 Spelare i Ligan
{top_20_md}
"""

script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else '.'
readme_path = os.path.join(script_dir, 'README.md')

with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(readme_content)

print("Klar! Truppen innehåller nu enbart spelare som faktiskt får speltid.")
