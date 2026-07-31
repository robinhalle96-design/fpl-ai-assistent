import pulp
import requests

def hamta_och_berakna_fpl_data():
    """Hämtar spelardata och räknar ut ett totalindex baserat på mål, assist och defensiv statistik."""
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(url)
    data = response.json()
    
    spelar_lista = []
    spelares_index = {}
    spelares_pris = {}
    spelares_lag = {}
    spelares_position = {}
    spelares_minuter = {}
    
    position_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
    lag_map = {team['id']: team['name'] for team in data['teams']}
    
    for player in data['elements']:
        p_id = f"{player['first_name']} {player['second_name']} (ID:{player['id']})"
        
        mal = player.get('goals_scored', 0)
        assist = player.get('assists', 0)
        clean_sheets = player.get('clean_sheets', 0)
        minuter_spelade = player.get('minutes', 0)
        
        stat_index = (mal * 5) + (assist * 3) + (clean_sheets * 2)
        
        spelar_lista.append(p_id)
        spelares_index[p_id] = float(stat_index)
        spelares_pris[p_id] = player['now_cost'] / 10.0
        spelares_lag[p_id] = lag_map.get(player['team'], 'Okänt')
        spelares_position[p_id] = position_map.get(player['element_type'], 'Unknown')
        spelares_minuter[p_id] = minuter_spelade
        
    return spelar_lista, spelares_index, spelares_pris, spelares_lag, spelares_position, spelares_minuter

def optimera_fpl_trupp(spelar_lista, index_poang, pris, lag, positioner, minuter):
    """Optimerar truppen baserat på det nya statistiska indexet för mål, assist och defensiv."""
    print("Beräknar trupp med bäst statistik för mål, assist och defensiv...")
    
    prob = pulp.LpProblem("FPL_Optimal_Stats_Squad", pulp.LpMaximize)
    
    x = pulp.LpVariable.dicts("spelare", spelar_lista, cat='Binary')
    
    prob += pulp.lpSum([index_poang[s] * x[s] for s in spelar_lista])
    
    prob += pulp.lpSum([x[s] for s in spelar_lista]) == 15
    prob += pulp.lpSum([x[s] for s in spelar_lista if positioner[s] == 'GK']) == 2
    prob += pulp.lpSum([x[s] for s in spelar_lista if positioner[s] == 'DEF']) == 5
    prob += pulp.lpSum([x[s] for s in spelar_lista if positioner[s] == 'MID']) == 5
    prob += pulp.lpSum([x[s] for s in spelar_lista if positioner[s] == 'FWD']) == 3
    
    prob += pulp.lpSum([pris[s] * x[s] for s in spelar_lista]) <= 100.0
    
    for l in set(lag.values()):
        prob += pulp.lpSum([x[s] for s in spelar_lista if lag[s] == l]) <= 3
        
    for s in spelar_lista:
        if minuter[s] < 90:
            prob += x[s] == 0

    prob.solve()
    
    if pulp.LpStatus[prob.status] != 'Optimal':
        print("Kunde inte hitta en lösning med nuvarande villkor.")
        return

    print("\n==============================================")
    print("  TRUPP MED BÄST STATISTIK (MÅL/ASSIST/DEF)  ")
    print("==============================================")
    
    total_kostnad = 0
    
    for pos in ['GK', 'DEF', 'MID', 'FWD']:
        print(f"\n--- {pos} ---")
        for s in spelar_lista:
            if positioner[s] == pos and x[s].varValue == 1:
                print(f"• {s} | Lag: {lag[s]} | Pris: {pris[s]}M | Statistik-Index: {index_poang[s]}")
                total_kostnad += pris[s]
                
    print("\n----------------------------------------------")
    print(f"Total kostnad för truppen: {total_kostnad:.1f}M")
    print("==============================================\n")

    # Spara ner resultatet till en fil direkt i mappen
    with open("optimal_lag.md", "w", encoding="utf-8") as f:
        f.write("# 🤖 AI-Optimerad 15-Mannatrupp\n\n")
        f.write(f"**Total kostnad:** {total_kostnad:.1f}M / 100.0M\n\n")
        
        for pos in ['GK', 'DEF', 'MID', 'FWD']:
            f.write(f"### {pos}\n")
            for s in spelar_lista:
                if positioner[s] == pos and x[s].varValue == 1:
                    f.write(f"- **{s}** | Lag: {lag[s]} | Pris: {pris[s]}M | Index: {index_poang[s]}\n")
            f.write("\n")

if __name__ == "__main__":
    spelar_lista, index_poang, pris, lag, positioner, minuter = hamta_och_berakna_fpl_data()
    optimera_fpl_trupp(spelar_lista, index_poang, pris, lag, positioner, minuter)
