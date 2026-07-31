
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

def optimera_fpl_exakta_sparade_byten():
    spelar_lista, bas_index, pris, lag, lag_id, positioner, minuter, lag_omgang_fdr = hamta_och_berakna_fpl_data()
    
    print("Beräknar trupp med exakt logik för sparade byten (inga minuspoäng)...")
    
    with open("optimal_lag.md", "w", encoding="utf-8") as f:
        f.write("# 🤖 AI-Optimerad Trupp med Sparade Byten (GW 1-19)\n\n")
        f.write("Här följer skriptet reglerna: 1 gratisbyte per omgång som kan sparas till max 2. Inga minuspoäng tillåts!\n\n")
        
        for_ra_trupp = set()
        sparade_byten = 0  # Börjar med 0 sparade byten inför omgång 2 (1 tillgängligt)
        wildcard_anvandt = False
        
        for gw in range(1, 20):
            prob = pulp.LpProblem(f"FPL_GW_{gw}", pulp.LpMaximize)
            x = pulp.LpVariable.dicts(f"spelare_gw{gw}", spelar_lista, cat='Binary')
            
            omgangs_index = {}
            for s in spelar_lista:
                t_id = lag_id[s]
                fdr = lag_omgang_fdr.get(t_id, {}).get(gw, 3)
                modifierare = (6 - fdr) / 3.0  
                omgangs_index[s] = max(1.0, bas_index[s] * modifierare)

            anvander_wildcard_nu = False
            tillgangliga_byten = 1 + sparade_byten

            if gw > 1 and len(for_ra_trupp) > 0 and not wildcard_anvandt:
                byten = pulp.LpVariable.dicts(f"byte_{gw}", list(for_ra_trupp), cat='Binary')
                for s in for_ra_trupp:
                    prob += byten[s] >= 1 - x[s]
                
                antal_byten = pulp.lpSum([byten[s] for s in for_ra_trupp])
                
                if gw == 8:  # Wildcard i omgång 8
                    anvander_wildcard_nu = True
                    wildcard_anvandt = True
                else:
                    # STRIKT REGLER: Får aldrig göra fler byten än man har tillgängligt (inga minuspoäng)
                    prob += antal_byten <= tillgangliga_byten
            
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
                faktiska_byten = 0
                
                for pos in ['GK', 'DEF', 'MID', 'FWD']:
                    for s in spelar_lista:
                        if positioner[s] == pos and x[s].varValue and x[s].varValue > 0.5:
                            nuvarande_trupp.add(s)
                
                if gw > 1 and len(for_ra_trupp) > 0 and not anvander_wildcard_nu:
                    faktiska_byten = len(nuvarande_trupp - for_ra_trupp)
                    # Beräkna hur många byten som finns kvar till nästa omgång (max 2)
                    anvanda_av_bank = min(tillgangliga_byten, faktiska_byten)
                    kvar_i_banken = tillgangliga_byten - anvanda_av_bank
                    sparade_byten = min(2, kvar_i_banken)
                elif anvander_wildcard_nu:
                    sparade_byten = 0

                f.write(f"## 🏆 Gameweek {gw}")
                if anvander_wildcard_nu:
                    f.write(" ⚡ **[WILDCARD AKTIVERAT - Hela truppen ombyggd!]**")
                f.write("\n")
                
                if gw > 1 and not anvander_wildcard_nu:
                    f.write(f"*Gjorda byten denna omgång: {faktiska_byten} | Sparade byten till nästa omgång: {sparade_byten}*\n\n")
                elif not gw > 1:
                    f.write(f"*Sparade byten till nästa omgång: {sparade_byten}*\n\n")
                
                f.write("| Spelare | Lag | Pos | Pris | Omgångs-Index |\n")
                f.write("|---|---|---|---|---|\n")
                
                for pos in ['GK', 'DEF', 'MID', 'FWD']:
                    for s in spelar_lista:
                        if positioner[s] == pos and x[s].varValue and x[s].varValue > 0.5:
                            f.write(f"| {s} | {lag[s]} | {pos} | {pris[s]}M | {omgangs_index[s]:.1f} |\n")
                
                for_ra_trupp = nuvarande_trupp
                f.write("\n---\n\n")

if __name__ == "__main__":
    optimera_fpl_exakta_sparade_byten()
