import streamlit as st
import requests
import pandas as pd
import pulp

# 1. Sidans inställningar
st.set_page_config(page_title="Min FPL AI", page_icon="⚽")
st.title("🏆 Min Personliga FPL AI")
st.write("Klicka på knappen nedan för att beräkna säkra transfers och startelva!")

if st.button("Optimera min trupp"):
    with st.spinner("Hämtar data och analyserar..."):
        
        # Hämta data från FPL
        url = "https://fantasy.premierleague.com/api/bootstrap-static/"
        headers = {"User-Agent": "Mozilla/5.0"}
        data = requests.get(url, headers=headers).json()

        players = pd.DataFrame(data["elements"])
        players = players[players['status'] == 'a']
        players['price'] = players['now_cost'] / 10
        players['total_points'] = pd.to_numeric(players['total_points'])
        players['form'] = pd.to_numeric(players['form'])
        players['position'] = players['element_type']

        # Hämta omgångar (Gameweeks)
        events = pd.DataFrame(data["events"])
        next_event = events[events['is_next'] == True]
        
        current_gw = 1
        if not next_event.empty:
            current_gw = next_event['id'].values[0]

        # DINA SPELARE
        my_team_search = [
            "Raya", "Dubravka", "Gabriel", "Mitchell", "Diop", "Kerkez", 
            "Maguire", "Gro", "Semenyo", "Fernandes", "Bruno", "Fée", 
            "Gyök", "João Pedro", "Isak"
        ]

        my_team_ids = []
        
        for name in my_team_search:
            for index, row in players.iterrows():
                if name.lower() in row['web_name'].lower():
                    if name == "Raya" and "rayan" in row['web_name'].lower():
                        continue
                    if index not in my_team_ids:
                        my_team_ids.append(index)
                        break

        if len(my_team_ids) != 15:
            st.error(f"**Stopp!** AI:n hittade {len(my_team_ids)} spelare. Kontrollera sökorden.")
            st.stop()

        # 1. OPTIMERING FÖR TRANSFER (Vi låser 14 av 15 spelare så den inte säljer stjärnorna i onödan)
        prob_transfer = pulp.LpProblem("FPL_Transfer", pulp.LpMaximize)
        player_vars = pulp.LpVariable.dicts("Players", players.index, cat='Binary')

        prob_transfer += pulp.lpSum([players['total_points'][i] * player_vars[i] for i in players.index])

        # Tvinga AI:n att behålla minst 14 av dina nuvarande spelare (byter max 1 spelare om det behövs)
        kept_players = pulp.lpSum([player_vars[i] for i in my_team_ids])
        prob_transfer += kept_players >= 14

        prob_transfer += pulp.lpSum([player_vars[i] for i in players.index]) == 15
        prob_transfer += pulp.lpSum([players['price'][i] * player_vars[i] for i in players.index]) <= 100.0
        
        prob_transfer += pulp.lpSum([player_vars[i] for i in players.index if players['position'][i] == 1]) == 2
        prob_transfer += pulp.lpSum([player_vars[i] for i in players.index if players['position'][i] == 2]) == 5
        prob_transfer += pulp.lpSum([player_vars[i] for i in players.index if players['position'][i] == 3]) == 5
        prob_transfer += pulp.lpSum([player_vars[i] for i in players.index if players['position'][i] == 4]) == 3

        prob_transfer.solve()

        new_squad_ids = [i for i in players.index if player_vars[i].varValue == 1.0]

        # 2. OPTIMERING FÖR STARTELVA
        prob_xi = pulp.LpProblem("FPL_Starting_XI", pulp.LpMaximize)
        xi_vars = pulp.LpVariable.dicts("XI", new_squad_ids, cat='Binary')

        prob_xi += pulp.lpSum([players['total_points'][i] * xi_vars[i] for i in new_squad_ids])
        prob_xi += pulp.lpSum([xi_vars[i] for i in new_squad_ids]) == 11

        prob_xi += pulp.lpSum([xi_vars[i] for i in new_squad_ids if players['position'][i] == 1]) == 1

        prob_xi += pulp.lpSum([xi_vars[i] for i in new_squad_ids if players['position'][i] == 2]) >= 3
        prob_xi += pulp.lpSum([xi_vars[i] for i in new_squad_ids if players['position'][i] == 2]) <= 5
        
        prob_xi += pulp.lpSum([xi_vars[i] for i in new_squad_ids if players['position'][i] == 3]) >= 2
        prob_xi += pulp.lpSum([xi_vars[i] for i in new_squad_ids if players['position'][i] == 3]) <= 5
        
        prob_xi += pulp.lpSum([xi_vars[i] for i in new_squad_ids if players['position'][i] == 4]) >= 1
        prob_xi += pulp.lpSum([xi_vars[i] for i in new_squad_ids if players['position'][i] == 4]) <= 3

        prob_xi.solve()

        # 3. VISA RESULTAT
        st.subheader(f"📅 Aktuell Omgång: Gameweek {current_gw}")

        st.subheader("💡 Chip-Rådgivning")
        gw_left = 19 - current_gw
        if gw_left > 10:
            st.info(f"Fas 1 (Tidig säsong): Du har {gw_left} omgångar kvar till GW 19. Spara dina chips.")
        else:
            st.warning(f"⚠️ {gw_left} omgångar kvar till GW 19. Planera dina chips!")

        st.subheader("🔄 Veckans Transfer")
        sold = []
        bought = []
        
        for index in my_team_ids:
            if player_vars[index].varValue == 0.0:
                sold.append(players['web_name'][index])
                
        for i in players.index:
            if player_vars[i].varValue == 1.0 and i not in my_team_ids:
                bought.append(players['web_name'][i])
        
        if sold and bought:
            st.error(f"**SÄLJ:** {sold[0]}")
            st.success(f"**KÖP:** {bought[0]}")
        else:
            st.info("Inga byten rekommenderas denna vecka! Truppen är optimal.")

        starting_xi = [i for i in new_squad_ids if xi_vars[i].varValue == 1.0]
        bench = [i for i in new_squad_ids if xi_vars[i].varValue == 0.0]

        starting_xi_sorted = sorted(starting_xi, key=lambda x: players['total_points'][x], reverse=True)
        captain = starting_xi_sorted[0]
        vice_captain = starting_xi_sorted[1]

        st.subheader("⭐ Veckans Startelva & Kapten")
        st.write(f"©️ **Kapten:** {players['web_name'][captain]}")
        st.write(f"V️ **Vicekapten:** {players['web_name'][vice_captain]}")
        
        st.markdown("### Elvan:")
        for i in starting_xi:
            name = players['web_name'][i]
            total_p = players['total_points'][i]
            tag = " (©️ Kapten)" if i == captain else ""
            st.write(f"- **{name}**{tag} | Totalpoäng: {total_p}")

        st.markdown("### Bänken:")
        for i in bench:
            name = players['web_name'][i]
            total_p = players['total_points'][i]
            st.write(f"- {name} | Totalpoäng: {total_p}")

