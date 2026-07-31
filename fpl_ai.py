import pulp
import requests

def hamta_och_berakna_fpl_data():
    base_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(base_url)
    data = response.json()
    
    fixtures_url = "https://fantasy.premierleague.com/api/fixtures/"
    fixtures_response = requests.get(fixtures_url)
    fixtures = fixtures_response.json()
    
    lag_omgang_fdr = {}
    for match in fixtures:
        gw = match.get('event')
        if gw and gw <= 38:
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
        player_status = player.get('status', 'a')
        if player_status in ['i', 's', 'u']:
            continue
            
        p_id = f"{player['first_name']} {player['second_name']} (ID:{player['id']})"
        
        mal = player.get('goals_scored', 0)
        assist = player.get('assists', 0)
        clean_sheets = player.get('clean_sheets', 0)
        minuter_spelade = player.get('minutes', 0)
        
        # Beräkna totala poäng och gör om till ett snitt per match (om man spelat matcher)
        total_poang = (mal * 5) + (assist * 3) + (clean_sheets * 2)
        matcher_spelade = max(1, minuter_spelade / 90.0)
        snitt_poang_per_match = total_poang / matcher_spelade
        
        spelar_lista.append(p_id)
        spelares_bas_index[p_id] = float(snitt_poang_per_match)
        spelares_pris[p_id] = player['now_cost'] / 10.0
        spelares_lag[p_id] = lag_map.get(player['team'], 'Okänt')
        spelares_lag_id[p_id] = player['team']
        spelares_position[p_id] = position_map.get(player['element_type'], 'Unknown')
        spelares_minuter[p_id] = minuter_spelade
        
    return spelar_lista, spelares_bas_index, spelares_pris, spelares_lag, spelares_lag_id, spelares_position, spelares_minuter, lag_omgang_fdr

