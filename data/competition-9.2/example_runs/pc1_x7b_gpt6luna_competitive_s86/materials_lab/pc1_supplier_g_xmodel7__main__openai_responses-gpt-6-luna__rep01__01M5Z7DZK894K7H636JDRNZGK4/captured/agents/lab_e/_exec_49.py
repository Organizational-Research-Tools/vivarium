import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_7S365TH6Y0','p_7S365TH6Y2','p_7S365TH6Y4','p_7S365TH6Y6']:
 y=x[(x.prototype_id==p)&(x.test=='strength')]
 print(p,y.value.mean())