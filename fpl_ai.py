import streamlit as st
import requests
import pandas as pd
import pulp

st.title("🏆 Min Personliga FPL AI")
st.write("Klicka på knappen nedan för att hämta din trupp automatiskt via ditt FPL-ID och beräkna startelva!")

# Fält för att mata in FPL-ID
fpl_id = st.text_input("Ange ditt FPL-ID:", value="")

if st.button("Hämta och optimera min trupp"):
    if not fpl_id:
        st.error("Vänligen ange ditt FPL-ID först!")
    else:
        with st.spinner("Hämtar data från Fantasy Premier League..."):
            try:
                # 1. Hämta spelardata (bootstrap-static) för poäng, pris och namn
                bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
                r_boot = requests.get(bootstrap_url).json()
                
                players = r_boot['elements']
                teams_data = {t['id']: t['name'] for t in r_boot['teams']}
                
                # Skapa en DataFrame med spelare
                player_list = []
                for p in players:
                    player_list.append({
                        'id': p['id'],
                        'name': f"{p['first_name']} {p['second_name']}",
                        'web_name': p['web_name'],
                        'element_type': p['element_type'], # 1=GK, 2=DEF, 3=MID, 4=FWD
                        'total_points': p['total_points'],
                        'now_cost': p['now_cost'] / 10.0,
                        'chance_of_playing': p['chance_of_playing_next_round'] if p['chance_of_playing_next_round'] is not None else 100
                    })
                df_players = pd.DataFrame(player_list)

                # 2. Hämta användarens aktuella lag via FPL-ID (kräver att ligan/laget är publikt)
                # Använder aktuell gameweek, vi hämtar live-picks. För att hitta aktuellGW kan man titta i events.
                current_gw = 1
                for event in r_boot['events']:
                    if event['is_current'] or event['is_next']:
                        # Om säsongen inte startat är is_next nästa, annars is_current
                        current_gw = event['id']
                        if event['is_current']:
                            break
                
                my_team_url = f"https://fantasy.premierleague.com/api/entry/{fpl_id}/event/{current_gw}/picks/"
                r_team = requests.get(my_team_url)
                
                if r_team.status_code != 200:
                    st.error("Kunde inte hämta din trupp. Kontrollera att ditt FPL-ID är korrekt.")
                else:
                    team_data = r_team.json()
                    my_player_ids = [p['element'] for p in team_data['picks']]
                    
                    # Filtrera ut spelarna som är i din trupp
                    my_squad = df_players[df_players['id'].isin(my_player_ids)].copy()
                    
                    st.success(f"Hittade din trupp ({len(my_squad)} spelare)!")
                    
                    # 3. Enkel optimering/visning av startelva (exempel med PuLP eller sortering)
                    st.subheader("⭐ Din Aktiva Trupp")
                    st.dataframe(my_squad[['web_name', 'total_points', 'now_cost', 'chance_of_playing']])
                    
            except Exception as e:
                st.error(f"Ett fel uppstod vid hämtning: {e}")
