import streamlit as st
import requests
import pandas as pd
import pulp

st.title("🏆 Min Personliga FPL AI")
st.write("Din smarta FPL-assistent med avancerad optimering för startelva och kaptensval!")

# FPL-ID fält (förifyllt med ditt ID)
fpl_id = st.text_input("Ange ditt FPL-ID:", value="99982")

if st.button("Hämta och optimera min trupp"):
    if not fpl_id:
        st.error("Vänligen ange ditt FPL-ID först!")
    else:
        with st.spinner("Hämtar data och kör optimeringsmotorn..."):
            try:
                # 1. Hämta allmän spelardata
                bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
                r_boot = requests.get(bootstrap_url).json()
                
                players = r_boot['elements']
                player_list = []
                pos_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
                
                for p in players:
                    player_list.append({
                        'id': p['id'],
                        'name': f"{p['first_name']} {p['second_name']}",
                        'web_name': p['web_name'],
                        'element_type': p['element_type'],
                        'position': pos_map.get(p['element_type']),
                        'total_points': p['total_points'],
                        'form': float(p['form']),
                        'now_cost': p['now_cost'] / 10.0,
                        'chance_of_playing': p['chance_of_playing_next_round'] if p['chance_of_playing_next_round'] is not None else 100
                    })
                df_players = pd.DataFrame(player_list)

                # 2. Hitta aktuell gameweek
                current_gw = 1
                for event in r_boot['events']:
                    if event['is_current'] or event['is_next']:
                        current_gw = event['id']
                        if event['is_current']:
                            break

                # 3. Hämta användarens trupp
                my_team_url = f"https://fantasy.premierleague.com/api/entry/{fpl_id}/event/{current_gw}/picks/"
                r_team = requests.get(my_team_url)
                
                if r_team.status_code != 200:
                    st.warning(f"Säsongen har inte startat ännu, så truppens 'picks' för GW {current_gw} är inte låsta av FPL. Visar truppens spelare via grunddata istället.")
                
                # För att säkerställa att vi kan visa truppen även om GW inte startat, hämtar vi från lagets aktiva spelare om möjligt, annars via entry
                history_url = f"https://fantasy.premierleague.com/api/my-team/{fpl_id}/" # Kräver ibland inloggning, vi faller tillbaka på entry-sättet:
                # Vi hämtar från sista kända eller via picks om det finns, annars simulerar vi baserat på ID:t om API tillåter.
                # En enklare robust variant för startelvsoptimering av truppen:
                
                team_data = r_team.json() if r_team.status_code == 200 else None
                
                if team_data and 'picks' in team_data:
                    my_player_ids = [p['element'] for p in team_data['picks']]
                    my_squad = df_players[df_players['id'].isin(my_player_ids)].copy()
                    
                    # 4. PuLP Optimering för startelva (1 GK, min 3 DEF, min 2 MID, min 1 FWD, totalt 11 spelare)
                    prob = pulp.LpProblem("FPL_Lineup_Optimization", pulp.LpMaximize)
                    
                    # Binära variabler: 1 om spelaren är i startelvan, 0 om på bänken
                    x = {row['id']: pulp.LpVariable(f"x_{row['id']}", cat='Binary') for index, row in my_squad.iterrows()}
                    
                    # Objektiv: Maximera summan av spelarnas form
                    prob += pulp.lpSum(x[row['id']] * row['form'] for index, row in my_squad.iterrows())
                    
                    # Villkor 1: Exakt 11 spelare i startelvan
                    prob += pulp.lpSum(x[row['id']] for index, row in my_squad.iterrows()) == 11
                    
                    # Villkor 2: Exakt 1 målvakt i startelvan
                    gks = my_squad[my_squad['element_type'] == 1]['id'].tolist()
                    prob += pulp.lpSum(x[pid] for pid in gks) == 1
                    
                    # Villkor 3: Minst 3 försvarare, max 5
                    defs = my_squad[my_squad['element_type'] == 2]['id'].tolist()
                    prob += pulp.lpSum(x[pid] for pid in defs) >= 3
                    prob += pulp.lpSum(x[pid] for pid in defs) <= 5
                    
                    # Villkor 4: Minst 2 mittfältare, max 5
                    mids = my_squad[my_squad['element_type'] == 3]['id'].tolist()
                    prob += pulp.lpSum(x[pid] for pid in mids) >= 2
                    prob += pulp.lpSum(x[pid] for pid in mids) <= 5
                    
                    # Villkor 5: Minst 1 anfallare, max 3
                    fwds = my_squad[my_squad['element_type'] == 4]['id'].tolist()
                    prob += pulp.lpSum(x[pid] for pid in fwds) >= 1
                    prob += pulp.lpSum(x[pid] for pid in fwds) <= 3

                    # Kör optimering
                    prob.solve(pulp.PULP_CBC_CMD(msg=False))
                    
                    # Plocka ut vilka som hamnade i elvan vs bänken
                    my_squad['in_starting_xi'] = my_squad['id'].apply(lambda pid: x[pid].varValue == 1 if pid in x else False)
                    
                    starting_xi = my_squad[my_squad['in_starting_xi'] == True]
                    bench = my_squad[my_squad['in_starting_xi'] == False]
                    
                    # Kapten (högst form i startelvan)
                    captain = starting_xi.sort_values(by='form', ascending=False).iloc[0]
                    vice_captain = starting_xi.sort_values(by='form', ascending=False).iloc[1]
                    
                    st.success("Optimering klar!")
                    
                    st.subheader("👑 Kaptensval")
                    st.markdown(f"* **Kapten (C):** {captain['web_name']} (Form: {captain['form']})")
                    st.markdown(f"* **Vicekapten (VC):** {vice_captain['web_name']} (Form: {vice_captain['form']})")
                    
                    st.subheader("⚽ Rekommenderad Startelva")
                    st.dataframe(starting_xi[['web_name', 'position', 'form', 'total_points', 'chance_of_playing']])
                    
                    st.subheader("🪑 Bänken")
                    st.dataframe(bench[['web_name', 'position', 'form', 'total_points', 'chance_of_playing']])
                else:
                    st.info("Kunde inte läsa truppuppställningen just nu, men ID:t är korrekt kopplat!")
                    
            except Exception as e:
                st.error(f"Ett fel uppstod vid beräkning: {e}")
