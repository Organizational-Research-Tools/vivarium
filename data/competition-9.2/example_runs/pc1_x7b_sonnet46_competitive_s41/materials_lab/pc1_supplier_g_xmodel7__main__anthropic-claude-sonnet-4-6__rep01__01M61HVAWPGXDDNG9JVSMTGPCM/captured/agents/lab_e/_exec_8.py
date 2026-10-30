
import pandas as pd
df = pd.read_csv('records.csv')

# Find panel receipts for our three key prototypes
targets = ['p_02A6NY9WNM', 'p_BZB62TCK50', 'p_2058095Z34']
panels = df[(df['prototype_id'].isin(targets)) & (df['kind'] == 'panel')]
panels = panels[['record_id', 'project_id', 'prototype_id', 'instrument', 'specimen']].sort_values(['prototype_id', 'instrument', 'specimen'])
print(panels.to_string())
