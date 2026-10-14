import streamlit as st
import requests
import pandas as pd
import pulp

st.set_page_config(page_title="Min Personliga FPL AI", page_icon="🏆", layout="wide")

st.title("🏆 Min Personliga FPL AI")
st.markdown("Din smarta FPL-assistent med avancerad optimering för startelva och kaptensval!")

# --- 1. HÄMTA FPL-DATA ---
@st.cache_data(ttl=1800)
def fetch_fpl_data():
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    r = requests.get(url).json()
    
    events = pd.DataFrame(r['events'])
    next_gw_row = events[events['is_next'] == True]
    if not next_gw_row.empty:
        next_gw = int(next_gw_row.iloc[0]['id'])
    else:
        curr_gw_row = events[events['is_current'] == True]
        next_gw = int(curr_gw_row.iloc[0]['id']) + 1 if not curr_gw_row.empty else 1

    teams = {t['id']: t['short_name'] for t in r['teams']}
    
    elements = pd.DataFrame(r['elements'])
    elements['team_name'] = elements['team'].map(teams)
    elements['price'] = elements['now_cost'] / 10.0
    elements['ep_next'] = pd.to_numeric(elements['ep_next'], errors='coerce').fillna(0.0)
    elements['form'] = pd.to_numeric(elements['form'], errors='coerce').fillna(0.0)
    elements['points_per_game'] = pd.to_numeric(elements['points_per_game'], errors='coerce').fillna(0.0)
    
    # AI-viktad xP
    elements['ai_xp'] = (elements['ep_next'] * 0.65) + (elements['form'] * 0.20) + (elements['points_per_game'] * 0.15)
    elements.loc[elements['chance_of_playing_next_round'] == 0, 'ai_xp'] = 0.0
    
    pos_map = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}
    elements['pos'] = elements['element_type'].map(pos_map)
    
    return elements, next_gw

def fetch_user_squad(manager_id, gw):
    for check_gw in range(gw - 1, 0, -1):
        url = f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{check_gw}/picks/"
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            picks = [p['element'] for p in data['picks']]
            bank = data['entry_history']['bank'] / 10.0
            return picks, bank, check_gw
    return None, 0.0, None

df, next_gw = fetch_fpl_data()

# --- 2. ANVÄNDARINPUT ---
manager_id = st.text_input("Ange ditt FPL-ID:", value="", placeholder="T.exo 123456")

free_transfers = 1
allow_hits = "Strikt max 1 byte (0 minuspoäng)"
extra_bank = 0.0

squad_ids = []
bank_balance = extra_bank

if manager_id.isdigit():
    loaded_ids, api_bank, found_gw = fetch_user_squad(int(manager_id), next_gw)
    if loaded_ids:
        squad_ids = loaded_ids
        bank_balance = api_bank
        st.success(f"✅ Laddade trupp från GW {found_gw}!")
    else:
        st.error("Kunde inte hitta truppen för det ID:t.")

