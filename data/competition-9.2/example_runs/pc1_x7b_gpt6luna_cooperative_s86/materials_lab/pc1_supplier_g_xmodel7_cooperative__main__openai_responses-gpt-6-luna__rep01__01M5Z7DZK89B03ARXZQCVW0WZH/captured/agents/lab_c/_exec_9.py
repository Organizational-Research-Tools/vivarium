import pandas as pd
x=pd.read_csv('records.csv')
for test in ['seal hold temperature','edge crush resistance','wet strength retained']:
 d=x[(x.prototype_id=='p_Z398MDW5ST')&(x.test==test)].sort_values('specimen')
 print(test, list(d.record_id), d.value.mean())