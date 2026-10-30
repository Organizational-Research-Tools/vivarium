import pandas as pd
df = pd.read_csv('records.csv')
g = df.groupby(['project','prototype_id','test']).value.mean().unstack()
g.columns=['heat','strength','water']
cand = g[(g.heat>=78.25)&(g.strength>=7.19)&(g.water>=79.2)]
print(cand)
print("---- near misses on water (>=78.6), others ok ----")
print(g[(g.heat>=78.25)&(g.strength>=7.19)&(g.water>=78.6)&(g.water<79.2)])