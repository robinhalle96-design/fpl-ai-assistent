
import requests

# --- DINA INSTÄLLNINGAR ---
MANAGER_ID = 99982
# Eftersom säsongen precis börjar kikar vi på Gameweek 1
CURRENT_GW = 1 

def get_my_team(manager_id, gw):
    print(f"Hämtar truppen för Manager ID {manager_id} (GW {gw})...")
    url = f"https://fantasy.premierleague.com/api/entry/{manager_id}/event/{gw}/picks/"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print("❌ Kunde inte hämta laget. Är du säker på att omgången har startat och ID:t stämmer?")
        return []
        
    data = response.json()
    
    # Plockar ut spelarnas unika ID-nummer
    my_players = [pick['element'] for pick in data['picks']]
    return my_players

# Testkör funktionen
my_current_team_ids = get_my_team(MANAGER_ID, CURRENT_GW)
print(f"✅ Din trupp hämtad! Här är dina spelares ID-nummer: {my_current_team_ids}")