def optimera_fpl_exakta_sparade_byten():
    spelar_lista, bas_index, pris, lag, lag_id, positioner, minuter, lag_omgang_fdr = hamta_och_berakna_fpl_data()
    
    print("Beräknar trupp med normaliserade poäng per omgång (GW 1-38)...")
    
    with open("optimal_lag.md", "w", encoding="utf-8") as f:
        f.write("# 🤖 AI-Optimerad Trupp med Startelva & Kapten (GW 1-38)\n\n")
        
        for_ra_trupp = set()
        sparade_byten = 0  
        wildcard_anvandt = False
        
        for gw in range(1, 39):
            prob = pulp.LpProblem(f"FPL_GW_{gw}", pulp.LpMaximize)
            
            x = pulp.LpVariable.dicts(f"spelare_gw{gw}", spelar_lista, cat='Binary')
            y = pulp.LpVariable.dicts(f"start_gw{gw}", spelar_lista, cat='Binary')
            c = pulp.LpVariable.dicts(f"kapten_gw{gw}", spelar_lista, cat='Binary')
            
            omgangs_index = {}
            for s in spelar_lista:
                t_id = lag_id[s]
                fdr = lag_omgang_fdr.get(t_id, {}).get(gw, 3)
                modifierare = (6 - fdr) / 3.0  
                omgangs_index[s] = max(0.5, bas_index[s] * modifierare)

            anvander_wildcard_nu = False
            tillgangliga_byten = 1 + sparade_byten

            if gw > 1 and len(for_ra_trupp) > 0 and not wildcard_anvandt:
                byten = pulp.LpVariable.dicts(f"byte_{gw}", list(for_ra_trupp), cat='Binary')
                for s in for_ra_trupp:
                    prob += byten[s] >= 1 - x[s]
                
                antal_byten = pulp.lpSum([byten[s] for s in for_ra_trupp])
                
                if gw == 8 or gw == 20:
                    anvander_wildcard_nu = True
                    wildcard_anvandt = True
                else:
                    prob += antal_byten <= tillgangliga_byten
            
            prob += pulp.lpSum([omgangs_index[s] * y[s] + omgangs_index[s] * c[s] for s in spelar_lista])
            
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

            prob += pulp.lpSum([y[s] for s in spelar_lista]) == 11
            prob += pulp.lpSum([y[s] for s in spelar_lista if positioner[s] == 'GK']) == 1
            prob += pulp.lpSum([y[s] for s in spelar_lista if positioner[s] == 'DEF']) >= 3
            prob += pulp.lpSum([y[s] for s in spelar_lista if positioner[s] == 'DEF']) <= 5
            prob += pulp.lpSum([y[s] for s in spelar_lista if positioner[s] == 'MID']) >= 2
            prob += pulp.lpSum([y[s] for s in spelar_lista if positioner[s] == 'MID']) <= 5
            prob += pulp.lpSum([y[s] for s in spelar_lista if positioner[s] == 'FWD']) >= 1
            prob += pulp.lpSum([y[s] for s in spelar_lista if positioner[s] == 'FWD']) <= 3

            for s in spelar_lista:
                prob += y[s] <= x[s]

            prob += pulp.lpSum([c[s] for s in spelar_lista]) == 1
            for s in spelar_lista:
                prob += c[s] <= y[s]

            prob.solve()
            
            if pulp.LpStatus[prob.status] == 'Optimal':
                nuvarande_trupp = set()
                startelva = set()
                kapten = None
                faktiska_byten = 0
                
                for s in spelar_lista:
                    if x[s].varValue and x[s].varValue > 0.5:
                        nuvarande_trupp.add(s)
                    if y[s].varValue and y[s].varValue > 0.5:
                        startelva.add(s)
                    if c[s].varValue and c[s].varValue > 0.5:
                        kapten = s
                
                banken = nuvarande_trupp - startelva

                if gw > 1 and len(for_ra_trupp) > 0 and not anvander_wildcard_nu:
                    faktiska_byten = len(nuvarande_trupp - for_ra_trupp)
                    anvanda_av_bank = min(tillgangliga_byten, faktiska_byten)
                    kvar_i_banken = tillgangliga_byten - anvanda_av_bank
                    sparade_byten = min(2, kvar_i_banken)
                elif anvander_wildcard_nu:
                    sparade_byten = 0

                beraknad_poang = sum(omgangs_index[s] for s in startelva) + (omgangs_index[kapten] if kapten else 0)

                f.write(f"## 🏆 Gameweek {gw}")
                if anvander_wildcard_nu:
                    f.write(" ⚡ **[WILDCARD AKTIVERAT!]**")
                f.write("\n")
                
                if gw > 1 and not anvander_wildcard_nu:
                    f.write(f"*Gjorda byten: {faktiska_byten} | Sparade byten: {sparade_byten}*\n")
                elif not gw > 1:
                    f.write(f"*Sparade byten: {sparade_byten}*\n")
                
                f.write(f"📈 **Realistisk förväntad poäng (Startelva + Kapten):** `{beraknad_poang:.1f} poäng`\n\n")
                
                f.write("### ⚽ Startelva\n")
                f.write("| Spelare | Lag | Pos | Pris | Omgångs-Index |\n")
                f.write("|---|---|---|---|---|\n")
                for pos in ['GK', 'DEF', 'MID', 'FWD']:
                    for s in sorted(list(startelva)):
                        if positioner[s] == pos:
                            kapten_mark = " ((C))" if s == kapten else ""
                            f.write(f"| {s}{kapten_mark} | {lag[s]} | {pos} | {pris[s]}M | {omgangs_index[s]:.1f} |\n")
                
                f.write("\n### 🛋️ Avbytare\n")
                f.write("| Spelare | Lag | Pos | Pris | Omgångs-Index |\n")
                f.write("|---|---|---|---|---|\n")
                for pos in ['GK', 'DEF', 'MID', 'FWD']:
                    for s in sorted(list(banken)):
                        if positioner[s] == pos:
                            f.write(f"| {s} | {lag[s]} | {pos} | {pris[s]}M | {omgangs_index[s]:.1f} |\n")
                
                for_ra_trupp = nuvarande_trupp
                f.write("\n---\n\n")

if __name__ == "__main__":
    optimera_fpl_exakta_sparade_byten()

