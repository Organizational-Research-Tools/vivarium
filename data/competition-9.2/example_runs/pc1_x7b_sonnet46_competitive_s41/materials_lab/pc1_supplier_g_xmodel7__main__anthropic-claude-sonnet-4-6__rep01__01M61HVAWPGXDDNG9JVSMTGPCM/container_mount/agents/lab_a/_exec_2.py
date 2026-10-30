
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

# Get panel-level means per prototype per test
panels = df[df['kind'] == 'qualification'].groupby(['project', 'prototype_id', 'test'])['value'].mean().reset_index()
panels.columns = ['project', 'prototype_id', 'test', 'mean']

# Pivot to wide format
panels_wide = panels.pivot_table(index=['project', 'prototype_id'], columns='test', values='mean').reset_index()
print(panels_wide.to_string())
