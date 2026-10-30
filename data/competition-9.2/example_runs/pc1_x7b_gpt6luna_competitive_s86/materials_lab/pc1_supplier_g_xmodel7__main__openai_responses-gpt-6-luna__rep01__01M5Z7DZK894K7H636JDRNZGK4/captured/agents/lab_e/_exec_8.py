import pandas as pd
r=pd.read_csv('records.csv')
print('rows',len(r),'by proj/instrument/kind')
print(r.groupby(['project','instrument','kind']).size().to_string())
# means by proto project test
m=r.groupby(['project','prototype_id','instrument','kind','measured_by','requester'])['value'].agg(['count','mean']).reset_index()
print('\nPROTOTYPES')
for p,g in m.groupby('project'):
 print('\n',p)
 print(g.to_string(index=False))