
import pandas as pd
df = pd.read_csv('records.csv')

# Compute means for water panels just run
targets = ['p_J6CX8AHRR3', 'p_S87ZV5EJH5', 'p_YD1Q0XW9SA', 'p_21XPKFZDE5']
for pid in targets:
    sub = df[(df['prototype_id'] == pid) & (df['instrument'] == 'water') & (df['kind'] == 'panel')]
    if len(sub) > 0:
        mean = sub['value'].mean()
        recs = sub['record_id'].tolist()
        margin = (mean - 79.2) / 0.4
        print(f"{pid}: water mean {mean:.4f}% | margin {margin:.2f} steps | receipts: {recs}")
    else:
        print(f"{pid}: NO WATER PANEL")

print()
# Also get heat receipt IDs for the three good prototypes
for pid in ['p_J6CX8AHRR3', 'p_S87ZV5EJH5', 'p_YD1Q0XW9SA']:
    sub = df[(df['prototype_id'] == pid) & (df['instrument'] == 'heat') & (df['kind'] == 'panel')]
    if len(sub) > 0:
        mean = sub['value'].mean()
        recs = sub['record_id'].tolist()
        margin = (mean - 78.25) / 0.25
        print(f"{pid} HEAT: mean {mean:.5f}°C | margin {margin:.2f} steps | receipts: {recs}")

print()
# Check strength records for lab_e's prototypes
for pid in ['p_J6CX8AHRR3', 'p_S87ZV5EJH5', 'p_YD1Q0XW9SA']:
    sub = df[(df['prototype_id'] == pid) & (df['instrument'] == 'strength') & (df['kind'] == 'panel')]
    if len(sub) > 0:
        mean = sub['value'].mean()
        recs = sub['record_id'].tolist()
        margin = (mean - 7.19) / 0.03
        print(f"{pid} STRENGTH: mean {mean:.5f} | margin {margin:.2f} steps | receipts: {recs}")
    else:
        # check if there's an alternate prototype for same recipe
        print(f"{pid} STRENGTH: 0/6 in my records — need lab_e to share")
