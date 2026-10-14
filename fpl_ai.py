import streamlit as st
import requests
import pandas as pd
import pulp

st.set_page_config(page_title="Min Personliga FPL AI", page_icon="🏆", layout="wide")

st.title("🏆 Min Personliga FPL AI")
st.markdown("Din smarta FPL-assistent med avancerad optimering för startelva och kaptensval!")

@st.cache_data(ttl=1800)
def fetch_fpl_data():
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    r = requests.get(url).json()
    events = pd.DataFrame(r['events'])
    next_gw = events[events['is_next'] == True]
    if not next_gw.empty:
        next_gw_id = next_gw.iloc[0]['id']
    else:
        next_gw_id = 1
    
    elements = pd.DataFrame(r['elements'])
    teams = pd.DataFrame(r['teams'])
    return elements, teams, next_gw_id

elements, teams, next_gw_id = fetch_fpl_data()

st.sidebar.header("Dina inställningar")
manager_id = st.sidebar.text_input("FPL Manager ID", value="99982")
free_transfers = st.sidebar.number_input("Antal fria byten", min_value=0, max_value=5, value=1)

if st.button("Hämta och optimera min trupp"):
    if not manager_id:
        st.error("Vänligen ange ditt FPL Manager ID.")
    else:
        try:
            picks_url = f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{next_gw_id}/picks/"
            picks_res = requests.get(picks_url)
            
            if picks_res.status_code != 200:
                picks_url = f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{next_gw_id - 1}/picks/"
                picks_res = requests.get(picks_url)
            
            picks_data = picks_res.json()
            squad_ids = [p['element'] for p in picks_data['picks']]
            
            st.success(f"Laddade trupp från GW {next_gw_id}!")
            
            df = elements[elements['id'].isin(squad_ids)].copy()
            
            if len(squad_ids) == 15:
                prob = pulp.LpProblem("FPL_Optimizer", pulp.LpMaximize)
                players = df['id'].tolist()
                player_data = df.set_index('id').to_dict('index')
                
                in_spec = {}
                starter = {}
                for p in players:
                    in_spec[p] = pulp.LpVariable(f"squad_{p}", 0, 1, pulp.LpInteger)
                    starter[p] = pulp.LpVariable(f"starter_{p}", 0, 1, pulp.LpInteger)
                
                prob += pulp.lpSum(float(player_data[p].get('ep_next', 0)) * starter[p] for p in players)
                
                prob += pulp.lpSum(starter[p] for p in players) == 11
                prob += pulp.lpSum(in_spec[p] for p in players) == 15
                
                prob.solve(pulp.PULP_CBC_CMD(msg=False))
                
                st.subheader("Optimerad Startelva")
                optimized_players = []
                for p in players:
                    if starter[p].varValue == 1:
                        optimized_players.append(player_data[p]['web_name'])
                
                st.write(optimized_players)
            else:
                st.error("Kunde inte verifiera 15 spelare i truppen.")
                
        except Exception as err:
            st.error(f"Ett fel uppstod: {err}")
