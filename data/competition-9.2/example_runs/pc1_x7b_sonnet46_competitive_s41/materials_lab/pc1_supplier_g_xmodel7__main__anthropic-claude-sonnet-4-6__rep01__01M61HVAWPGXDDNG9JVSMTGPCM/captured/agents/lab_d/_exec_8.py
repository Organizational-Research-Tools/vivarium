
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

# Focus on qualification panels (heat) for the prototypes we just measured
heat_qual = df[(df['kind'] == 'qualification') & (df['instrument'] == 'heat')]

# Group by prototype and project, compute means
summary = heat_qual.groupby(['project', 'prototype_id', 'measured_by'])['value'].agg(['mean', 'count']).reset_index()
summary = summary[summary['count'] == 6]  # full panels only
summary['pass_heat'] = summary['mean'] >= 77.5
summary = summary.sort_values(['project', 'mean'], ascending=[True, False])
print(summary.to_string(index=False))
