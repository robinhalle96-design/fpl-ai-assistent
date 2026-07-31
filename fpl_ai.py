import pulp
import requests

def hamta_och_berakna_fpl_data():
    base_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    response = requests.get(base_url)
    data = response.json()
    
    fixtures_url = "https://fantasy.premierleague.com/api/fixtures/"
    fixtures_response = requests.get(fixtures_url)
    fixtures = fixtures_response.json()
    
    # SVARTLISTA: Lägg till ID för spelare som ska rensas bort helt
    # Exempel: Lucas Digne (ID: 30) och Karl Darlow (lägg in deras ID-nummer här)
    svartlista_ids = [30] # Lägg till fler ID:n i listan om det behövs, t.ex. [30, ID_FÖR_DARLOW]
    
    lag_omgang_fdr = {}
    lag_namn_dict = {team['id']: team['name'] for team in data['teams']}
    
    omgang_matcher = {}
    for match in fixtures:
        gw = match.get('event')
        if gw and gw <= 38:
            h_team = match.get('team_h')
            a_team = match.get('team_a')
            h_diff = match.get('team_h_difficulty', 3)
            a_diff = match.get('team_a_difficulty', 3)
            
            lag_omgang_fdr.setdefault(h_team, {})[gw] = h_diff
            lag_omgang_fdr.setdefault(a_team, {})[gw] = a_diff
            
            h_namn = lag_namn_dict.get(h_team, "Hemma")
            a_namn = lag_namn_dict.get(a_team, "Borta")
            
            omgang_matcher.setdefault(gw, {})[h_team] = f"vs {a_namn} (H)"
            omgang_matcher.setdefault(gw, {})[a_team] = f"vs {h_namn} (B)"

    spelar_lista = []
    spelares_pris = {}
    spelares_lag = {}
    spelares_lag_id = {}
    spelares_position = {}
    spelares_minuter = {}
    spelares_bas_index = {}
    
    position_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
    
    for player in data['elements']:
        p_id_num = player['id']
        
        # Extra kontroll för att säkerställa att även namn som matchar blockeras direkt om man vill
        full_namn = f"{player['first_name']} {player['second_name']}"
        if p_id_num in svartlista_ids or "Darlow" in full_namn or "Digne" in full_namn:
            continue
            
        player_status = player.get('status', 'a')
        if player_status in ['i', 's', 'u']:
            continue
            
        minuter_spelade = player.get('minutes', 0)
        pris_mil = player.get('now_cost') / 10.0
        
        element_type = player.get('element_type')
        if element_type == 1: 
            if minuter_spelade < 1500: 
                continue
        else: 
            if minuter_spelade < 1200 and pris_mil > 5.0:
                continue
            if minuter_spelade < 800 and pris_mil <= 5.0:
                continue
            
        p_id = f"{full_namn} (ID:{p_id_num})"
        
        mal = player.get('goals_scored', 0)
        assist = player.get('assists', 0)
        clean_sheets = player.get('clean_sheets', 0)
        
        total_poang = (mal * 6) + (assist * 4) + (clean_sheets * 3)
        matcher_spelade = max(1, minuter_spelade / 90.0)
        snitt_poang_per_match = (total_poang / matcher_spelade) * 1.3
        
        lag_id_num = player['team']
        lag_namn = lag_namn_dict.get(lag_id_num, 'Okänt')
        
        spelar_lista.append(p_id)
        spelares_bas_index[p_id] = float(snitt_poang_per_match)
        spelares_pris[p_id] = pris_mil
        spelares_lag[p_id] = lag_namn
        spelares_lag_id[p_id] = lag_id_num
        spelares_position[p_id] = position_map.get(player['element_type'], 'Unknown')
        spelares_minuter[p_id] = minuter_spelade
        
    return spelar_lista, spelares_bas_index, spelares_pris, spelares_lag, spelares_lag_id, spelares_position, spelares_minuter, lag_omgang_fdr, omgang_matcher

