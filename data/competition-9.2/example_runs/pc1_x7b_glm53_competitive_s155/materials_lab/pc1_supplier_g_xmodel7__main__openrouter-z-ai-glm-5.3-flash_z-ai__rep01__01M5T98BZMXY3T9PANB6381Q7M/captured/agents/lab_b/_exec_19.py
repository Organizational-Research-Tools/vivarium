import pandas as pd
df = pd.read_csv('records.csv')
g = df.groupby(['prototype_id','test']).agg(n=('value','size'),mn=('value','mean'),proj=('project','first')).reset_index()
piv = g.pivot_table(index=['prototype_id','proj'], columns='test', values='mn')
cnt = g.pivot_table(index=['prototype_id','proj'], columns='test', values='n')
piv=piv[piv.notna().sum(axis=1)>=2]; cnt=cnt.reindex(piv.index)
piv.columns=['heat','strength','water']; cnt.columns=['n_heat','n_str','n_water']
sel = piv[((piv.heat>=78.4)&(piv.strength>=7.15)&(piv.water>=79.4))]
print(sel.join(cnt).to_string())
for t in ['heat','strength','water']:
    print(t); print(piv.sort_values(t,ascending=False).head(6).join(cnt).to_string())