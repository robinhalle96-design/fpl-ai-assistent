import requests
import pandas as pd

# 1. Hämta live-data från FPL:s officiella API
BASE_URL = "https://fantasy.premierleague.com/api/"
bootstrap = requests.get(f"{BASE_URL}bootstrap-static/").json()
fixtures = requests.get(f"{BASE_URL}fixtures/").json()

players = bootstrap['elements']
teams = {t['id']: t['name'] for t in bootstrap['teams']}
element_types = {e['id']: e['singular_name_short'] for e in bootstrap['element_types']}

# Hitta nuvarande omgång
current_gw = 1
for event in bootstrap['events']:
    if event['is_current']:
        current_gw = event['id']
        break
    elif event['is_next']:
        current_gw = event['id'] - 1
        break

target_gw = 15  # Vi beräknar fram till omgång 15

# 2. Skapa en kartläggning av kommande matchsvårighet per lag
team_fdr = {t_id: [] for t_id in teams.keys()}

for f in fixtures:
    gw = f.get('event')
    if gw and current_gw < gw <= target_gw:
        # Hemma/Bortasvårighet
        team_fdr[f['team_h']].append(f['team_h_difficulty'])
        team_fdr[f['team_a']].append(f['team_a_difficulty'])

# 3. Beräkna poängprognos per spelare
player_projections = []

for p in players:
    # Filtrera bort skadade/avstängda spelare
    if p['status'] != 'a' and p['chance_of_playing_next_round'] is not None and p['chance_of_playing_next_round'] < 50:
        continue

    minutes = p['minutes']
    if minutes < 180:  # Ta bara med spelare som spelar regelbundet
        continue

    form = float(p['form'])
    ppm = float(p['points_per_game'])
    ict = float(p['ict_index'])
    cost = p['now_cost'] / 10.0
    team_id = p['team']

    # Beräkna genomsnittlig matchsvårighet fram till GW15 (lägre = enklare)
    upcoming_fdr = team_fdr.get(team_id, [3])
    avg_fdr = sum(upcoming_fdr) / len(upcoming_fdr) if upcoming_fdr else 3.0

    # FDR-multiplikator: Enkelt schema (FDR ~2) ger bonus, svårt (FDR ~4-5) ger avdrag
    fdr_factor = 1 + ((3.0 - avg_fdr) * 0.1)

    # Basmodell för förväntade poäng per match
    base_xp_per_gw = ((form * 0.35) + (ppm * 0.45) + (ict / 20.0 * 0.20)) * fdr_factor
    
    num_games = len(upcoming_fdr) if upcoming_fdr else (target_gw - current_gw)
    projected_total_xp = round(base_xp_per_gw * num_games, 1)

    player_projections.append({
        'Spelare': p['web_name'],
        'Lag': teams[team_id],
        'Pos': element_types[p['element_type']],
        'Pris': f"£{cost}",
        'Form': form,
        'Snitt FDR': round(avg_fdr, 2),
        'xP/Match': round(base_xp_per_gw, 2),
        'Totalt xP (GW15)': projected_total_xp
    })

# 4. Sortera och skapa filer
df = pd.DataFrame(player_projections)
df = df.sort_values(by='Totalt xP (GW15)', ascending=False)

# Spara hela databasen som CSV
df.to_csv('fpl_predictions.csv', index=False)

# Uppdatera README.md så att topp-20 visas direkt på GitHub-sidan
top_20_md = df.head(20).to_markdown(index=False)

readme_content = f"""# 🏆 FPL AI Assistant

Automatisk poängprognos för alla spelare fram till **Omgång 15**.

Modellen väger samman:
* **Spelarform** (senaste matcherna)
* **Historiskt poängsnitt**
* **ICT-index** (Underliggande statistik/chanser)
* **Matchsvårighet (FDR)** för alla kommande matcher fram till GW15

## Top 20 Spelare (Prognos till GW15)

{top_20_md}

*Databasen uppdateras automatiskt varje natt.*
"""

with open('README.md', 'w', encoding='utf-8') as f:
    f.write(readme_content)

print("Uppdatering klar med FDR-data!")
