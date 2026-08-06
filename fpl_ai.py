import requests
import pandas as pd
import pulp

# 1. Hämtar datan från Premier League
print("Hämtar data från FPL...")
url = "https://fantasy.premierleague.com/api/bootstrap-static/"
headers = {"User-Agent": "Mozilla/5.0"}
data = requests.get(url, headers=headers).json()

# 2. Förbereder spelarna
players = pd.DataFrame(data["elements"])
players = players[players['status'] == 'a'] # Väljer bara spelare som inte är skadade
players['price'] = players['now_cost'] / 10 # Fixar till priserna
players['form'] = pd.to_numeric(players['form']) # Hämtar spelarnas nuvarande form

# 3. AI:n bygger laget
prob = pulp.LpProblem("FPL_Dream_Team", pulp.LpMaximize)
player_vars = pulp.LpVariable.dicts("Players", players.index, cat='Binary')

# Mål: Få så hög 'form' som möjligt på laget
prob += pulp.lpSum([players['form'][i] * player_vars[i] for i in players.index])

# Regel 1: Välj exakt 11 spelare
prob += pulp.lpSum([player_vars[i] for i in players.index]) == 11

# Regel 2: Max 83 miljoner i budget (eftersom de 4 bänkspelarna kostar minst 17m)
prob += pulp.lpSum([players['price'][i] * player_vars[i] for i in players.index]) <= 83.0

print("AI räknar ut bästa laget...\n")
prob.solve()

# 4. Skriver ut resultatet på skärmen!
print("🌟 HÄR ÄR DITT OPTIMALA LAG JUST NU 🌟")
for i in players.index:
    if player_vars[i].varValue == 1.0:
        print(f"- {players['web_name'][i]} ({players['price'][i]}m)")
