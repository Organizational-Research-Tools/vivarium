
import pandas as pd

df = pd.read_csv('records.csv')

# Look at panel means per prototype
panels = df[df['kind'] == 'qualification'].groupby(['project', 'prototype_id', 'test']).agg(
    mean_value=('value', 'mean'),
    count=('value', 'count')
).reset_index()

print(panels.to_string())
