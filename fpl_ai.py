import streamlit as st
import requests
import pandas as pd

st.title("🏆 Min Personliga FPL AI")
st.write("Klicka på knappen nedan för att hämta din trupp automatiskt via ditt FPL-ID!")

# Förifyllt med ditt FPL-ID
fpl_id = st.text_input("Ange ditt FPL-ID:", value="99982")

if st.button("Hämta och optimera min trupp"):
    if not fpl_id:
        st.error("Vänligen ange ditt FPL-ID först!")
    else:
        with st.spinner("Hämtar data från Fantasy Premier League..."):
            try:
                # 1. Hämta allmän spelardata
                bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
                r_boot = requests.get(bootstrap_url).json()
                
                players = r_boot['elements']
                player_list = []
                for p in players:
                    player_list.append({
                        'id': p['id'],
                        'name': f"{p['first_name']} {p['second_name']}",
                        'web_name': p['web_name'],
                        'total_points': p['total_points'],
                        'now_cost': p['now_cost'] / 10.0
                    })
                df_players = pd.DataFrame(player_list)

                # 2. Hitta aktuell eller nästkommande gameweek automatiskt
                current_gw = 1
                for event in r_boot['events']:
                    if event['is_current'] or event['is_next']:
                        current_gw = event['id']
                        if event['is_current']:
                            break

                # 3. Hämta truppen för vald gameweek
                my_team_url = f"https://fantasy.premierleague.com/api/entry/{fpl_id}/event/{current_gw}/picks/"
                r_team = requests.get(my_team_url)
                
                if r_team.status_code != 200:
                    # Om aktuell omgång inte har data, testa att hämta från grundprofilen istället
                    profile_url = f"https://fantasy.premierleague.com/api/entry/{fpl_id}/"
                    r_profile = requests.get(profile_url).json()
                    st.warning(f"Hittade lag för: {r_profile.get('player_first_name', '')} {r_profile.get('player_last_name', '')} ({r_profile.get('name', '')}), men kunde inte läsa picks för GW {current_gw} ännu.")
                else:
                    team_data = r_team.json()
                    my_player_ids = [p['element'] for p in team_data['picks']]
                    my_squad = df_players[df_players['id'].isin(my_player_ids)].copy()
                    
                    st.success(f"Hittade din trupp ({len(my_squad)} spelare)!")
                    st.subheader("⭐ Din Aktiva Trupp")
                    st.dataframe(my_squad[['web_name', 'total_points', 'now_cost']])
                    
            except Exception as e:
                st.error(f"Ett fel uppstod vid hämtning: {e}")