if st.button("Hämta och optimera min trupp", type="primary") and len(squad_ids) == 15:
    
    max_transfers_allowed = free_transfers
    
    prob = pulp.LpProblem("FPL_Optimizer", pulp.LpMaximize)
    players = df['id'].tolist()
    player_data = df.set_index('id').to_dict('index')
    
    in_squad = pulp.LpVariable.dicts("squad", players, cat="Binary")
    starter = pulp.LpVariable.dicts("starter", players, cat="Binary")
    captain = pulp.LpVariable.dicts("captain", players, cat="Binary")
    vice_captain = pulp.LpVariable.dicts("vice", players, cat="Binary")
    transfer_in = pulp.LpVariable.dicts("trans_in", players, cat="Binary")
    transfer_out = pulp.LpVariable.dicts("trans_out", players, cat="Binary")
    
    # Fastställd variabelhantering som inte kraschar
    hits_taken = pulp.LpVariable("hits", lowBound=0, upBound=12, cat="Integer")
    
    current_squad_value = sum(player_data[p]['price'] for p in squad_ids)
    total_budget = current_squad_value + bank_balance
    
    prob += (
        pulp.lpSum(player_data[p]['ai_xp'] * starter[p] for p in players) +
        pulp.lpSum(player_data[p]['ai_xp'] * captain[p] for p in players) -
        (4.0 * hits_taken)
    )
    
    prob += pulp.lpSum(in_squad[p] for p in players) == 15
    prob += pulp.lpSum(starter[p] for p in players) == 11
    prob += pulp.lpSum(captain[p] for p in players) == 1
    prob += pulp.lpSum(vice_captain[p] for p in players) == 1
    prob += pulp.lpSum(player_data[p]['price'] * in_squad[p] for p in players) <= total_budget
    
    for p in players:
        prob += starter[p] <= in_squad[p]
        prob += captain[p] <= starter[p]
        prob += vice_captain[p] <= starter[p]
        prob += captain[p] + vice_captain[p] <= 1
        if p in squad_ids:
            prob += transfer_out[p] == 1 - in_squad[p]
            prob += transfer_in[p] == 0
        else:
            prob += transfer_in[p] == in_squad[p]
            prob += transfer_out[p] == 0

    gkp = [p for p in players if player_data[p]['element_type'] == 1]
    defs = [p for p in players if player_data[p]['element_type'] == 2]
    mids = [p for p in players if player_data[p]['element_type'] == 3]
    fwds = [p for p in players if player_data[p]['element_type'] == 4]
    
    prob += pulp.lpSum(in_squad[p] for p in gkp) == 2
    prob += pulp.lpSum(in_squad[p] for p in defs) == 5
    prob += pulp.lpSum(in_squad[p] for p in mids) == 5
    prob += pulp.lpSum(in_squad[p] for p in fwds) == 3
    
    prob += pulp.lpSum(starter[p] for p in gkp) == 1
    prob += pulp.lpSum(starter[p] for p in defs) >= 3
    prob += pulp.lpSum(starter[p] for p in mids) >= 2
    prob += pulp.lpSum(starter[p] for p in fwds) >= 1
    
    for team_id in df['team'].unique():
        team_players = [p for p in players if player_data[p]['team'] == team_id]
        prob += pulp.lpSum(in_squad[p] for p in team_players) <= 3
        
    total_transfers = pulp.lpSum(transfer_in[p] for p in players)
    prob += total_transfers <= max_transfers_allowed
    prob += hits_taken >= total_transfers - free_transfers
    
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    bought = [p for p in players if pulp.value(transfer_in[p]) > 0.5]
    sold = [p for p in players if pulp.value(transfer_out[p]) > 0.5]
    
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔄 Veckans Byte")
        if not bought:
            st.info("💡 Spara ditt byte! Truppen är optimal.")
        else:
            for s, b in zip(sold, bought):
                s_inf, b_inf = player_data[s], player_data[b]
                st.markdown(f"🔴 **UT:** {s_inf['web_name']} (£{s_inf['price']}m)\n\n🟢 **IN:** **{b_inf['web_name']}** (£{b_inf['price']}m)")

    with col2:
        cap_id = [p for p in players if pulp.value(captain[p]) > 0.5][0]
        total_xp = pulp.value(prob.objective)
        st.subheader("👑 Kaptensval")
        st.metric("Förväntad poäng", f"{total_xp:.1f} p")
        st.markdown(f"🥇 **Kapten:** **{player_data[cap_id]['web_name']}**")

    st.subheader("🏟️ Startelva")
    starters = [p for p in players if pulp.value(starter[p]) > 0.5]
    s_df = pd.DataFrame([player_data[p] for p in starters])
    s_df['Roll'] = s_df['web_name'].apply(lambda x: "👑 Kapten" if x == player_data[cap_id]['web_name'] else "Start")
    st.dataframe(s_df[['pos', 'web_name', 'team_name', 'price', 'ai_xp', 'Roll']], use_container_width=True, hide_index=True)

elif len(squad_ids) != 15 and manager_id.isdigit():
    st.warning("Ange ett giltigt FPL-ID så truppen kan hämtas.")
