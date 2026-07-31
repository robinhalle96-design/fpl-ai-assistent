import pulp
import requests

def hamta_och_berakna_fpl_data():
    """Hämtar spelardata, spelschema och räknar ut ett omgångsbaserat index."""
    base_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(base_url)
    data = response.json()
    
    # Hämtar spelschemat för att kunna beräkna motstånd per omgång
    fixtures_url = "https://fantasy.premierleague.com/api/fixtures/"
    fixtures_response = requests.get(fixtures_url)
    fixtures = fixtures_response.json()
    
    # Skapa en karta över lagets svårighet per omgång eller motstånd
    # Vi mappar lag-ID till kommande matcher (omgång -> motståndets styrka/FDR)
    lag_omgang_fdr = {}
    for match in fixtures:
        gw = match.get('event')
        if gw and gw <= 19:  # Vi kikar på omgång 1 till 19 (fram till jul)
            h_team = match.get('team_h')
            a_team = match.get('team_a')
            h_diff = match.get('team_h_difficulty', 3)
            a_diff = match.get('team_a_difficulty', 3)
            
            lag_omgang_fdr.setdefault(h_team, {})[gw] = h_diff
            lag_omgang_fdr.setdefault(a_team, {})[gw] = a_diff

    spelar_lista = []
    spelares_pris = {}
    spelares_lag = {}
    spelares_lag_id = {}
    spelares_position = {}
    spelares_minuter = {}
    spelares_bas_index = {}
    
    position_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
    lag_map = {team['id']: team['name'] for team in data['teams']}
    
    for player in data['elements']:
        p_id = f"{player['first_name']} {player['second_name']} (ID:{player['id']})"
        
        mal = player.get('goals_scored', 0)
        assist = player.get('assists', 0)
        clean_sheets = player.get('clean_sheets', 0)
        minuter_spelade = player.get('minutes', 0)
        
        # Basindex baserat på historisk statistik
        stat_index = (mal * 5) + (assist * 3) + (clean_sheets * 2)
        
        spelar_lista.append(p_id)
        spelares_bas_index[p_id] = float(stat_index)
        spelares_pris[p_id] = player['now_cost'] / 10.0
        spelares_lag[p_id] = lag_map.get(player['team'], 'Okänt')
        spelares_lag_id[p_id] = player['team']
        spelares_position[p_id] = position_map.get(player['element_type'], 'Unknown')
        spelares_minuter[p_id] = minuter_spelade
        
    return spelar_lista, spelares_bas_index, spelares_pris, spelares_lag, spelares_lag_id, spelares_position, spelares_minuter, lag_omgang_fdr

def optimera_fpl_per_omgang():
    spelar_lista, bas_index, pris, lag, lag_id, positioner, minuter, lag_omgang_fdr = hamta_och_berakna_fpl_data()
    
    print("Beräknar optimala lag omgång för omgång (GW 1-19)...")
    
    # Spara ner resultatet till filen omgång för omgång
    with open("optimal_lag.md", "w", encoding="utf-8") as f:
        f.write("# 🤖 AI-Optimerad Trupp Omgång för Omspaning (GW 1-19)\n\n")
        f.write("Här är det taktiskt bästa laget beräknat vecka för vecka baserat på spelschema och motstånd fram till jul.\n\n")
        
        # Loopa igenom omgång 1 till 19
        for gw in range(1, 20):
            prob = pulp.LpProblem(f"FPL_GW_{gw}", pulp.LpMaximize)
            x = pulp.LpVariable.dicts(f"spelare_gw{gw}", spelar_lista, cat='Binary')
            
            # Beräkna omgångsspecifikt index baserat på motståndets svårighet (FDR)
            omgangs_index = {}
            for s in spelar_lista:
                t_id = lag_id[s]
                fdr = lag_omgang_fdr.get(t_id, {}).get(gw, 3) # Standard svårighet 3 om saknas
                # Om det är en lättare match (lågt FDR) får spelaren en boost, svår match sänker
                modifierare = (6 - fdr) / 3.0  
                omgangs_index[s] = max(1.0, bas_index[s] * modifierare)

            prob += pulp.lpSum([omgangs_index[s] * x[s] for s in spelar_lista])
            
            # Truppregler
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
            
            if pulp.LpStatus[prob.status] == 'Optimal':
                f.write(f"## 🏆 Gameweek {gw}\n")
                f.write("| Spelare | Lag | Pos | Pris | Omgångs-Index |\n")
                f.write("|---|---|---|---|---|\n")
                
                for pos in ['GK', 'DEF', 'MID', 'FWD']:
                    for s in spelar_lista:
                        if positioner[s] == pos and x[s].varValue == 1:
                            f.write(f"| {s} | {lag[s]} | {pos} | {pris[s]}M | {omgangs_index[s]:.1f} |\n")
                f.write("\n---\n\n")

if __name__ == "__main__":
    optimera_fpl_per_omgang()