def optimera_fpl_med_chips():
    spelar_lista, bas_index, pris, lag, lag_id, positioner, minuter, lag_omgang_fdr, omgang_matcher = hamta_och_berakna_fpl_data()
    
    print("Optimerar FPL-trupp med rensad svartlista...")
    
    with open("optimal_lag.md", "w", encoding="utf-8") as f:
        f.write("# 🤖 AI-Optimerad FPL-Trupp (Rensad)\n\n")
        
        for_ra_trupp = set()
        sparade_byten = 0  
        
        valda_wc1 = 8
        valda_wc2 = 26
        valda_fh = 29
        valda_tc = 17
        valda_bb = 34
        
        starka_lag = ["Arsenal", "Manchester City", "Liverpool", "Aston Villa", "Tottenham Hotspur"]
        
        for gw in range(1, 39):
            prob = pulp.LpProblem(f"FPL_GW_{gw}", pulp.LpMaximize)
            
            x = pulp.LpVariable.dicts(f"spelare_gw{gw}", spelar_lista, cat='Binary')
            y = pulp.LpVariable.dicts(f"start_gw{gw}", spelar_lista, cat='Binary')
            c = pulp.LpVariable.dicts(f"kapten_gw{gw}", spelar_lista, cat='Binary')
            
            omgangs_index = {}
            for s in spelar_lista:
                t_id = lag_id[s]
                fdr = lag_omgang_fdr.get(t_id, {}).get(gw, 3)
                modifierare = (6 - fdr) / 2.8  
                
                lag_bonus = 1.15 if (pris[s] <= 4.5 and lag[s] in starka_lag) else 1.0
                omgangs_index[s] = max(1.0, bas_index[s] * modifierare * lag_bonus)

            anvander_wildcard = (gw == valda_wc1 or gw == valda_wc2)
            anvander_free_hit = (gw == valda_fh)
            anvander_triple_captain = (gw == valda_tc)
            anvander_bench_boost = (gw == valda_bb)
            
            tillgangliga_byten = 1 + sparade_byten

            if gw > 1 and len(for_ra_trupp) > 0 and not anvander_wildcard and not anvander_free_hit:
                byten = pulp.LpVariable.dicts(f"byte_{gw}", list(for_ra_trupp), cat='Binary')
                for s in for_ra_trupp:
                    prob += byten[s] >= 1 - x[s]
                
                antal_byten = pulp.lpSum([byten[s] for s in for_ra_trupp])
                prob += antal_byten <= tillgangliga_byten

            kapten_multiplikator = 3.0 if anvander_triple_captain else 2.0
            
            if anvander_bench_boost:
                prob += pulp.lpSum([omgangs_index[s] * x[s] for s in spelar_lista]) + pulp.lpSum([omgangs_index[s] * (kapten_multiplikator - 1.0) * c[s] for s in spelar_lista])
            else:
                prob += pulp.lpSum([omgangs_index[s] * y[s] for s in spelar_lista]) + pulp.lpSum([omgangs_index[s] * (kapten_multiplikator - 1.0) * c[s] for s in spelar_lista])
            
            prob += pulp.lpSum([x[s] for s in spelar_lista]) == 15
            prob += pulp.lpSum([x[s] for s in spelar_lista if positioner[s] == 'GK']) == 2
            prob += pulp.lpSum([x[s] for s in spelar_lista if positioner[s] == 'DEF']) == 5
            prob += pulp.lpSum([x[s] for s in spelar_lista if positioner[s] == 'MID']) == 5
            prob += pulp.lpSum([x[s] for s in spelar_lista if positioner[s] == 'FWD']) == 3
            prob += pulp.lpSum([pris[s] * x[s] for s in spelar_lista]) <= 100.0
            
            for l in set(lag.values()):
                prob += pulp.lpSum([x[s] for s in spelar_lista if lag[s] == l]) <= 3

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

                if gw > 1 and len(for_ra_trupp) > 0 and not anvander_wildcard and not anvander_free_hit:
                    faktiska_byten = len(nuvarande_trupp - for_ra_trupp)
                    anvanda_av_bank = min(tillgangliga_byten, faktiska_byten)
                    kvar_i_banken = tillgangliga_byten - anvanda_av_bank
                    sparade_byten = min(2, kvar_i_banken)
                elif anvander_wildcard or anvander_free_hit:
                    sparade_byten = 0

                if anvander_bench_boost:
                    beraknad_poang = sum(omgangs_index[s] for s in nuvarande_trupp) + ((kapten_multiplikator - 1.0) * omgangs_index[kapten] if kapten else 0)
                else:
                    beraknad_poang = sum(omgangs_index[s] for s in startelva) + ((kapten_multiplikator - 1.0) * omgangs_index[kapten] if kapten else 0)

                f.write(f"## 🏆 Gameweek {gw}")
                if anvander_wildcard:
                    f.write(" ⚡ **[WILDCARD AKTIVERAT!]**")
                if anvander_free_hit:
                    f.write(" 🎯 **[FREE HIT AKTIVERAT!]**")
                if anvander_triple_captain:
                    f.write(" 🔥 **[TRIPLE CAPTAIN AKTIVERAT!]**")
                if anvander_bench_boost:
                    f.write(" 🚀 **[BENCH BOOST AKTIVERAT!]**")
                f.write("\n")
                
                if gw > 1 and not anvander_wildcard and not anvander_free_hit:
                    f.write(f"*Gjorda byten: {faktiska_byten} | Sparade byten till nästa omgång: {sparade_byten}*\n")
                elif not gw > 1:
                    f.write(f"*Sparade byten till nästa omgång: {sparade_byten}*\n")
                
                f.write(f"📈 **Förväntad poäng:** `{beraknad_poang:.1f} poäng`\n\n")
                
                f.write("### ⚽ Startelva\n")
                f.write("| Spelare | Lag | Motstånd | Pos | Pris | Index |\n")
                f.write("|---|---|---|---|---|---|\n")
                for pos in ['GK', 'DEF', 'MID', 'FWD']:
                    for s in sorted(list(startelva)):
                        if positioner[s] == pos:
                            kapten_mark = f" ((C - {int(kapten_multiplikator)}x))" if s == kapten else ""
                            t_id = lag_id[s]
                            motstandare = omgang_matcher.get(gw, {}).get(t_id, "Spelar ej")
                            f.write(f"| {s}{kapten_mark} | {lag[s]} | {motstandare} | {pos} | {pris[s]}M | {omgangs_index[s]:.1f} |\n")
                
                f.write("\n### 🛋️ Avbytare\n")
                f.write("| Spelare | Lag | Motstånd | Pos | Pris | Index |\n")
                f.write("|---|---|---|---|---|---|\n")
                for pos in ['GK', 'DEF', 'MID', 'FWD']:
                    for s in sorted(list(banken)):
                        if positioner[s] == pos:
                            t_id = lag_id[s]
                            motstandare = omgang_matcher.get(gw, {}).get(t_id, "Spelar ej")
                            f.write(f"| {s} | {lag[s]} | {motstandare} | {pos} | {pris[s]}M | {omgangs_index[s]:.1f} |\n")
                
                if not anvander_free_hit:
                    for_ra_trupp = nuvarande_trupp
                f.write("\n---\n\n")

if __name__ == "__main__":
    optimera_fpl_med_chips()

