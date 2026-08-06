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

                # 3. Hämta användarens trupp (Försök via omgångens picks först)
                my_team_url = f"https://fantasy.premierleague.com/api/entry/{fpl_id}/event/{current_gw}/picks/"
                r_team = requests.get(my_team_url)
                
                my_player_ids = []
                if r_team.status_code == 200:
                    team_data = r_team.json()
                    if 'picks' in team_data:
                        my_player_ids = [p['element'] for p in team_data['picks']]
                
                # Om picks inte finns (för att säsongen inte startat), hämta via transfers/current (eller liknande endpoint)
                if not my_player_ids:
                    transfers_url = f"https://fantasy.premierleague.com/api/my-team/{fpl_id}/"
                    r_transfers = requests.get(transfers_url)
                    if r_transfers.status_code == 200:
                        transfer_data = r_transfers.json()
                        if 'picks' in transfer_data:
                            my_player_ids = [p['element'] for p in transfer_data['picks']]

                # Om vi fortfarande inte hittar via my-team (pga inloggningskrav), simulerar vi en trupp eller hämtar via en alternativ öppen vy om möjligt. 
                # Men för att säkra att appen inte kraschar skapar vi en fallback på spelare om listan är tom:
                if not my_player_ids:
                    # Fallback om API kräver inloggning för my-team innan start: plocka några spelare baserat på ID eller visa meddelande
                    st.warning("FPL-API:et döljer truppen helt publikt innan GW1 har låst sig. Så fort den första deadlinen passerar kommer dina exakta spelare att visas automatiskt!")
                else:
                    my_squad = df_players[df_players['id'].isin(my_player_ids)].copy()
                    
                    # 4. PuLP Optimering för startelva
                    prob = pulp.LpProblem("FPL_Lineup_Optimization", pulp.LpMaximize)
                    
                    x = {row['id']: pulp.LpVariable(f"x_{row['id']}", cat='Binary') for index, row in my_squad.iterrows()}
                    
                    prob += pulp.lpSum(x[row['id']] * row['form'] for index, row in my_squad.iterrows())
                    
                    prob += pulp.lpSum(x[row['id']] for index, row in my_squad.iterrows()) == 11
                    
                    gks = my_squad[my_squad['element_type'] == 1]['id'].tolist()
                    prob += pulp.lpSum(x[pid] for pid in gks) == 1
                    
                    defs = my_squad[my_squad['element_type'] == 2]['id'].tolist()
                    prob += pulp.lpSum(x[pid] for pid in defs) >= 3
                    prob += pulp.lpSum(x[pid] for pid in defs) <= 5
                    
                    mids = my_squad[my_squad['element_type'] == 3]['id'].tolist()
                    prob += pulp.lpSum(x[pid] for pid in mids) >= 2
                    prob += pulp.lpSum(x[pid] for pid in mids) <= 5
                    
                    fwds = my_squad[my_squad['element_type'] == 4]['id'].tolist()
                    prob += pulp.lpSum(x[pid] for pid in fwds) >= 1
                    prob += pulp.lpSum(x[pid] for pid in fwds) <= 3

                    prob.solve(pulp.PULP_CBC_CMD(msg=False))
                    
                    my_squad['in_starting_xi'] = my_squad['id'].apply(lambda pid: x[pid].varValue == 1 if pid in x else False)
                    
                    starting_xi = my_squad[my_squad['in_starting_xi'] == True]
                    bench = my_squad[my_squad['in_starting_xi'] == False]
                    
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
                    
            except Exception as e:
                st.error(f"Ett fel uppstod vid beräkning: {e}")
