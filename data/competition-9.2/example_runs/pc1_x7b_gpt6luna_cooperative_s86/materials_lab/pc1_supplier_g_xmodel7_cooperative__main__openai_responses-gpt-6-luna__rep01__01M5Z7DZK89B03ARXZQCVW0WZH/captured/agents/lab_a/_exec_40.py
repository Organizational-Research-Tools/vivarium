import pandas as pd
x=pd.read_csv('records.csv')
means=x[x.kind=='qualification'].pivot_table(index=['project','prototype_id'],columns='test',values='value',aggfunc='mean')
for proj,g in means.groupby(level=0):
 print('\n',proj)
 g=g.copy()
 # show candidates with number of tests >=2 and any passing C
 g['passcount']=((g.get('seal hold temperature',0)>=78.625).astype(int)+(g.get('edge crush resistance',0)>=7.235).astype(int)+(g.get('wet strength retained',0)>=79.8).astype(int))
 g['near']=((g.get('seal hold temperature',0)-78.625).clip(upper=0)/.25)**2+((g.get('edge crush resistance',0)-7.235).clip(upper=0)/.03)**2+((g.get('wet strength retained',0)-79.8).clip(upper=0)/.4)**2
 print(g.sort_values(['passcount','near'],ascending=[False,True]).head(12).round(4).to_string())