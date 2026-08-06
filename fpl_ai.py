
import requests
import pandas as pd
import pulp

# 1. Hämtar datan 
print("Hämtar data från FPL...")
url = "https://fantasy.premierleague.com/api/bootstrap-static/"
headers = {"User-Agent": "Mozilla/5.0"}
data = requests.get(url, headers=headers).json()

# 2. Förbereder spelarna
players = pd.DataFrame(data["elements"])
players = players[players['status'] == 'a']
players['price'] = players['now_cost'] / 10

# FIX: Vi använder 'total_points' istället för snittpoäng. 
# Detta rensar bort bänkspelare och ger oss de verkliga poängmaskinerna.
players['total_points'] = pd.to_numeric(players['total_points'])

# Positioner (1=Målvakt, 2=Back, 3=Mittfältare, 4=Anfallare)
players['position'] = players['element_type']

# 3. AI:n bygger laget
prob = pulp.LpProblem("FPL_Dream_Team", pulp.LpMaximize)
player_vars = pulp.LpVariable.dicts("Players", players.index, cat='Binary')

# Nytt Mål: Maximera de totala poängen i laget
prob += pulp.lpSum([players['total_points'][i] * player_vars[i] for i in players.index])

# Budget (max 83 miljoner för 11 startspelare)
prob += pulp.lpSum([players['price'][i] * player_vars[i] for i in players.index]) <= 83.0

# Exakt 11 spelare på planen
prob += pulp.lpSum([player_vars[i] for i in players.index]) == 11

# --- REGLER FÖR EN RIKTIG UPPSTÄLLNING ---
prob += pulp.lpSum([player_vars[i] for i in players.index if players['position'][i] == 1]) == 1
prob += pulp.lpSum([player_vars[i] for i in players.index if players['position'][i] == 2]) >= 3
prob += pulp.lpSum([player_vars[i] for i in players.index if players['position'][i] == 3]) >= 2
prob += pulp.lpSum([player_vars[i] for i in players.index if players['position'][i] == 4]) >= 1

print("AI räknar ut bästa startelvan baserat på tunga mätvärden...\n")
prob.solve()

# 4. Skriver ut resultatet på skärmen
print("🌟 HÄR ÄR DIN OPTIMALA STARTELVA (Totalpoäng) 🌟")
for i in players.index:
    if player_vars[i].varValue == 1.0:
        print(f"- {players['web_name'][i]} ({players['price'][i]}m, Totalpoäng: {players['total_points'][i]})")
