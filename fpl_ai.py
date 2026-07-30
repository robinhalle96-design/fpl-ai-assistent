import requests
import pandas as pd
import os

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

# 3. Beräkna poängprognos
player_projections = []
for p in players:
    if p['status'] != 'a' and p['chance_of_playing_next_round'] is not None and p['chance_of_playing_next_round'] < 50:
        continue
    if p['minutes'] < 180:
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
df = df.sort_values(by='Totalt xP (GW15)', ascending=False)
df.to_csv('fpl_predictions.csv', index=False)

# 4. Bygg optimalt 15-mannalag under 100m
gks = df[df['pos_type'] == 1].to_dict('records')
defs = df[df['pos_type'] == 2].to_dict('records')
mids = df[df['pos_type'] == 3].to_dict('records')
fwds = df[df['pos_type'] == 4].to_dict('records')

def build_squad():
    squad = []
    team_counts = {}

    def can_add(p):
        return team_counts.get(p['team_id'], 0) < 3

    def add_player(p):
        squad.append(p)
        team_counts[p['team_id']] = team_counts.get(p['team_id'], 0) + 1

    # Välj grundstomme
    add_player(gks[0])
    for p in gks[1:]:
        if can_add(p): add_player(p); break

    for p in defs:
        if len([x for x in squad if x['pos_type'] == 2]) < 5 and can_add(p):
            add_player(p)

    for p in mids:
        if len([x for x in squad if x['pos_type'] == 3]) < 5 and can_add(p):
            add_player(p)

    for p in fwds:
        if len([x for x in squad if x['pos_type'] == 4]) < 3 and can_add(p):
            add_player(p)

    # Budgetjustering: Om över 100m, ersätt billigaste/svagaste bänkspelarna med budgetalternativ
    current_cost = sum(p['Pris'] for p in squad)
    if current_cost > 100.0:
        # Hitta billiga spelare för varje position
        cheapest_gk = min(gks, key=lambda x: x['Pris'])
        cheapest_def = min(defs, key=lambda x: x['Pris'])
        cheapest_mid = min(mids, key=lambda x: x['Pris'])

        # Byt ut reservmålvakten till absolut billigaste
        gks_in_squad = [p for p in squad if p['pos_type'] == 1]
        if len(gks_in_squad) > 1:
            worst_gk = min(gks_in_squad, key=lambda x: x['Totalt xP (GW15)'])
            squad.remove(worst_gk)
            squad.append(cheapest_gk)

        # Nedgradera lägst rangerade försvarare/mittfältare tills budget hålls
        squad.sort(key=lambda x: (x['pos_type'] == 1, x['Totalt xP (GW15)']))
        for i in range(len(squad)):
            if sum(p['Pris'] for p in squad) <= 100.0:
                break
            if squad[i]['pos_type'] == 2 and squad[i]['id'] != cheapest_def['id']:
                squad[i] = cheapest_def
            elif squad[i]['pos_type'] == 3 and squad[i]['id'] != cheapest_mid['id']:
                squad[i] = cheapest_mid

    return pd.DataFrame(squad)

squad_df = build_squad()
total_cost = round(squad_df['Pris'].sum(), 1)

starting_gk = squad_df[squad_df['pos_type'] == 1].sort_values(by='Totalt xP (GW15)', ascending=False).head(1)
outfield = squad_df[squad_df['pos_type'] != 1].sort_values(by='Totalt xP (GW15)', ascending=False)
starting_10 = outfield.head(10)
bench = pd.concat([squad_df[squad_df['pos_type'] == 1].tail(1), outfield.tail(4)])

start_xi = pd.concat([starting_gk, starting_10])
captain = start_xi.iloc[0]['Spelare']

top_20_md = df[['Spelare', 'Lag', 'Pos', 'Pris', 'Snitt FDR', 'Totalt xP (GW15)']].head(20).to_markdown(index=False)
xi_md = start_xi[['Spelare', 'Lag', 'Pos', 'Pris', 'Totalt xP (GW15)']].to_markdown(index=False)
bench_md = bench[['Spelare', 'Lag', 'Pos', 'Pris', 'Totalt xP (GW15)']].to_markdown(index=False)

readme_content = f"""# 🏆 FPL AI Assistant

Automatisk poängprognos och **Optimalt Wildcard-lag (£100m budget)** fram till **Omgång 15**.

---

## ⚽ Optimal AI-Startelva (GW15-prognos)
* **Totalt trupppris:** £{total_cost}m / £100.0m
* **Vald Kapten 👑:** **{captain}** (högst förväntade poäng)

### 🏃 Startelva (11 spelare)
{xi_md}

### 🪑 Bänk (4 spelare)
{bench_md}

---

## 📊 Top 20 Spelare i Ligan
{top_20_md}

*Databasen uppdateras automatiskt varje natt.*
"""

script_dir = os.path.dirname(os.path.abspath(__file__))
readme_path = os.path.join(script_dir, 'README.md')

with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(readme_content)

print("Klar! README.md har uppdaterats med budgetanpassat lag.")

