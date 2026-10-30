import pandas as pd
df = pd.read_csv('records.csv')
e = df[df.kind=='exploratory'].copy()
# panel means too
p = df[df.kind=='qualification'].groupby(['prototype_id','project','test']).value.mean().reset_index()
pp = p.pivot_table(index=['prototype_id','project'],columns='test',values='value')
print("PANELS above C-ish:")
print(pp[(pp['seal hold temperature']>=78.2)|(pp['wet strength retained']>=79.8)|(pp['edge crush resistance']>=7.2)].to_string())
# exploratory means
g = e.groupby(['prototype_id','project','test']).value.mean().reset_index()
piv = g.pivot_table(index=['prototype_id','project'],columns='test',values='value')
piv = piv.rename(columns={'seal hold temperature':'heat','wet strength retained':'water','edge crush resistance':'strength'})
print(piv[(piv.strength>=7.15)].sort_values('strength',ascending=False).head(40).to_string())
