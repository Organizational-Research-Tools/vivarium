import pandas as pd
x=pd.read_csv('records.csv'); x=x[x.project=='QP-6879']
# aggregate per prototype/test all qualification and exploratory
for kind in ['qualification','exploratory']:
 g=x[x.kind==kind].groupby(['prototype_id','test']).value.agg(['mean','count']).unstack('test')
 print('\n',kind)
 print(g.to_string())