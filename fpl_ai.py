import pulp
import requests

def hamta_och_berakna_fpl_data():
    """Hämtar spelardata, spelschema och räknar ut ett omgångsbaserat index."""
    base_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(base_url)
    data = response.json()
    
    fixtures_url = "https://fantasy.premierleague.com/api/fixtures/"
    fixtures_response = requests.get(fixtures_url)
    fixtures = fixtures_response.json()
    
    lag_omgang_fdr = {}
    for match in fixtures:
        gw = match.get('event')
        if gw and gw <= 19:
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
        
        stat_index = (mal * 5) + (assist * 3) + (clean_sheets * 2)
        
        spelar_lista.append(p_id)
        spelares_bas_index[p_id] = float(stat_index)
        spelares_pris[p_id] = player['now_cost'] / 10.0
        spelares_lag[p_id] = lag_map.get(player['team'], 'Okänt')
        spelares_lag_id[p_id] = player['team']
        spelares_position[p_id] = position_map.get(player['element_type'], 'Unknown')
        spelares_minuter[p_id] = minuter_spelade
        
    return spelar_lista, spelares_bas_index, spelares_pris, spelares_lag, spelares_lag_id, spelares_position, spelares_minuter, lag_omgang_fdr

def optimera_fpl_med_transfers():
    spelar_lista, bas_index, pris, lag, lag_id, positioner, minuter, lag_omgang_fdr = hamta_och_berakna_fpl_data()
    
    print("Beräknar realistisk trupp med transfer-logik (GW 1-19)...")
    
    with open("optimal_lag.md", "w", encoding="utf-8") as f:
        f.write("# 🤖 AI-Optimerad Trupp med Transfer-logik (GW 1-19)\n\n")
        f.write("Här är truppen som rullar vidare vecka för vecka med hänsyn till befintliga spelare för att undvika onödiga minusbyten.\n\n")
        
        for_ra_trupp = set()
        
        for gw in range(1, 20):
            prob = pulp.LpProblem(f"FPL_GW_{gw}", pulp.LpMaximize)
            x = pulp.LpVariable.dicts(f"spelare_gw{gw}", spelar_lista, cat='Binary')
            
            # Beräkna omgångsspecifikt index
            omgangs_index = {}
            for s in spelar_lista:
                t_id = lag_id[s]
                fdr = lag_omgang_fdr.get(t_id, {}).get(gw, 3)
                modifierare = (6 - fdr) / 3.0  
                omgangs_index[s] = max(1.0, bas_index[s] * modifierare)

            # Om det inte är GW1 vill vi minimera antalet byten från föregående omgång
            if gw > 1 and len(for_ra_trupp) > 0:
                # Maximera poäng MINUS en straffavgift för spelare som byts ut
                # Vi skapar en variabel för antalet spelare som INTE fanns med förra veckan (nya byten)
                byten = pulp.LpVariable.dicts(f"byte_{gw}", list(for_ra_trupp), cat='Binary')
                for s in for_ra_trupp:
                    # Om spelaren från förra veckan INTE är med i nuvarande lag (x[s] == 0), så räknas det som ett byte
                    prob += byten[s] >= 1 - x[s]
                
                # Om man gör fler än 1 byte per omgång kostar det 4 poäng per extra byte i modulen
                # (Vi låter skriptet väga poängvinsten mot minuspoängskostnaden på 4p per extra byte)
                extra_byten_straff = 4.0
                antal_extra_byten = pulp.LpVariable(f"extra_byten_{gw}", lowBound=0, cat='Continuous')
                prob += antal_extra_byten >= pulp.lpSum([byten[s] for s in for_ra_trupp]) - 1.0 # 1 gratisbyte per vecka
                
                prob += pulp.lpSum([omgangs_index[s] * x[s] for s in spelar_lista]) - (antal_extra_byten * extra_byten_straff)
            else:
                prob += pulp.lpSum([omgangs_index[s] * x[s] for s in spelar_lista])
            
            # Standard FPL-regler
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
                nuvarande_trupp = set()
                f.write(f"## 🏆 Gameweek {gw}\n")
                f.write("| Spelare | Lag | Pos | Pris | Omgångs-Index |\n")
                f.write("|---|---|---|---|---|\n")
                
                for pos in ['GK', 'DEF', 'MID', 'FWD']:
                    for s in spelar_lista:
                        if positioner[s] == pos and x[s].varValue and x[s].varValue > 0.5:
                            f.write(f"| {s} | {lag[s]} | {pos} | {pris[s]}M | {omgangs_index[s]:.1f} |\n")
                            nuvarande_trupp.add(s)
                
                for_ra_trupp = nuvarande_trupp
                f.write("\n---\n\n")

if __name__ == "__main__":
    optimera_fpl_med_transfers()
