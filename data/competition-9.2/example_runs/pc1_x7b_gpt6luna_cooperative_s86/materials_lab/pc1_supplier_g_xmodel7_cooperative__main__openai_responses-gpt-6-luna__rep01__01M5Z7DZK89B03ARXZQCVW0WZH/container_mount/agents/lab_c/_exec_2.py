import pandas as pd, numpy as np
D=pd.read_csv('records.csv')
mods=list(D.columns[11:23])
print('unique prototypes',D.prototype_id.nunique(),'projects',D.project.unique())
P=D.pivot_table(index=['project','prototype_id'],columns='test',values='value',aggfunc='mean').reset_index()
C=D.groupby(['project','prototype_id'])[mods].first().reset_index()
P=P.merge(C,on=['project','prototype_id'])
print(P[['project','prototype_id','heat','strength','water','base_sheet']].to_string(index=False))