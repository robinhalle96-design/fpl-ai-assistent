import requests
import pandas as pd
import json

# 1. Hämta data från FPL:s officiella API
BASE_URL = "https://fantasy.premierleague.com/api/"
r = requests.get(f"{BASE_URL}bootstrap-static/").json()

players = r['elements']
teams = {t['id']: t['name'] for t in r['teams']}
element_types = {e['id']: e['singular_name_short'] for e in r['element_types']}

# 2. Beräkna poängprognos per spelare
player_projections = []

for p in players:
    # Filtrera bort skadade eller avstängda spelare
    if p['status'] != 'a' and p['chance_of_playing_next_round'] is not None and p['chance_of_playing_next_round'] < 50:
        continue

    minutes = p['minutes']
    if minutes < 180:  # Hoppa över spelare med för lite speltid
        continue

    form = float(p['form'])  # Senaste formen
    ppm = float(p['points_per_game'])  # Snittpoäng per match
    ict = float(p['ict_index'])  # Influence, Creativity, Threat
    cost = p['now_cost'] / 10.0

    # Grundläggande xP-modell (väger form, snitt och ICT)
    base_xp_per_gw = (form * 0.4) + (ppm * 0.4) + (ict / 20.0 * 0.2)
    
    # Beräkna totalt förväntade poäng för de kommande omgångarna upp till Omgång 15
    # (Här kan du bygga ut med specifik FDR/matchsvårighet per omgång)
    projected_total_xp = round(base_xp_per_gw * 15, 1)

    player_projections.append({
        'name': p['web_name'],
        'team': teams[p['team']],
        'position': element_types[p['element_type']],
        'cost': cost,
        'form': form,
        'selected_by_percent': float(p['selected_by_percent']),
        'xp_per_gw': round(base_xp_per_gw, 2),
        'total_xp_gw15': projected_total_xp
    })

# 3. Sortera och spara resultat
df = pd.DataFrame(player_projections)
df = df.sort_values(by='total_xp_gw15', ascending=False)

# Spara som CSV och JSON i repositoriet
df.to_csv('fpl_predictions.csv', index=False)

# Skapa en enkel summeringsfil för README
top_15 = df.head(15).to_markdown(index=False)
with open('top_players.md', 'w') as f:
    f.write("# 🏆 FPL AI Top 15 Picks (Uppdaterad)\n\n")
    f.write(top_15)

print("Uppdatering klar! fpl_predictions.csv och top_players.md har skapats.")

