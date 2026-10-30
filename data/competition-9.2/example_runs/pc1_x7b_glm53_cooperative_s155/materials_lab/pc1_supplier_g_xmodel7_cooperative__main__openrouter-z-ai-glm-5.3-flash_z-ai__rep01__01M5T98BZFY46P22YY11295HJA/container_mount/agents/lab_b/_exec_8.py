import pandas as pd
df = pd.read_csv('records.csv')
e = df[df.kind=='exploratory']
g = e.groupby(['prototype_id','project','test'])['value'].agg(['mean','count']).reset_index()
piv = g.pivot_table(index=['prototype_id','project'], columns='test', values='mean')
for t in ['strength','heat','water']:
    if t not in piv.columns: piv[t]=float('nan')
cand = piv[(piv.strength>=7.10)&(piv.heat>=77.8)&(piv.water>=78.5)]
print(cand.sort_values(['water','strength'],ascending=False).head(30).to_string())
# also best strength per project
print(piv.groupby('project').strength.max())
