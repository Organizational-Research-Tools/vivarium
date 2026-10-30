
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

print("All kinds:", df['kind'].unique())
print("All tests:", df['test'].unique())
print("All instruments:", df['instrument'].unique())

# Check the filing status records - the "earlier records" mentioned
# These have full panels on all three tests
# Let me look at what panels are available per project/prototype
all_panels = df.copy()

# Group by project + prototype + instrument to get counts
panel_counts = all_panels.groupby(['project', 'prototype_id', 'instrument']).size().reset_index(name='n_readings')
print("\nPanel counts by project/prototype/instrument:")
print(panel_counts[panel_counts['n_readings'] >= 6].to_string())
