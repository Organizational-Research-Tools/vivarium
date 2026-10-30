import pandas as pd
D=pd.read_csv('records.csv'); mods=list(D.columns[11:23]);
R=D.groupby(['project','prototype_id'])[mods].first().reset_index(); y=D.groupby(['project','prototype_id','test']).value.mean().unstack().reset_index(); R=R.merge(y,on=['project','prototype_id'],how='left');
print(R.to_string(index=False))