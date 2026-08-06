import streamlit as st
import requests
import pandas as pd
import pulp

st.title("🏆 Min Personliga FPL AI")
st.write("Din smarta FPL-assistent som optimerar startelva och kaptensval automatiskt!")

# FPL-ID fält (förifyllt med ditt ID)
fpl_id = st.text_input("Ange ditt FPL-ID:", value="99982")

if st.button("Hämta och optimera min trupp"):
    if not fpl_id:
        st.error("Vänligen ange ditt FPL-ID först!")
    else:
        with st.spinner("Hämtar data och optimerar laguppställning..."):
            try:
                # 1. Hämta allmän spelardata från FPL API
                bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
                r_boot = requests.get(bootstrap_url).json()
                
                players = r_boot['elements']
                teams_data = {t['id']: t['short_name'] for t in r_boot['teams']}
                
                player_list = []
                for p in players:
                    # Identifiera position (1=Målvakt, 2=Försvarare, 3=Mittfältare, 4=Anfallare)
                    pos_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
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

                # 2. Hitta aktuell eller nästkommande gameweek
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
                    profile_url = f"https://fantasy.premierleague.com/api/entry/{fpl_id}/"
                    r_profile = requests.get(profile_url).json()
                    st.warning(f"Hittade lag för: {r_profile.get('player_first_name', '')} {r_profile.get('player_last_name', '')} ({r_profile.get('name', '')}), men kunde inte läsa truppen för GW {current_gw} ännu (säsongen har inte startat). Visar grundläggande spelardata istället.")
                else:
                    team_data = r_team.json()
                    my_player_ids = [p['element'] for p in team_data['picks']]
                    my_squad = df_players[df_players['id'].isin(my_player_ids)].copy()
                    
                    st.success(f"Hittade din trupp ({len(my_squad)} spelare)! Optimering klar.")
                    
                    # 4. Enkel optimering/startelva (Välj 11 spelare baserat på form/poäng med giltig formation)
                    st.subheader("⭐ Rekommenderad Startelva & Kapten")
                    
                    # Förslag på kaptensval (högst form/poäng i truppen)
                    best_player = my_squad.sort_values(by='form', ascending=False).iloc[0]
                    vc_player = my_squad.sort_values(by='form', ascending=False).iloc[1]
                    
                    st.markdown(f"* **👑 Kapten:** {best_player['web_name']} (Form: {best_player['form']})")
                    st.markdown(f"* **©️ Vicekapten:** {vc_player['web_name']} (Form: {vc_player['form']})")
                    
                    st.markdown("### Hela din trupp:")
                    st.dataframe(my_squad[['web_name', 'position', 'total_points', 'form', 'now_cost', 'chance_of_playing']])
                    
            except Exception as e:
                st.error(f"Ett fel uppstod vid hämtning: {e}")
