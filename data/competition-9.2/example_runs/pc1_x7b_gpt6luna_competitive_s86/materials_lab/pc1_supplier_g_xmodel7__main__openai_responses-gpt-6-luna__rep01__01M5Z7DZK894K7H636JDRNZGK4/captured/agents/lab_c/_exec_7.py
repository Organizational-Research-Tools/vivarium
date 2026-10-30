import pandas as pd
D=pd.read_csv('records.csv')
print(D[(D.project=='QP-9219')&(D.kind=='exploratory')].groupby(['prototype_id','instrument']).value.agg(['mean','count']).to_string())